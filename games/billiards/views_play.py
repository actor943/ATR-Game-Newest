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
import math
import time
from typing import Optional, Tuple

import flet as ft

from core import registry
from core import responsive
from core.i18n import t
from core.registry import NavigateFn
from core.theme import T
from core.ui_common import app_bar, page_padding, tap_button

from .engine import (
    BilliardsEngine, FOUL_EIGHT_EARLY, FOUL_NO_CONTACT, FOUL_SCRATCH,
    FOUL_WRONG_BALL, FOUL_WRONG_FIRST, GROUP_SOLID, GROUP_STRIPE,
    PHASE_OVER, PHASE_SHOOT,
)
from .assets import TABLE_GREEN, TABLE_IMAGE_SIZE
from .physics import (
    BASE_H, BASE_W, FORCE_MAX_N, clamp_tip, force_to_power, power_to_force,
)
from .views_controls import AngleDial, PowerBar, SpinDial
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


# 球桌宽度上限：0.4.10 写死 BASE_W=760，宽屏上球桌永远只占半屏。
# 物理层 Table.scale 会把球半径 / 袋口 / 速度与摩擦一起等比缩放，
# 所以放大桌面不会改变玩法比例，只是画面铺满。
TABLE_MAX_W = 1200.0

# 宽屏（Mac 全屏 / 大显示器）：球桌 | 对局信息 | 出杆与发球，三列横向同排
WIDE_MIN_W = 1180.0
SIDE_W = 190.0
CONTROLS_W = 330.0
COL_GAP = 14.0
# 额外留白：宽屏 Row 不 wrap，宽度必须留余量，否则一行放不下就会溢出。
WIDE_SAFE = 32.0

# 球桌控件比物理台面大一圈（木质库边 + 袋口，见 views_table.build）：
# 贴图 1200×678、绿色台面 1087×565。算尺寸时必须把这一圈除掉，
# 否则手机上球桌右边会被裁掉、宽屏上三列会被挤出屏幕。
RAIL_W = TABLE_IMAGE_SIZE[0] / TABLE_GREEN[2]   # ≈1.104
RAIL_H = TABLE_IMAGE_SIZE[1] / TABLE_GREEN[3]   # ≈1.200


def _wide_layout(page: ft.Page) -> bool:
    """宽度够、且不是手机时，才把控制区挪到球桌右侧。"""
    w, _h = responsive.size(page)
    plat = str(getattr(page, "platform", "") or "").lower()
    return w >= WIDE_MIN_W and plat not in ("android", "ios")


def _table_size(page: ft.Page) -> Tuple[float, float]:
    """按页面**宽高一起**算球桌尺寸（球桌、球、袋口全都等比缩放）。

    * **宽屏**：球桌、信息栏、出杆 / 发球三列**横向同排**，右侧两列的
      宽度（``SIDE_W + CONTROLS_W``）连同留白一起从可用宽度里扣掉；
      控制区不再占下方一整行，高度里也不再预留 230px。用户明确要求
      「页面整体优先」，所以不为了保住球桌面积而把内容竖着堆到下面；
    * **其它尺寸**：沿用「球桌 + 右侧信息栏 / 下方控制区」的布局。

    ``avail_w/avail_h`` 是**控件**能占的空间，而物理台面只是贴图中间的
    绿色区 —— 球桌控件还要多出 ``RAIL_W/RAIL_H`` 倍的木质库边，所以先
    除掉这一圈再算台面宽高，免得手机上右边被裁、宽屏上三列溢出。
    """
    w, h = responsive.size(page)
    pad = 2 * getattr(T, "PADDING", 16)
    if _wide_layout(page):
        avail_w = max(280.0, w - pad - 16.0 - SIDE_W - CONTROLS_W
                      - 2 * COL_GAP - WIDE_SAFE)
        avail_h = max(220.0, h - 56.0 - pad - 24.0)
    else:
        # 窄屏自上而下：app 栏 + padding + 球桌 + 紧凑信息条 + 控制区。
        # 控制区已换成小号控件（转盘 78 / 力度条 94 / 击球点 78），
        # 390px 留白足够装下信息条 + 三行控制器 + 间隔，矮屏还能再压球桌。
        avail_w = max(240.0, w - pad - 16.0)
        avail_h = max(100.0, h - 56.0 - pad - 390.0)
        if avail_w >= 660.0 + 210.0:
            avail_w -= 210.0               # 留出右侧信息栏
    table_w = min(avail_w / RAIL_W,
                  (avail_h / RAIL_H) * BASE_W / BASE_H,
                  TABLE_MAX_W)
    table_w = max(200.0, table_w)     # 下限别反过来把库边顶出屏幕
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

        # ----- 外接控制器：角度转盘 + 力度条 + 击球点圆盘 -----
        # 手机端不用去戳白球也能精准瞄准；桌面端作为「拉弓」之外的补充。
        self._aim_angle = 0.0                   # 弧度，y 轴向下
        self._force_n = power_to_force(0.4)     # 默认 40% 力度（80 / 200 牛）
        self._top = 0.0                         # 高低杆：-1 低杆 ~ +1 高杆
        self._side = 0.0                        # 加塞：-1 左塞 ~ +1 右塞
        # 手机（窄屏）从一开始就造小号控制器，避免信息栏 + 控制区竖着
        # 堆起来超过一屏。尺寸只在建页时选一次：手机永远窄、桌面永远宽，
        # 用户拖窗口只换外层排版，不动物理与棋局。
        self.compact = not _wide_layout(page)
        # 矮屏（<=700）再用小一档，保证 320×568 也不越界；高屏给手指
        # 留出更大的点击面积，反正下面还有富余空间。
        self.tiny = self.compact and responsive.size(page)[1] < 700.0
        dial_size = 72.0 if self.tiny else (88.0 if self.compact else 110.0)
        power_size = ((30.0, 86.0) if self.tiny else
                      ((36.0, 108.0) if self.compact else (40.0, 132.0)))
        self.dial = AngleDial(size=dial_size,
                              on_change=self._on_dial_change)
        self.powerbar = PowerBar(width=power_size[0], height=power_size[1],
                                 max_n=FORCE_MAX_N,
                                 on_change=self._on_power_change)
        self.spin_dial = SpinDial(size=dial_size,
                                  on_change=self._on_spin_change)
        self.force_text = ft.Text("", size=13, color=T.TEXT_PRIMARY,
                                  weight=ft.FontWeight.BOLD)
        self.angle_text = ft.Text("", size=11, color=T.TEXT_SECONDARY)
        self.spin_text = ft.Text("", size=11, color=T.ACCENT,
                                 weight=ft.FontWeight.BOLD,
                                 text_align=ft.TextAlign.CENTER)
        self.control_hint = ft.Text("", size=11, color=T.TEXT_MUTED,
                                    text_align=ft.TextAlign.CENTER)
        # 力度数值输入：0~200 牛，和力度条双向同步（敲数字就能精确出力）
        self.force_input = ft.TextField(
            value=f"{self._force_n:.0f}",
            width=88, height=36, text_size=13,
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.NumbersOnlyInputFilter(),
            text_align=ft.TextAlign.CENTER,
            hint_text=f"0-{int(FORCE_MAX_N)}",
            content_padding=ft.Padding.symmetric(horizontal=6, vertical=4),
            on_change=self._on_force_typed,
            on_submit=self._on_force_typed,
        )
        # 宽 / 窄布局切换：只换外层容器，复用球桌、信息栏、控制器，
        # resize 时不会重建棋局 / 球 / 输入内容
        self._panels = None
        self._wide_mode = None
        self._layout_host = None

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
        # 轮到本机时，把转盘/力度条的当前值反映到球桌瞄准线上
        self._update_aim_preview()

    # ============================================================
    # 外接控制器：角度转盘 + 力度条（牛顿）
    # ============================================================

    def _on_dial_change(self, angle: float) -> None:
        """转盘转了：更新方向并实时刷新球桌瞄准线。"""
        self._aim_angle = float(angle)
        self._update_aim_preview()
        self._render_controls_text()
        self.page.update()

    def _on_power_change(self, force_n: float) -> None:
        """力度条拖了：刷新力度数值与瞄准线长度，并同步输入框。"""
        self._force_n = float(force_n)
        self.force_input.value = f"{self._force_n:.0f}"
        self._render_power(force_to_power(self._force_n))
        self._update_aim_preview()
        self._render_controls_text()
        self.page.update()

    def _on_force_typed(self, _e=None) -> None:
        """输入框敲了力度（0~200 牛）：截断到合法区间，同步力度条与瞄准线。"""
        raw = (self.force_input.value or "").strip()
        if not raw:
            return                          # 清空时不改力度，避免误触出杆
        try:
            parsed = float(raw)
        except (TypeError, ValueError):
            return
        n = max(0.0, min(FORCE_MAX_N, parsed))
        if n != parsed:
            self.force_input.value = f"{n:.0f}"
        self._force_n = n
        self.powerbar.set_force(n)
        self._render_power(force_to_power(n))
        self._update_aim_preview()
        self._render_controls_text()
        self.page.update()

    # ---------- 杆法：高低杆 / 加塞 ----------

    @staticmethod
    def _tip_label(top: float, side: float) -> str:
        """把 (top, side) 说成人话，例如「高杆 · 右塞」。

        静态方法的理由：历史记录里存的是每一杆当时的击球点，不能拿
        当前 UI 上选中的值去解释。
        """
        parts = []
        if top > 0.15:
            parts.append(t("billiards.tip_follow"))
        elif top < -0.15:
            parts.append(t("billiards.tip_draw"))
        if side > 0.15:
            parts.append(t("billiards.tip_right"))
        elif side < -0.15:
            parts.append(t("billiards.tip_left"))
        return " · ".join(parts) if parts else t("billiards.tip_neutral")

    def _spin_label(self) -> str:
        return self._tip_label(self._top, self._side)

    def _set_spin(self, top: float, side: float) -> None:
        """程序设定杆法（预设按钮 / 出杆后归中）：同步圆盘、读数、球桌。"""
        self._top, self._side = clamp_tip(top, side)
        self.spin_dial.set_spin(self._top, self._side)
        self._render_controls_text()
        self._update_aim_preview()

    def _on_spin_change(self, top: float, side: float) -> None:
        """玩家在击球点圆盘上拖了红点。"""
        self._top, self._side = clamp_tip(top, side)
        self._render_controls_text()
        self._update_aim_preview()
        self.page.update()

    def _preset_spin(self, top: float, side: float, _e=None) -> None:
        """快捷杆法按钮：中 / 高 / 低 / 左 / 右。"""
        self._set_spin(top, side)
        self.page.update()

    def _reset_spin(self) -> None:
        """出杆后回到中杆：杆法是每一杆的战术选择，不留到下一杆。"""
        self._set_spin(0.0, 0.0)
        self.page.update()

    def _update_aim_preview(self) -> None:
        """把转盘角度 + 力度条 + 杆法画成球桌上的瞄准线。

        瞄准线的颜色随杆法变（中杆白 / 高杆暖 / 低杆冷 / 加塞紫），
        母球上的小红点给出这杆的走位方向。
        """
        dx = math.cos(self._aim_angle)
        dy = math.sin(self._aim_angle)
        self.table_view.set_tip(self._top, self._side, dx, dy)
        cue = self.engine.cue
        if cue is None or not self._may_act() or self.engine.ball_in_hand:
            self.table_view.clear_aim()
            return
        power = force_to_power(self._force_n)
        self.table_view.set_aim(cue.x, cue.y, dx, dy, power)

    def _render_controls_text(self) -> None:
        """力度（牛）、角度（度）、杆法的实时读数。"""
        self.force_text.value = "{n:.0f} N".format(n=self._force_n)
        deg = math.degrees(self._aim_angle) % 360
        self.angle_text.value = t("billiards.angle_deg", deg=deg)
        self.spin_text.value = t("billiards.spin_readout",
                                 v=self._spin_label())
        if not self._may_act():
            self.control_hint.value = t("billiards.hint_wait")
        elif self.engine.ball_in_hand:
            self.control_hint.value = t("billiards.hint_place")
        else:
            self.control_hint.value = t("billiards.control_hint")

    def _shoot_from_controls(self, _e=None) -> None:
        """按转盘角度 + 力度条 + 击球点出杆（手机端主操作）。"""
        if not self._may_act() or self.engine.ball_in_hand:
            return
        power = force_to_power(self._force_n)
        if power < 0.06:
            return
        dx = math.cos(self._aim_angle)
        dy = math.sin(self._aim_angle)
        self._shoot(dx, dy, power, self._top, self._side)
        self._reset_spin()

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
            tip = shot.get("tip") or [0.0, 0.0]
            try:
                label = self._tip_label(float(tip[0]), float(tip[1]))
            except (TypeError, ValueError, IndexError):
                label = t("billiards.tip_neutral")
            if label != t("billiards.tip_neutral"):
                text += " 杆法 " + label
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

    def _compose(self, wide: bool) -> ft.Control:
        """把同一批控件排成三列（宽屏）或上下两行（窄屏）。

        宽屏用 ``ft.Row`` 且**不 wrap**：球桌、信息栏、出杆 / 发球必须
        横向同排，绝不能因为宽度刚好卡住，就把右侧内容换到球桌下面。
        三列复用同一批控件，切换布局时不重建棋局 / 球 / 输入内容。
        """
        table_panel, side, side_compact, controls = self._panels
        if wide:
            return ft.Row(
                [table_panel, ft.Container(width=COL_GAP), side,
                 ft.Container(width=COL_GAP),
                 ft.Container(content=controls, width=CONTROLS_W)],
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )
        # 窄屏：信息栏换成两行的紧凑条（去掉力度条 / 模式标题 / 长提示），
        # 力矩和出杆按钮本来就在下面的控制区，不必重复占一整列高度。
        return ft.Column(
            [table_panel, ft.Container(height=6), side_compact,
             ft.Container(height=6), controls],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _on_resize(self, _w, _h) -> None:
        """窗口由窄变宽（或反过来）时只换外层布局，棋局状态不动。"""
        if self._layout_host is None or self._panels is None:
            return
        wide = _wide_layout(self.page)
        if wide == self._wide_mode:
            return
        self._wide_mode = wide
        self._layout_host.content = self._compose(wide)
        self._layout_host.expand = bool(wide)
        self._layout_host.alignment = (ft.Alignment.CENTER if wide
                                       else ft.Alignment.TOP_LEFT)
        self.page.update()

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
        # 球画在 Stack 里，桌子建好之后再补一次（sync 会把球加进去）；
        # 瞄准线 / 杆法红点也要等 Stack 建好才能画，这里补一次刷新。
        self.table_view.sync()
        self._update_aim_preview()

        # 外接控制器：角度转盘 + 力度条 + 击球点圆盘 + 读数 + 击球按钮。
        # 拆成三行短 Row（每行都窄于 CONTROLS_W），宽屏第三列不会被挤到
        # 球桌下方；窄屏整块落在球桌下面，一屏也放得下。
        self._render_power(force_to_power(self._force_n))
        self._render_controls_text()

        top_row = ft.Row(
            [
                ft.Column(
                    [ft.Text(t("billiards.angle"), size=11,
                             color=T.TEXT_MUTED), self.dial.control],
                    spacing=4,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(width=8),
                ft.Column(
                    [ft.Text(t("billiards.force"), size=11,
                             color=T.TEXT_MUTED), self.powerbar.control],
                    spacing=4,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(width=8),
                ft.Column(
                    [ft.Text(t("billiards.spin"), size=11,
                             color=T.TEXT_MUTED), self.spin_dial.control,
                     self.spin_text],
                    spacing=4,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.START,
            wrap=True, run_spacing=8,
        )
        mid_row = ft.Row(
            [
                ft.Column(
                    [ft.Text(t("billiards.force_input"), size=10,
                             color=T.TEXT_MUTED), self.force_input,
                     self.force_text, self.angle_text],
                    spacing=2,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(width=10),
                ft.Button(content=ft.Text(t("billiards.shoot"), size=14),
                          width=110, height=42,
                          on_click=self._shoot_from_controls),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            wrap=True, run_spacing=6,
        )
        # 矮屏按钮保持 54px 宽（5 个刚好塞进 320px），高屏可以放大一点
        pw, ph = ((58, 32) if (self.compact and not self.tiny) else (54, 28))
        presets = ft.Row(
            [
                tap_button(t("billiards.tip_center"),
                           lambda _e, a=0.0, s=0.0: self._preset_spin(a, s),
                           width=pw, height=ph, size=10),
                tap_button(t("billiards.tip_follow"),
                           lambda _e, a=0.85, s=0.0: self._preset_spin(a, s),
                           width=pw, height=ph, size=10),
                tap_button(t("billiards.tip_draw"),
                           lambda _e, a=-0.85, s=0.0: self._preset_spin(a, s),
                           width=pw, height=ph, size=10),
                tap_button(t("billiards.tip_left"),
                           lambda _e, a=0.0, s=-0.85: self._preset_spin(a, s),
                           width=pw, height=ph, size=10),
                tap_button(t("billiards.tip_right"),
                           lambda _e, a=0.0, s=0.85: self._preset_spin(a, s),
                           width=pw, height=ph, size=10),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=4, wrap=True, run_spacing=4,
        )
        controls_panel = ft.Column(
            [top_row, mid_row, presets, self.control_hint],
            spacing=4 if self.compact else 8,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # 窄屏信息条：只留「轮到谁 + 重开」「两人剩球」「状态」三行。
        # 原来的模式标题 / 力度条 / 长提示 / 大按钮在手机上纯占高度，
        # 力度已经在控制区有输入框和按钮，重开改成小按钮即可。
        restart_small = ft.Button(
            content=ft.Text(t("billiards.restart"), size=11),
            width=74, height=30, on_click=self._reset,
        )
        side_compact = ft.Column(
            [
                ft.Row(
                    [self.turn_text, restart_small],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    [ft.Column([self.p1_text], spacing=0, expand=1),
                     ft.Column([self.p2_text], spacing=0, expand=1)],
                    spacing=8,
                ),
                self.status_text,
            ],
            spacing=1,
        )

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
            width=SIDE_W,
        )

        self._panels = (table_panel, side, side_compact, controls_panel)
        self._wide_mode = _wide_layout(self.page)
        padded = page_padding(self._compose(self._wide_mode))
        self._layout_host = padded
        if self._wide_mode:
            # 三列整体在页面里居中；内容区撑满剩余高度，页面才整齐
            padded.expand = True
            padded.alignment = ft.Alignment.CENTER

        def _back(_e):
            self._save_match_log(False)
            self._detach()
            # 联机对局：返回房间大厅（不要直接退到单人台球）
            if self.net is not None:
                self.navigate("/room")
            else:
                self.navigate("/g/billiards")

        return ft.Column(
            [app_bar(t("route.billiards.play", default="台球 · 对局"),
                     on_back=_back),
             padded],
            expand=True,
        )

    def _attach(self) -> None:
        """起主循环（用 page.run_task：它跑在 flet 自己的事件循环上）。"""
        # 走全局 resize 分发器：窗口拉宽 / 缩窄时原地换三列 / 上下布局，
        # 不覆盖框架或其它页面的回调（见 core/responsive.py）
        responsive.subscribe(self.page, "billiards.play", self._on_resize)
        try:
            self._task = self.page.run_task(self._loop)
        except Exception:                   # noqa: BLE001
            self._task = None

    def _detach(self) -> None:
        """离开对局页：停循环、摘 resize 订阅与网络回调。"""
        self._attached = False
        responsive.unsubscribe(self.page, "billiards.play", self._on_resize)
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
