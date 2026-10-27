# -*- coding: utf-8 -*-
"""台球对局页：球桌、主循环、画面、落盘。

三种玩法共用一套画面
--------------------
* **本地双人**：同一台设备上两个人轮流打，轮到谁谁拖白球。
* **联机**：房间里席位 0 / 1 分别是 1 号 / 2 号选手，其余观战。
  房主权威 —— 客人把击球请求发给房主，房主校验「是不是轮到你」，
  通过后自己开杆，并把这一杆（方向 + 力度）广播给所有人。
* **观战**：看得见，不能打。

文件怎么分
----------
* :mod:`games.billiards.views_table` —— 球桌画面（绝对定位的球 + 手势层）
* :mod:`games.billiards.views_gesture` —— 拖拽手势（拉弓瞄准 / 摆白球）
* :mod:`games.billiards.views_net` —— 联机同步（身份 / 请求 / 快照）
* 本文件 —— 组装、主循环、界面、落盘

主循环
------
物理按**真实帧间隔**推进（``time.monotonic()`` 差值），掉帧时也不会
一次跳太远；球停稳后交给规则引擎判这一杆。
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional, Tuple

import flet as ft

from core import registry
from core.i18n import t
from core.registry import NavigateFn
from core.theme import T
from core.ui_common import app_bar, page_padding

from .engine import (
    BilliardsEngine, FOUL_EIGHT_EARLY, FOUL_NO_CONTACT, FOUL_SCRATCH,
    FOUL_WRONG_BALL, FOUL_WRONG_FIRST, GROUP_SOLID, GROUP_STRIPE,
    PHASE_OVER, PHASE_SHOOT,
)
from .physics import BASE_H, BASE_W
from .views_gesture import PlayGestureMixin
from .views_net import PlayNetMixin
from .views_table import TableView

GAME_ID = "billiards"

# 犯规代码 → 文案键
_FOUL_KEYS = {
    FOUL_SCRATCH: "billiards.foul_scratch",
    FOUL_NO_CONTACT: "billiards.foul_no_contact",
    FOUL_WRONG_FIRST: "billiards.foul_wrong_first",
    FOUL_WRONG_BALL: "billiards.foul_wrong_ball",
    FOUL_EIGHT_EARLY: "billiards.foul_eight_early",
}


def _session():
    """当前房间会话；``None`` 表示本地双人。"""
    try:
        from core.net import session as S
        return S.current()
    except Exception:                       # noqa: BLE001 — 纯本地环境
        return None


def _table_size(page: ft.Page) -> Tuple[float, float]:
    """按页面宽度算球桌尺寸（球桌、球、袋口全都等比缩放）。

    宽屏时右侧留一条信息栏；窄屏（手机）时信息栏换到下面。
    """
    avail = 0.0
    try:
        if page.width:
            avail = float(page.width) - 32.0
    except Exception:                       # noqa: BLE001
        avail = 0.0
    if avail <= 0:
        avail = BASE_W
    if avail >= 660:
        table_w = min(BASE_W, avail - 210)     # 留出右侧信息栏
    else:
        table_w = min(BASE_W, avail)
    table_w = max(280.0, table_w)
    return table_w, table_w * BASE_H / BASE_W


class _PlayPage(PlayNetMixin, PlayGestureMixin):
    """一页对局：持有引擎、控件、本机身份、循环任务。"""

    def __init__(self, page: ft.Page, navigate: NavigateFn):
        self.page = page
        self.navigate = navigate
        self.net = _session()                    # None = 本地双人
        self.players = registry.game_players(GAME_ID)
        self.role = "local"                      # local/p0/p1/spectator
        self._compute_role()

        w, h = _table_size(page)
        self.engine = BilliardsEngine(w, h)
        self.table_view = TableView(self.engine, self._on_pan_start,
                                    self._on_pan_update, self._on_pan_end)
        self._task: Optional[asyncio.Task] = None
        self._drag: Optional[str] = None          # "aim" / "place"
        self._aim: Optional[Tuple[float, float, float]] = None
        self._pending_state: Optional[dict] = None
        self._log_saved = False                   # 这一局是否已经落过盘
        self._attached = False                    # 对局页是否还开着

        self.mode_text = ft.Text("", size=12, color=T.TEXT_SECONDARY)
        self.turn_text = ft.Text("", size=15, color=T.TEXT_PRIMARY,
                                 weight=ft.FontWeight.BOLD)
        self.p1_text = ft.Text("", size=12, color=T.TEXT_SECONDARY)
        self.p2_text = ft.Text("", size=12, color=T.TEXT_SECONDARY)
        self.status_text = ft.Text("", size=12, color=T.ACCENT)
        self.hint_text = ft.Text("", size=11, color=T.TEXT_MUTED)
        self.power_fill = ft.Container(width=0, height=8, bgcolor=T.ACCENT,
                                       border_radius=4)
        self.power_bar = ft.Container(
            width=120, height=8, bgcolor=T.SURFACE_ALT, border_radius=4,
            content=self.power_fill,
        )

    # ============================================================
    # 主循环
    # ============================================================

    async def _loop(self) -> None:
        """物理主循环：按真实帧间隔推进，球停了就交给规则引擎。"""
        last = time.monotonic()
        while True:
            try:
                now = time.monotonic()
                dt = now - last
                last = now
                dt = max(0.001, min(0.05, dt))     # 掉帧时不要一次跳太远
                if self.engine.phase == PHASE_SHOOT:
                    done = self.engine.advance(dt)
                    self.table_view.sync()
                    self._render_side()
                    self.page.update()
                    if done:
                        self._after_shot()
                elif self._pending_state is not None:
                    # 本地物理停稳后，再对齐房主的权威快照
                    self._apply_state(self._pending_state)
                    self._pending_state = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:             # noqa: BLE001 — 循环不能死
                print(f"[billiards] 主循环出错：{exc!r}")
            await asyncio.sleep(1 / 60)

    def _after_shot(self) -> None:
        """一杆结束：房主判规则并广播快照。"""
        if self.net is not None and self.net.is_host:
            self._broadcast_state()
        self._render_side()
        self.page.update()

    # ============================================================
    # 界面
    # ============================================================

    def _render_power(self, power: float) -> None:
        """力度条。"""
        self.power_fill.width = max(0.0, min(120.0, power * 120.0))

    def _foul_text(self, code: str) -> str:
        """犯规代码 → 一句话说明。"""
        key = _FOUL_KEYS.get(code, "")
        if not key:
            return ""
        return t(key, default=code)

    def _status_text(self) -> str:
        """当前状态的一句话说明。"""
        e = self.engine
        if e.phase == PHASE_OVER:
            if e.result is None:
                return ""
            who = (t("billiards.player1") if e.result == 0
                   else t("billiards.player2"))
            text = t("billiards.win", who=who)
            extra = " · ".join(x for x in (self._foul_text(c)
                                           for c in e.fouls) if x)
            if extra:
                text = f"{text}（{extra}）"
            return text
        if e.ball_in_hand:
            return t("billiards.free_ball")
        if e.message == "continue":
            return t("billiards.continue")
        if e.message and e.message != "turn":
            parts = [x for x in (self._foul_text(c)
                                 for c in e.message.split(",")) if x]
            if parts:
                return " · ".join(parts)
        if e.cleared(e.turn):
            return t("billiards.eight_next")
        return ""

    def _group_label(self, player: int) -> str:
        """某位选手的花色。"""
        g = self.engine.groups[player]
        if g == GROUP_SOLID:
            return t("billiards.group_solid")
        if g == GROUP_STRIPE:
            return t("billiards.group_stripe")
        return t("billiards.group_none")

    def _left_text(self, player: int) -> str:
        """该选手桌上还剩几颗自己的球（还没定花色就显示「—」）。"""
        g = self.engine.groups[player]
        if g is None:
            return "—"
        return str(self.engine.on_table(g))

    def _render_side(self) -> None:
        """右侧信息栏。"""
        e = self.engine
        self.mode_text.value = self._identity_label()
        if e.phase == PHASE_OVER:
            who = (t("billiards.player1") if e.result == 0
                   else t("billiards.player2"))
            self.turn_text.value = t("billiards.win", who=who)
        else:
            who = (t("billiards.player1") if e.turn == 0
                   else t("billiards.player2"))
            self.turn_text.value = t("billiards.turn", who=who)
        self.p1_text.value = "{n}：{g}（剩 {left}）".format(
            n=t("billiards.player1"), g=self._group_label(0),
            left=self._left_text(0))
        self.p2_text.value = "{n}：{g}（剩 {left}）".format(
            n=t("billiards.player2"), g=self._group_label(1),
            left=self._left_text(1))
        self.status_text.value = self._status_text()
        if e.ball_in_hand and self._may_act():
            self.hint_text.value = t("billiards.hint_place")
        elif self._may_act():
            self.hint_text.value = t("billiards.hint_shoot")
        else:
            self.hint_text.value = t("billiards.hint_wait")

    def _identity_label(self) -> str:
        """本机身份的一句话。"""
        return {
            "local": t("billiards.mode_local"),
            "p0": t("billiards.mode_p0"),
            "p1": t("billiards.mode_p1"),
            "spectator": t("billiards.mode_spectator"),
        }.get(self.role, "")

    # ============================================================
    # 动作
    # ============================================================

    def _engine_reset(self) -> None:
        """重开一局（本地直接重置）。"""
        self.engine.reset()
        self._log_saved = False
        self.table_view.sync()
        self._render_side()
        self.page.update()

    def _reset(self, _e=None) -> None:
        """点「重开」：联机时只有房主说了算。"""
        if self.net is None:
            self._engine_reset()
        elif self.net.is_host:
            self._engine_reset()
            self._broadcast_state()
        else:
            self._send_to_host({"k": "req_reset", "from": self._my_mid()})

    # ============================================================
    # 历史记录
    # ============================================================

    def _save_match_log(self, finished: bool = True) -> None:
        """把这一局落盘（写到 ``logs/billiards/``）。

        联机时**只有房主**保存：房主才是权威方，两边都存会留下两份。
        """
        if self._log_saved:
            return
        if self.net is not None and not self.net.is_host:
            return
        if not self.engine.shots:
            return
        self._log_saved = True
        e = self.engine
        if e.result is None:
            result = t("billiards.no_result")
        elif e.result == 0:
            result = t("billiards.player1")
        else:
            result = t("billiards.player2")
        meta = {
            "状态": "正常结束" if finished else "中途结束",
            "结果": result,
            "模式": self._identity_label(),
            "杆数": str(len(e.shots)),
            "进球": str(len(e.potted)),
        }
        lines = []
        for i, shot in enumerate(e.shots):
            who = t("billiards.player1") if shot.get("player") == 0 \
                else t("billiards.player2")
            potted = shot.get("potted") or []
            fouls = shot.get("fouls") or []
            text = f"{i + 1}. {who}"
            if potted:
                text += " 进球 " + " ".join(str(n) for n in potted)
            if fouls:
                text += " 犯规 " + ",".join(fouls)
            lines.append(text)
        try:
            from core import history
            history.save_match_log(GAME_ID, lines, meta)
        except Exception as exc:              # noqa: BLE001
            print(f"[billiards] 保存历史记录失败：{exc!r}")

    # ============================================================
    # 组装与生命周期
    # ============================================================

    def build(self) -> ft.Control:
        """搭出对局页（球桌 + 右侧信息栏）。"""
        self._attached = True
        self.table_view.sync()
        self._render_side()
        self._attach()
        if self.net is not None:
            try:
                self.net.set_game_handler(self._on_net)
                if not self.net.is_host:
                    self._send_to_host({"k": "req_state"})
            except Exception:               # noqa: BLE001
                pass

        table_panel = self.table_view.build()
        # 球画在 Stack 里，桌子建好之后再补一次（sync 会把球加进去）
        self.table_view.sync()

        side = ft.Column(
            [
                ft.Text(t("billiards.mode"), size=11, color=T.TEXT_MUTED),
                self.mode_text,
                ft.Container(height=6),
                self.turn_text,
                self.p1_text,
                self.p2_text,
                ft.Container(height=8),
                self.status_text,
                ft.Container(height=8),
                ft.Text(t("billiards.power"), size=11, color=T.TEXT_MUTED),
                self.power_bar,
                ft.Container(height=8),
                self.hint_text,
                ft.Container(height=10),
                ft.Button(content=ft.Text(t("billiards.restart")),
                          on_click=self._reset),
            ],
            spacing=3,
            width=190,
        )

        body = ft.Row(
            [table_panel, ft.Container(width=14), side],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.START,
            wrap=True,
            run_spacing=10,
        )

        def _back(_e):
            self._save_match_log(False)
            self._detach()
            self.navigate("/g/billiards")

        return ft.Column(
            [app_bar(t("route.billiards.play", default="台球 · 对局"),
                     on_back=_back),
             page_padding(body)],
            expand=True,
        )

    def _attach(self) -> None:
        """起主循环（用 page.run_task：它跑在 flet 自己的事件循环上）。"""
        try:
            self._task = self.page.run_task(self._loop)
        except Exception:                   # noqa: BLE001
            self._task = None

    def _detach(self) -> None:
        """离开对局页：停循环、摘网络回调。"""
        self._attached = False
        if self._task is not None:
            try:
                self._task.cancel()
            except Exception:               # noqa: BLE001
                pass
            self._task = None
        if self.net is not None:
            try:
                self.net.set_game_handler(None)
            except Exception:               # noqa: BLE001
                pass


def build(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """入口：新建一页对局并返回控件树。"""
    return _PlayPage(page, navigate).build()
