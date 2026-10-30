# -*- coding: utf-8 -*-
"""五子棋棋盘画面：网格、落子、悔棋、重开；可选联机同步。

* 本地模式：两人轮流用同一屏幕点格。
* 联机模式：若 ``core.net.session.current()`` 非空，本机按席位决定执黑/执白；
  房主是权威方（客人把走子请求发给房主，房主落子后广播整盘快照）。
"""

from __future__ import annotations

from typing import Optional

import flet as ft

from core import registry
from core.i18n import t
from core.registry import NavigateFn
from core.theme import T
from core.ui_common import app_bar, page_padding, page_width

from .engine import (
    BLACK, BLACK_WIN, DRAW, SIZE, WHITE, WHITE_WIN,
    GomokuEngine,
)

CELL = 30                       # 旧版「按格子」布局用的格宽（保留备用）
SPACING = 28                    # 相邻两个**交叉点**之间的距离（棋盘线间距）
STONE = 22                      # 棋子直径
MARGIN = SPACING                # 棋盘留白：最外侧那条线离边的距离
BOARD_SIZE = 2 * MARGIN + (SIZE - 1) * SPACING      # 棋盘整体边长

# 颜色（不跟主题变，木头/黑白是本体）
_BOARD_BG = "#E8C88A"
_GRID_LINE = "#7A5A2A"
_BLACK_STONE = "#1A1A1A"
_WHITE_STONE = "#FAFAFA"
_WIN_HL = "#FF5252"

# 同一时刻只有「当前正在显示」的那一个棋局才应该收发网络消息，
# 避免路由器缓存的旧视图实例仍在后台收消息（与象棋同思路）。
_ACTIVE: Optional["_BoardPage"] = None


def _session():
    """当前房间会话；``None`` 表示本地双人。"""
    try:
        from core.net import session as S
        return S.current()
    except Exception:                       # noqa: BLE001 — 纯本地环境
        return None


class _BoardPage:
    """一页棋局：持有引擎、控件、本机身份。"""

    def __init__(self, page: ft.Page, navigate: NavigateFn):
        self.page = page
        self.navigate = navigate
        self.engine = GomokuEngine()
        self.net = _session()               # None = 本地双人
        self.players = registry.game_players("gomoku")
        self.role = "local"                 # "local"/"black"/"white"/"spectator"
        self._compute_role()

        self.board_host = ft.Column(spacing=0)
        self.status_text = ft.Text("", size=14, color=T.TEXT_PRIMARY)
        self.turn_text = ft.Text("", size=14, color=T.TEXT_SECONDARY)
        self._log_saved = False          # 这一局是否已经落过盘
        # 棋盘尺寸：按屏幕宽度缩放，手机上整盘留在屏幕里
        (self.spacing, self.stone, self.margin,
         self.board_size) = self._fit_board()
        self._narrow = page_width(self.page) < 620      # 手机竖屏

    # ---------- 尺寸 ----------

    def _fit_board(self):
        """按可用宽度算棋盘尺寸（线距 / 棋子 / 留白 / 整体边长）。

        桌面按原尺寸（线距 28、棋子 22、整体 448），手机按比例缩小 ——
        15 路棋盘在 375 逻辑像素宽的手机上必须缩，否则右边一列会跑到
        屏幕外面去。
        """
        avail = page_width(self.page) - 2 * getattr(T, "PADDING", 16) - 20
        if avail <= 0:
            avail = 320.0
        # 棋盘边长 = 2*留白 + (SIZE-1)*线距，而留白 = 线距 → 边长 = (SIZE+1)*线距
        spacing = min(SPACING, max(14, int(avail) // (SIZE + 1)))
        stone = max(11, int(round(STONE * spacing / float(SPACING))))
        margin = spacing
        size = 2 * margin + (SIZE - 1) * spacing
        return spacing, stone, margin, size

    # ---------- 身份 ----------

    def _compute_role(self) -> None:
        """按房间席位表算本机身份。

        规则：座位号最小的两个上场座位（``seat < players``）分别是黑、白；
        其余座位以及未入座的人都是观战。
        """
        if self.net is None:
            self.role = "local"
            return
        black_mid = white_mid = None
        try:
            # roster() 返回的是 List[Member]（按座位排），不是字典。
            members = self.net.roster()
            seated = sorted((m for m in members if m.seat >= 0),
                            key=lambda m: m.seat)
            players = [m for m in seated if m.seat < self.players]
            black_mid = players[0].mid if players else None
            white_mid = players[1].mid if len(players) > 1 else None
        except Exception as exc:            # 手机端红屏比"降级成观战"糟糕得多
            print(f"[gomoku] 算身份失败，先按观战处理：{exc!r}")
        me = getattr(self.net, "me", None)
        my_mid = getattr(me, "mid", None)
        if my_mid is not None and my_mid == black_mid:
            self.role = "black"
        elif my_mid is not None and my_mid == white_mid:
            self.role = "white"
        else:
            self.role = "spectator"

    # ---------- 画面 ----------

    def _stone_dot(self, stone: int, highlight: bool) -> Optional[ft.Control]:
        """一颗棋子（圆形）；空点返回 None。"""
        if stone == 0:
            return None
        color = _BLACK_STONE if stone == BLACK else _WHITE_STONE
        border = _WIN_HL if highlight else (T.TEXT_INVERT if stone == BLACK
                                            else "#555555")
        return ft.Container(
            width=self.stone, height=self.stone,
            bgcolor=color,
            border=ft.Border.all(2 if highlight else 1, border),
            border_radius=self.stone // 2,
        )

    def _grid_lines(self) -> list:
        """棋盘线：15 条横线 + 15 条竖线。

        **线是画出来的，棋子摆在这些线的交汇点上**（五子棋的规矩）：
        第 (r,c) 个交叉点的坐标 = (MARGIN + c*SPACING, MARGIN + r*SPACING)。
        """
        span = (SIZE - 1) * self.spacing
        lines = []
        for i in range(SIZE):
            lines.append(ft.Container(
                left=self.margin, top=self.margin + i * self.spacing,
                width=span, height=1, bgcolor=_GRID_LINE))
            lines.append(ft.Container(
                left=self.margin + i * self.spacing, top=self.margin,
                width=1, height=span, bgcolor=_GRID_LINE))
        return lines

    def _star_points(self) -> list:
        """天元与四个星位（小圆点，纯装饰）。"""
        mids = [3, 7, 11]
        dots = []
        for r in mids:
            for c in mids:
                if (r, c) not in ((3, 3), (3, 11), (11, 3), (11, 11),
                                  (7, 7)):
                    continue
                dots.append(ft.Container(
                    left=self.margin + c * self.spacing - 3,
                    top=self.margin + r * self.spacing - 3,
                    width=6, height=6,
                    bgcolor=_GRID_LINE, border_radius=3))
        return dots

    def _cell_control(self, r: int, c: int) -> ft.Control:
        """一个交叉点：透明点击热区 + 摆在该点上的棋子。

        热区是 SPACING×SPACING 的方块，**以交叉点为中心**（因此点在线上、
        点在线旁边都不会落到隔壁格）；棋子画在热区正中，也就是线的交汇点。
        """
        s = self.engine.state
        stone = s.board[r][c]
        win = (r, c) in set(s.win_line)
        clickable = self._can_click() and stone == 0
        center_x = self.margin + c * self.spacing
        center_y = self.margin + r * self.spacing
        return ft.Container(
            left=center_x - self.spacing // 2,
            top=center_y - self.spacing // 2,
            width=self.spacing, height=self.spacing,
            alignment=ft.Alignment.CENTER,
            ink=clickable,
            on_click=(lambda _e, rr=r, cc=c: self._on_click(rr, cc))
            if clickable else None,
            content=self._stone_dot(stone, win),
        )

    def _can_click(self) -> bool:
        """轮到我才能点。"""
        s = self.engine.state
        if s.result != 0:
            return False
        if self.role == "spectator":
            return False
        if self.role == "local":
            return True
        me = BLACK if self.role == "black" else WHITE
        return s.turn == me

    def _render_board(self):
        """重画棋盘：先铺线，再把棋子摆到线的交汇点上。"""
        stones = [self._cell_control(r, c)
                  for r in range(SIZE) for c in range(SIZE)]
        self.board_host.controls = [
            ft.Stack(
                controls=[*self._grid_lines(), *self._star_points(), *stones],
                width=self.board_size, height=self.board_size,
            )
        ]

    def _render_side(self):
        s = self.engine.state
        if s.result == BLACK_WIN:
            self.status_text.value = t("gomoku.black_win", default="黑方获胜！")
        elif s.result == WHITE_WIN:
            self.status_text.value = t("gomoku.white_win", default="白方获胜！")
        elif s.result == DRAW:
            self.status_text.value = t("gomoku.draw", default="平局")
        else:
            self.status_text.value = ""
        who = t("gomoku.black", default="黑方") if s.turn == BLACK \
            else t("gomoku.white", default="白方")
        self.turn_text.value = t("gomoku.turn", who=who,
                                 default=f"轮到 {who}")

    def _refresh(self):
        self._render_board()
        self._render_side()
        self.page.update()

    # ---------- 交互 ----------

    def _after_play(self) -> None:
        """落子成功后的统一处理：刷新界面 + 分出胜负就落盘。"""
        self._refresh()
        if self.engine.state.result:
            self._save_match_log(True)

    def _on_click(self, r: int, c: int):
        if not self._can_click():
            return
        if self.net is not None and self.role != "local":
            # 联机：房主权威。客人把走子请求发给房主，房主落子后广播整盘快照。
            if self.net.is_host:
                if self.engine.play(r, c):
                    self._after_play()
                    self._broadcast_state()
            else:
                self._send_to_host({"k": "mv", "r": r, "c": c})
            return
        if not self.engine.play(r, c):
            return
        self._after_play()

    # ---------- 网络 ----------

    def _broadcast_state(self) -> None:
        """房主把整盘快照广播给房间里其他人。"""
        if self.net is None:
            return
        try:
            self.net.send_game({"k": "state", "s": self.engine.to_dict()})
        except Exception:                   # noqa: BLE001 — 网络断开不崩
            pass

    def _send_to_host(self, data: dict) -> None:
        """客人把请求单播给房主。"""
        if self.net is None:
            return
        try:
            self.net.send_game_to_host(data)
        except Exception:                   # noqa: BLE001
            pass

    def _on_net(self, msg) -> None:
        """收到房间里的玩法消息（来自其他设备）。"""
        if _ACTIVE is not self or self.net is None:
            return
        data = (msg or {}).get("data") or {}
        k = data.get("k")
        if k == "mv":
            # 房主收到客人的走子请求 → 落子后广播
            if not self.net.is_host:
                return
            if self.engine.play(int(data["r"]), int(data["c"])):
                self._after_play()
                self._broadcast_state()
        elif k == "state":
            state = data.get("s")
            if state:
                self.engine = GomokuEngine.from_dict(state)
                self._refresh()
        elif k == "req_state":
            if self.net.is_host:
                self._broadcast_state()
        elif k == "undo":
            self.engine.undo()
            self._refresh()
            if self.net.is_host:
                self._broadcast_state()
        elif k == "reset":
            self.engine.reset()
            self._refresh()
            if self.net.is_host:
                self._broadcast_state()
        # 任何网络事件后重算身份（可能有人入座 / 离座）
        self._compute_role()

    def apply_state(self, data: dict):
        """收到房主快照时调用（联机用）。"""
        self.engine = GomokuEngine.from_dict(data)
        self._refresh()

    # ---------- 历史记录 ----------

    def _save_match_log(self, finished: bool = True) -> None:
        """把这一局落盘（分出胜负 / 中途退出都留一份）。

        写到应用数据目录的 ``logs/gomoku/``（见 :mod:`core.history`）；
        主菜单的「游玩记录」页会把它和别的游戏的记录汇总在一起。

        联机时**只有房主**保存：房主才是权威方，两边都存会留下两份重复记录。
        """
        if self._log_saved:
            return
        if self.net is not None and not self.net.is_host:
            return
        s = self.engine.state
        if not s.moves:
            return
        self._log_saved = True

        if s.result == BLACK_WIN:
            win = t("gomoku.black", default="黑方")
        elif s.result == WHITE_WIN:
            win = t("gomoku.white", default="白方")
        elif s.result == DRAW:
            win = t("gomoku.draw", default="平局")
        else:
            win = "未分胜负"

        meta = {
            "状态": "正常结束" if finished else "中途结束",
            "胜方": win,
            "模式": self._identity_label(),
            "步数": str(len(s.moves)),
        }
        lines = []
        for i, mv in enumerate(s.moves):
            who = t("gomoku.black", default="黑方") if mv.stone == BLACK \
                else t("gomoku.white", default="白方")
            lines.append(f"{i + 1}. {who} ({mv.row + 1},{mv.col + 1})")
        try:
            from core import history
            history.save_match_log("gomoku", lines, meta)
        except Exception as exc:          # noqa: BLE001
            print(f"[gomoku] 保存历史记录失败：{exc!r}")

    # ---------- 工具栏 ----------

    def _undo(self, _e):
        if self.net is not None and self.role == "spectator":
            return
        if self.net is not None and not self.net.is_host:
            # 联机时房主权威：客人只提请求，等房主改完再同步回来
            self._send_to_host({"k": "undo"})
            return
        self.engine.undo()
        self._refresh()
        if self.net is not None:
            self._broadcast_state()

    def _restart(self, _e):
        if self.net is not None and not self.net.is_host:
            self._send_to_host({"k": "reset"})
            return
        self.engine.reset()
        self._log_saved = False           # 新的一局，重新允许落盘
        self._refresh()
        if self.net is not None:
            self._broadcast_state()

    # ---------- 组装 ----------

    def build(self) -> ft.Control:
        global _ACTIVE
        _ACTIVE = self
        self._refresh()
        if self.net is not None:
            # 接管房间里的玩法消息；先跟房主要一份当前局面（中途加入也能对上）
            try:
                self.net.set_game_handler(self._on_net)
                if not self.net.is_host:
                    self._send_to_host({"k": "req_state"})
            except Exception:               # noqa: BLE001
                pass
        board_panel = ft.Container(
            bgcolor=_BOARD_BG,
            border=ft.Border.all(2, _GRID_LINE),
            padding=ft.Padding.all(2),
            content=self.board_host,
        )
        side_items = [
            ft.Text(t("gomoku.mode", default="模式"), size=11,
                    color=T.TEXT_MUTED),
            ft.Text(self._identity_label(), size=13,
                    color=T.TEXT_PRIMARY),
            self.turn_text,
            self.status_text,
            ft.Button(
                content=ft.Text(t("gomoku.undo", default="悔棋")),
                on_click=self._undo,
            ),
            ft.Button(
                content=ft.Text(t("gomoku.restart", default="重开")),
                on_click=self._restart,
            ),
        ]
        if self._narrow:
            # 手机竖屏：信息横着放在棋盘下面，别把棋盘挤到屏幕外
            side = ft.Row(
                side_items, spacing=8, wrap=True, run_spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
            body = ft.Column(
                [board_panel, ft.Container(height=10), side],
                spacing=0,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                scroll=ft.ScrollMode.AUTO,
            )
        else:
            side = ft.Column(side_items, spacing=4)
            body = ft.Row(
                [board_panel, ft.Container(width=16), side],
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )

        def _back(_e):
            # 中途退出也留一份记录（还没分出胜负）
            self._save_match_log(False)
            self._detach()
            self.navigate("/g/gomoku")

        return ft.Column(
            [app_bar(t("route.gomoku.play", default="五子棋 · 对局"),
                     on_back=_back),
             page_padding(body)],
            expand=True,
        )

    def _detach(self) -> None:
        """离开对局页：摘掉网络回调，别让旧视图继续收消息。"""
        global _ACTIVE
        if _ACTIVE is self:
            _ACTIVE = None
        if self.net is not None:
            try:
                self.net.set_game_handler(None)
            except Exception:               # noqa: BLE001
                pass

    def _identity_label(self) -> str:
        return {
            "local": t("gomoku.mode_local", default="本地双人"),
            "black": t("gomoku.mode_black", default="联机 · 执黑"),
            "white": t("gomoku.mode_white", default="联机 · 执白"),
            "spectator": t("gomoku.mode_spectator", default="联机 · 观战"),
        }.get(self.role, "")


def build(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """入口：新建一页棋局并返回控件树。"""
    return _BoardPage(page, navigate).build()