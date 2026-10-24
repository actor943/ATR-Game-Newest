# games/chess/views.py
# -*- coding: utf-8 -*-
"""国际象棋 UI 视图（Flet）。"""
from __future__ import annotations

import asyncio

import flet as ft

from core.i18n import t
from core.registry import NavigateFn
from core.theme import T
from core.ui_common import app_bar, page_padding, menu_card, page_width
from core.net import session as _sess
from core import registry
from core import history

from .engine import ChessGame, PROMO_ORDER
from .assets import available_themes, piece_image_src

# 棋盘配色（木质风格，不随主题卡片色变化，避免视觉冲突）
LIGHT_SQ = "#F0D9B5"
DARK_SQ = "#B58863"
SELECTED = "#7B61FF"
LASTMOVE = "#C8E6C9"
CHECK_TINT = "#FF8A80"

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


class ChessPlayView:
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

        # 联网：挂上网络回调、算出身份、后台轮询席位变化，并向房主要当前局面
        if self.net is not None:
            global _ACTIVE
            _ACTIVE = self
            self.net.set_game_handler(self._on_net)
            self._compute_role()
            self._refresh_net_text()
            if self.net.is_host:
                # 房主进房即把当前局面推给所有人：客人不必等要牌，
                # 「开始游戏」瞬间视图重建的先后差不会让人停在旧局面
                # （0.4.8-fix：此前只被动回 req_state，客人那帧常被吞掉）
                self.net.send_game({"k": "state", "s": self.game.serialize()})
            else:
                self.net.send_game({"k": "req_state"})
                self.page.run_task(self._sync_wait())
            self.page.run_task(self._net_poll())

        # 开局记录一行（本地双人 / 联网-白方-黑方-观战）
        self._log_lines.append(f"对局开始：{self._mode_label()}")

        return ft.Column([
            app_bar("对局", on_back=on_back),
            page_padding(body),
        ], expand=True)

    # ------------------------------------------------------------------
    def _cell_size(self) -> int:
        avail = page_width(self.page) - 2 * getattr(T, "PADDING", 16) - 12
        board_w = min(avail, 460)
        return max(34, int(board_w / 8))

    def _render_board(self):
        size = self._cell_size()
        row_idxs = list(range(8)) if not self.flip else list(range(7, -1, -1))
        col_idxs = list(range(8)) if not self.flip else list(range(7, -1, -1))

        valid = set()
        if self.selected_pos:
            valid = {(r, c) for (r, c) in self.game.get_valid_moves(*self.selected_pos)}

        lm = self.game.last_move
        last_set = set()
        if lm:
            last_set = {(lm[0], lm[1]), (lm[2], lm[3])}

        rows = []
        for r in row_idxs:
            cells = []
            for c in col_idxs:
                cells.append(self._make_cell(r, c, size, valid, last_set))
            rows.append(ft.Row(cells, spacing=0))
        self.board_container.content = ft.Column(rows, spacing=0)
        self.board_container.width = size * 8 + 4

    def _make_cell(self, r, c, size, valid, last_set) -> ft.Control:
        piece = self.game.get_piece(r, c)
        is_light = (r + c) % 2 == 0
        bgcolor = LIGHT_SQ if is_light else DARK_SQ

        if (r, c) == self.selected_pos:
            bgcolor = SELECTED
        elif (r, c) in last_set:
            bgcolor = LASTMOVE
        if self.game.in_check(self.game.turn) and piece == self.game.turn + "K":
            bgcolor = CHECK_TINT

        img = None
        if piece:
            img = ft.Image(
                src=piece_image_src(piece, self.theme),
                width=size - 6, height=size - 6,
                fit=ft.BoxFit.CONTAIN,
            )
        base = ft.Container(
            content=img, alignment=ft.alignment.Alignment(0, 0),
            width=size, height=size,
        )

        if (r, c) in valid:
            dot = ft.Container(
                width=14 if not piece else size - 10,
                height=14 if not piece else size - 10,
                border_radius=7 if not piece else (size - 10) / 2,
                bgcolor=None if piece else SELECTED,
                border=None if not piece else ft.Border.all(3, SELECTED),
                opacity=0.55,
            )
            base = ft.Stack(
                [
                    ft.Container(content=img, alignment=ft.alignment.Alignment(0, 0),
                                 width=size, height=size),
                    ft.Container(content=dot, alignment=ft.alignment.Alignment(0, 0),
                                 width=size, height=size),
                ],
                width=size, height=size,
            )

        return ft.Container(
            content=base,
            bgcolor=bgcolor,
            width=size, height=size,
            on_click=lambda e, row=r, col=c: self._on_cell_click(row, col),
        )

    # ------------------------------------------------------------------
    def _on_cell_click(self, r: int, c: int):
        # 联网：对手已离场，对局结束，不能再走
        if self.opponent_left:
            self._toast("对局已结束（对手离场）")
            return
        # 联网观战：不能操作棋盘
        if self.net is not None and self.role == "spectator":
            self._toast("你正在观战，不能走子")
            return
        # 联网对局：只能走「轮到自己」的那一方
        if self.net is not None and self.role not in ("w", "b"):
            return
        if self.net is not None and self.role != self.game.turn:
            self._toast("还没轮到你")
            return

        # 1. 已选中棋子且点击合法目标 → 走子（可能需要升变）
        if self.selected_pos:
            fr, fc = self.selected_pos
            if (r, c) in self.game.get_valid_moves(fr, fc):
                piece = self.game.get_piece(fr, fc)
                if piece and piece[1] == "P" and r in (0, 7):
                    self.promotion_pending = (fr, fc, r, c)
                    self._open_promo(piece[0])
                    return
                self._do_move(fr, fc, r, c, None)
                return

        # 2. 选中 / 取消选中自己的棋子
        piece = self.game.get_piece(r, c)
        if piece and piece[0] == self.game.turn:
            self.selected_pos = (r, c)
        else:
            self.selected_pos = None
        self._render_board()
        self.page.update()

    def _do_move(self, fr, fc, tr, tc, promo):
        color = self.game.turn               # 走子方颜色（走之前）
        ok = self.game.move(fr, fc, tr, tc, promotion=promo)
        if ok:
            self._record_ply(color, fr, fc, tr, tc, promo)
            self.selected_pos = None
            self._render_board()
            self._update_status()
            # 联网：把这一步可靠地发给房间里其他人
            if self.net is not None and self.role in ("w", "b"):
                self.net.send_game({"k": "mv", "fr": fr, "fc": fc,
                                    "tr": tr, "tc": tc, "p": promo or ""})
            self._maybe_save_on_end()

    # ------------------------------------------------------------------
    def _open_promo(self, color: str):
        btns = []
        for pc in PROMO_ORDER:
            code = color + pc
            btns.append(
                ft.Container(
                    content=ft.Image(src=piece_image_src(code, self.theme),
                                     width=46, height=46, fit=ft.BoxFit.CONTAIN),
                    ink=True,
                    on_click=lambda e, p=pc: self._choose_promo(p),
                )
            )
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("选择升变兵种"),
            content=ft.Row(btns, spacing=10, alignment=ft.MainAxisAlignment.CENTER),
            actions=[ft.TextButton("取消", on_click=self._cancel_promo)],
        )
        self.page.show_dialog(dlg)

    def _choose_promo(self, promo: str):
        self.page.pop_dialog()
        if self.promotion_pending:
            fr, fc, tr, tc = self.promotion_pending
            self.promotion_pending = None
            self._do_move(fr, fc, tr, tc, promo)

    def _cancel_promo(self, _e):
        self.page.pop_dialog()
        self.promotion_pending = None

    # ------------------------------------------------------------------
    def _on_theme_change(self, e):
        self.theme = e.control.value
        self._render_board()
        self.page.update()

    def _update_status(self):
        # 联网：对手中途离场，直接判在场方获胜
        if self.opponent_left:
            side = "白方" if self.role == "w" else "黑方"
            self.status_text.value = f"🏁 对方离开，{side}获胜！"
            self.status_text.color = T.DANGER
            self._save_match_log(opponent_left=True)
            self.page.update()
            return
        txt = self.game.status_text()
        color = T.TEXT_PRIMARY
        if self.game.is_checkmate():
            color = T.DANGER
            txt = "🏁 " + txt
        elif self.game.in_check(self.game.turn):
            color = T.WARNING
            txt = "⚠ " + ("白方被将军！" if self.game.turn == "w" else "黑方被将军！")
        self.status_text.value = txt
        self.status_text.color = color
        self.page.update()

    # ------------------------------------------------------------------
    # 联网对弈相关
    # ------------------------------------------------------------------
    def _toast(self, msg: str):
        try:
            self.page.pop_dialog()
        except Exception:
            pass
        try:
            self.page.show_dialog(
                ft.AlertDialog(
                    modal=False,
                    content=ft.Text(msg),
                    actions=[ft.TextButton(
                        "知道了",
                        on_click=lambda _e: self.page.pop_dialog())],
                )
            )
        except Exception:
            pass

    def _compute_role(self):
        """根据房间席位表算出本机是白方 / 黑方 / 观战。

        规则：座位号最小的两个上场座位（< players）分别是白、黑；
        其余座位以及未入座的人都是观战。
        """
        if self.net is None:
            self.role = "local"
            return
        members = self.net.roster()
        me = self.net.me
        seated = sorted((m for m in members.values() if m.seat >= 0),
                        key=lambda m: m.seat)
        players = [m for m in seated if m.seat < self.players]
        white_mid = players[0].mid if len(players) > 0 else None
        black_mid = players[1].mid if len(players) > 1 else None
        self.white_mid = white_mid
        self.black_mid = black_mid
        if me.mid == white_mid:
            self.role = "w"
        elif me.mid == black_mid:
            self.role = "b"
        else:
            self.role = "spectator"

    def _evaluate_presence(self):
        """判断联网对手是否中途离场（在场方直接判胜）。

        仅在「本机是上场玩家且对面的玩家座位已空、对局尚未结束」时成立；
        观战方 / 双方都不在时不判胜（只负责显示谁离开了）。
        """
        if self.net is None or self.role not in ("w", "b"):
            self.opponent_left = False
            return
        opp_mid = self.black_mid if self.role == "w" else self.white_mid
        self.opponent_left = (opp_mid is None) and not self.game.is_game_over()

    def _refresh_net_text(self):
        if self.net is None or self.page is None:
            return
        self._evaluate_presence()
        if self.opponent_left:
            self.net_text.value = "对方已离开，可重开新对局"
            # 判胜文案交给 _update_status 统一显示
            self._update_status()
            return
        if self.role == "local":
            self.net_text.value = ""
        elif self.role == "spectator":
            missing = []
            if self.white_mid is None:
                missing.append("白方")
            if self.black_mid is None:
                missing.append("黑方")
            if missing:
                self.net_text.value = "观战中 · " + "、".join(missing) + "已离开"
            else:
                self.net_text.value = "观战中 · 轮到" + (
                    "白方" if self.game.turn == "w" else "黑方")
        else:
            side = "白方" if self.role == "w" else "黑方"
            opp_mid = self.black_mid if self.role == "w" else self.white_mid
            if opp_mid is None:
                self.net_text.value = f"你是{side} · 对方已离开，等待新对手"
            elif self.role == self.game.turn:
                self.net_text.value = f"你是{side} · ▶ 轮到你走棋"
            else:
                self.net_text.value = f"你是{side} · ⏳ 等待对方"
        try:
            self.page.update()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 对局记录（与掼蛋共用 core/history 的落盘逻辑）
    # ------------------------------------------------------------------
    def _mode_label(self) -> str:
        """这一局的模式，写进记录元信息。"""
        if self.net is None:
            return "本地双人"
        if self.role == "spectator":
            return "联网-观战"
        return "联网-" + ("白方" if self.role == "w" else "黑方")

    @staticmethod
    def _coord(r: int, c: int) -> str:
        """棋盘坐标 (row, col) → 国际象棋记谱坐标，如 e2、a7。"""
        return chr(ord("a") + c) + str(8 - r)

    def _record_ply(self, color: str, fr: int, fc: int, tr: int, tc: int,
                    promo) -> None:
        """把一步着法追加到落盘日志（纯文本，赛后保存用）。"""
        self._ply += 1
        move_no = (self._ply + 1) // 2          # 第几个完整回合（1 起）
        side = "白" if color == "w" else "黑"
        promo_s = ("=" + promo) if promo else ""
        san = (f"{move_no}. {side} {self._coord(fr, fc)}"
               f"-{self._coord(tr, tc)}{promo_s}")
        if self.game.is_checkmate():
            san += " #"                          # 将死
        elif self.game.in_check(self.game.turn):
            san += "+"                           # 将军
        self._log_lines.append(san)

    def _maybe_save_on_end(self) -> None:
        """对局结束（将死 / 逼和）且还没保存过，就落盘。"""
        if self.game.is_game_over() and not self._log_saved:
            self._save_match_log(finished=True)

    def _save_match_log(self, finished: bool = True,
                        opponent_left: bool = False) -> None:
        """把这一局的完整着法落盘到应用数据目录（``logs/chess/``）。

        将死 / 逼和 / 对手离场 会存；中途离开（``on_back``）也存（标「中途结束」），
        这样历史记录里每一局都留得下。同一局只写一次文件。
        """
        if self._log_saved or not self._log_lines:
            return
        self._log_saved = True
        if opponent_left:
            winner = "白方" if self.role == "w" else "黑方"
            state = "对手离场判胜"
        elif self.game.is_checkmate():
            # 轮到走棋的一方被将死 → 对方获胜
            winner = "黑方" if self.game.turn == "w" else "白方"
            state = "整场结束"
        elif self.game.is_stalemate():
            winner = "和棋"
            state = "整场结束"
        elif not finished:
            winner = "未分胜负"
            state = "中途结束（未打完）"
        else:
            winner = "未分胜负"
            state = "中途结束（未打完）"
        mode = self._mode_label()
        lines = list(self._log_lines) + [
            f"◆ 记录结束：{state} · 共 {self._ply} 步 · {mode}",
        ]
        try:
            history.save_match_log(
                "chess", lines,
                meta={
                    "状态": state,
                    "胜方": winner,
                    "步数": self._ply,
                    "模式": mode,
                },
            )
        except Exception:                          # noqa: BLE001
            pass     # 数据目录不可写时静默失败，不影响对局

    def _on_net(self, msg):
        """收到房间里的玩法消息（来自其他设备）。"""
        if self is not _ACTIVE or self.net is None:
            return
        data = msg.get("data") or {}
        k = data.get("k")
        if k == "mv":
            color = self.game.turn               # 走子方颜色（走之前）
            self.game.move(data["fr"], data["fc"], data["tr"], data["tc"],
                           promotion=data.get("p") or None)
            self._record_ply(color, data["fr"], data["fc"],
                             data["tr"], data["tc"], data.get("p") or None)
            self.selected_pos = None
            self._render_board()
            self._update_status()
            self._maybe_save_on_end()
        elif k == "reset":
            self.game.reset()
            self.selected_pos = None
            self._render_board()
            self._update_status()
            # 重开 = 新的一局，记录从头再来
            self._log_lines = []
            self._log_saved = False
            self._ply = 0
            self._log_lines.append(f"对局开始：{self._mode_label()}")
        elif k == "undo":
            self.game.undo()
            self.selected_pos = None
            self._render_board()
            self._update_status()
        elif k == "req_state":
            if self.net.is_host:
                self.net.send_game({"k": "state", "s": self.game.serialize()})
        elif k == "state":
            state = data.get("s")
            if state:
                self._state_synced = True
                self.game.load_state(state)
                # 迟到者从中途局面加入，只记录后续着法
                if not self._log_lines:
                    self._log_lines.append("（从中途局面开始记录）")
                self.selected_pos = None
                self._render_board()
                self._update_status()
        # 任何网络事件后都重算身份（可能有人入座 / 离座）
        self._compute_role()
        self._refresh_net_text()

    async def _sync_wait(self):
        """没拿到房主局面就周期性重问（房主的视图可能比我们晚建好）。"""
        for _ in range(40):                     # 最多等 20 秒
            if self._state_synced or self is not _ACTIVE:
                return
            self.net.send_game({"k": "req_state"})
            await asyncio.sleep(0.5)

    async def _net_poll(self):
        """后台轮询席位变化，让「等待对方入座 / 对方离开」等状态及时刷新。"""
        while True:
            if self is not _ACTIVE or self.net is None:
                return
            try:
                self._compute_role()
                self._refresh_net_text()
            except Exception:
                pass
            await asyncio.sleep(0.6)


def build_play(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    return ChessPlayView(page, navigate).build()
