# -*- coding: utf-8 -*-
"""国际象棋 UI 视图（Flet）。

模块划分
--------
原文件 660 多行，现在按职责拆开（``ChessPlayView`` 用 mixin 组合起来）：

============================== ========================================== ==========
模块                         负责什么                                  行数量级
============================== ========================================== ==========
``views.py``（本文件）        子菜单 + 视图骨架 + 工具栏 + 生命周期    约 190
``views_board.py``            棋盘画面、点格子走子、升变选择          约 200
``views_sync.py``             联机身份计算、局面同步、席位轮询        约 210
``views_record.py``           棋谱记录与落盘                          约 100
============================== ========================================== ==========

同一时刻只有「当前正在显示」的那一个象棋视图才应该响应网络消息，
避免路由器缓存的旧视图实例仍在后台收消息（见 ``_ACTIVE``）。
"""

from __future__ import annotations

import flet as ft

from core.i18n import t
from core.registry import NavigateFn
from core.theme import T
from core.ui_common import app_bar, page_padding, menu_card
from core.net import session as _sess
from core import registry

from .engine import ChessGame
from .assets import available_themes
from .views_board import ChessBoardMixin
from .views_record import ChessRecordMixin
from .views_sync import ChessSyncMixin

# 同一时刻只有「当前正在显示」的那一个象棋视图才应该响应网络消息，
# 避免路由器缓存的旧视图实例仍在后台收消息。
_ACTIVE: "ChessPlayView | None" = None

def build_home(_page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """国际象棋子菜单。"""

    def go_play(_e):
        # 每次进对局都重建视图：重新判断是「本地双人」还是「房间联网」
        from core.router import Router
        if Router.current is not None:
            Router.current.invalidate("/g/chess/play")
        navigate("/g/chess/play")

    def go_back(_e):
        navigate("/")

    def go_history(_e):
        from .history_view import open_history
        open_history(navigate)        # 丢掉缓存，进来看的是最新记录

    body = ft.Column([
        ft.Text(t("chess.home.intro"),
                size=13, color=T.TEXT_SECONDARY),
        ft.Container(height=16),
        ft.Row([
            menu_card(
                title=t("chess.home.play"),
                description=t("chess.home.play_desc"),
                icon="♟️",
                available=True,
                on_click=go_play,
            ),
            menu_card(
                title=t("chess.home.history"),
                description=t("chess.home.history_desc"),
                icon="🕘",
                available=True,
                on_click=go_history,
            )
        ], wrap=True),
    ])

    return ft.Column(
        [
            app_bar(t("game.chess.title"), on_back=go_back),
            page_padding(body),
        ],
        expand=True,
    )

class ChessPlayView(ChessBoardMixin, ChessSyncMixin, ChessRecordMixin):
    def __init__(self, page: ft.Page, navigate: NavigateFn):
        self.page = page
        self.navigate = navigate
        self.game = ChessGame()
        self.selected_pos: tuple | None = None
        self.theme = (available_themes()[0] if available_themes() else "Cyborg")
        self.flip = False
        self.promotion_pending: tuple | None = None  # (fr, fc, tr, tc)

        # ---- 联网对弈状态 ----
        self.net = _sess.current()            # 房间会话；None 表示本地双人
        self.players = registry.game_players("chess")
        self.role = "local"                   # "local" / "w" / "b" / "spectator"
        self.white_mid: str | None = None
        self.black_mid: str | None = None
        self.opponent_left = False            # 联网中对手中途离场（在场方判胜）
        # 客人是否已拿到房主局面（没拿到就周期性重问，见 _sync_wait）
        self._state_synced = self.net is None or bool(self.net.is_host)

        # ---- 对局记录（赛后落盘，供历史页回看，底层逻辑见 core/history）----
        self._log_lines: list = []            # 纯文本着法行，赛后保存用
        self._log_saved = False               # 这一局是否已落盘（防重复写）
        self._ply = 0                         # 已记录的半回合数

        self.board_container = ft.Container()
        self.status_text = ft.Text("白方走棋", size=18, weight=ft.FontWeight.BOLD)
        self.net_text = ft.Text("", size=12, color=T.TEXT_SECONDARY)

        self.theme_dd = ft.Dropdown(
            label="棋子皮肤",
            width=160,
            value=self.theme,
            options=[ft.dropdown.Option(t) for t in available_themes()],
            on_select=self._on_theme_change,
        )

    # ------------------------------------------------------------------
    def build(self) -> ft.Control:
        self._render_board()

        def on_undo(_e):
            # 联网时只有「轮到你」才能悔棋（撤回对方刚走的一步）
            if self.net is not None and self.role not in ("w", "b"):
                self._toast("观战中，不能悔棋")
                return
            if self.net is not None and self.role != self.game.turn:
                self._toast("还没轮到你")
                return
            if self.game.undo():
                self.selected_pos = None
                self._render_board()
                self._update_status()
                if self.net is not None:
                    self.net.send_game({"k": "undo"})

        def on_reset(_e):
            if self.net is not None and not self.net.is_host:
                self._toast("只有房主能重开")
                return
            self.game.reset()
            self.selected_pos = None
            self._render_board()
            self._update_status()
            # 重开 = 新的一局，记录从头再来
            self._log_lines = []
            self._log_saved = False
            self._ply = 0
            self._log_lines.append(f"对局开始：{self._mode_label()}")
            if self.net is not None:
                self.net.send_game({"k": "reset"})

        def on_flip(_e):
            self.flip = not self.flip
            self.selected_pos = None
            self._render_board()
            self.page.update()

        def on_back(_e):
            # 离开对局：先把（未结束的）这一局落盘，再摘掉网络回调、停下轮询
            self._save_match_log(finished=False)
            global _ACTIVE
            _ACTIVE = None
            if self.net is not None:
                self.net.set_game_handler(None)
            self.navigate("/g/chess" if self.net is None else "/room")

        toolbar = ft.Row([
            ft.Button(content=ft.Text("悔棋"), icon=ft.Icons.UNDO, on_click=on_undo),
            ft.Button(content=ft.Text("重开"), icon=ft.Icons.REFRESH, on_click=on_reset),
            ft.Button(content=ft.Text("翻转"), icon=ft.Icons.AUTORENEW, on_click=on_flip),
            self.theme_dd,
        ], wrap=True, alignment=ft.MainAxisAlignment.CENTER)

        body = ft.Column([
            self.status_text,
            self.net_text,
            ft.Container(height=10),
            ft.Container(
                content=self.board_container,
                border=ft.Border.all(2, "#8B4513"),
                border_radius=4,
                padding=2,
                alignment=ft.alignment.Alignment(0, 0),
            ),
            ft.Container(height=16),
            toolbar,
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        # 联网：挂上网络回调、算出身份、后台轮询席位变化，并向房主要当前局面。
        # 整段兜底：网络/序列化任何一环出错都只影响联机，不能把棋局页带崩
        # （手机上未捕获异常 = "Error running app" 红屏，应用直接不可用）。
        if self.net is not None:
            global _ACTIVE
            _ACTIVE = self
            try:
                self.net.set_game_handler(self._on_net)
                self._compute_role()
                self._refresh_net_text()
                if self.net.is_host:
                    # 房主进房即把当前局面推给所有人：客人不必等要牌，
                    # 「开始游戏」瞬间视图重建的先后差不会让人停在旧局面
                    # （0.4.8-fix：此前只被动回 req_state，客人那帧常被吞掉）
                    self.net.send_game({"k": "state",
                                        "s": self.game.serialize()})
                else:
                    self.net.send_game({"k": "req_state"})
                    self.page.run_task(self._sync_wait)      # 传方法，别带括号！
                self.page.run_task(self._net_poll)           # 同上（带括号会
                # TypeError: handler must be a coroutine function，对联机双方都生效）
            except Exception as exc:
                print(f"[chess] 联机初始化失败，按单机观战继续：{exc!r}")
                self.role = "spectator"

        # 开局记录一行（本地双人 / 联网-白方-黑方-观战）
        self._log_lines.append(f"对局开始：{self._mode_label()}")

        return ft.Column([
            app_bar("对局", on_back=on_back),
            page_padding(body),
        ], expand=True)

    # ------------------------------------------------------------------
    # 生命周期辅助
    # ------------------------------------------------------------------
    def _is_active_view(self) -> bool:
        """我是不是「当前正在显示」的那一个棋局视图。

        路由器会缓存视图，旧实例可能还在后台活着；只有当前显示的那一个
        才应该响应网络消息，否则客人会看到两个棋盘同时在动。
        """
        return self is _ACTIVE

def build_play(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    return ChessPlayView(page, navigate).build()
