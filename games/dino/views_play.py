# -*- coding: utf-8 -*-
"""对局页：小恐龙跑酷画面 + 键盘/触屏输入 + 主循环（自动加速）。

手机端怎么玩
------------
手机上没有键盘，所以这一页同时提供两套操作，走同一个 ``_act()``：

* **键盘（桌面）**：空格 / ↑ / W 跳跃；↓ / S 下蹲（按住）；P 暂停；R 重开；
* **触屏（手机）**：屏幕点击 / 下方「跳」键起跳；按住「蹲」键下蹲；
  直接在画面上**下滑**也能下蹲。

复古像素风：黑底 + 浅灰恐龙 + 绿色仙人掌 + 橙色飞鸟。恐龙与障碍只用少量
``Container`` 定位，性能开销很小。

为避免内存泄漏，离开页面时必须 ``_detach()``：取消 asyncio 任务、还原
``page.on_keyboard_event`` 与 ``page.on_resize``、停掉触屏按键的连发任务。
"""

from __future__ import annotations

import asyncio
from typing import Dict, Optional

import flet as ft

from core.i18n import t
from core.registry import NavigateFn
from core.theme import T
from core.ui_common import page_width

from .engine import (
    DINO_DUCK_H, DINO_STAND_H, DINO_W, DINO_X, GROUND_TOP, WORLD_H, WORLD_W, Dino,
)
from .views_layout import LayoutMixin
from .views_pad import TouchPad

# 复古配色
BG = "#0d0d0d"
GROUND = "#5a5a5a"
DINO = "#f2f2f2"
DINO_EYE = "#0d0d0d"
CACTUS = "#43a047"
BIRD = "#ff7043"

NARROW_W = 620         # 小于这个宽度按「手机竖屏」处理
INTERVAL = 0.03        # 主循环步进间隔（秒），与引擎 TICK_SECONDS 对齐


class _PlayPage(LayoutMixin):
    """一页对局：持有引擎、控件、循环任务。"""

    def __init__(self, page: ft.Page, navigate: NavigateFn):
        self.page = page
        self.navigate = navigate
        self._best = 0
        self.engine = Dino()
        self._task: Optional[asyncio.Task] = None
        self._prev_keyboard = None
        self._prev_resize = None
        self._log_saved = False
        self.scale = 6.0
        self._touch = False
        self._obstacle_ctrls: Dict[int, ft.Container] = {}
        self._drag_from: Optional[float] = None
        self._tap_handled = False        # 同一次点击 on_tap_up / on_tap 只跳一次

        # —— 舞台（画布）——
        self.ground_ctrl = ft.Container(bgcolor=GROUND)
        self.dino_eye = ft.Container(bgcolor=DINO_EYE)
        self.dino_ctrl = ft.Container(
            bgcolor=DINO,
            border_radius=2,
            content=self.dino_eye,
        )
        self.overlay_text = ft.Text("", size=18, weight=ft.FontWeight.BOLD,
                                   color=T.TEXT_PRIMARY, text_align=ft.TextAlign.CENTER)
        self.overlay = ft.Container(
            bgcolor=ft.Colors.with_opacity(0.55, "#000000"),
            alignment=ft.Alignment.CENTER,
            content=self.overlay_text,
            visible=False,
        )
        self.stack = ft.Stack(
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            controls=[self.ground_ctrl, self.dino_ctrl, self.overlay],
        )
        self.stage = ft.Container(
            bgcolor=BG,
            border=ft.Border.all(2, T.BORDER),
            border_radius=6,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=self.stack,
        )

        # —— 信息文字 ——
        self.score_text = ft.Text("0", size=18, weight=ft.FontWeight.BOLD,
                                 color=T.TEXT_PRIMARY)
        self.best_text = ft.Text("0", size=14, color=T.TEXT_SECONDARY)
        self.speed_text = ft.Text("1.0", size=14, color=T.ACCENT,
                                 weight=ft.FontWeight.BOLD)
        self.status_text = ft.Text("", size=12, color=T.DANGER)
        self.pause_label = ft.Text(t("dino.pause", default="暂停"),
                                  size=13, color=T.TEXT_PRIMARY)
        _pause_box = ft.Container(
            bgcolor=T.SURFACE_ALT, border=ft.Border.all(1, T.BORDER),
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            alignment=ft.Alignment.CENTER,
            content=ft.Row(
                [ft.Icon(ft.Icons.PAUSE, size=16, color=T.TEXT_PRIMARY),
                 self.pause_label],
                spacing=4, tight=True,
            ),
        )
        # 用 GestureDetector 而非 ft.Button：不可获得键盘焦点，方向键不会在
        # 按钮间跳、也不会误触按钮（只保留鼠标 / 触控与键盘 on_keyboard_event）
        self.pause_btn = ft.GestureDetector(
            content=_pause_box, on_tap=lambda _e: self._toggle_pause())
        self.pad = TouchPad(page, self._act)

    # ---------- 布局（在 views_layout 中调用） ----------

    def _apply_stage_size(self) -> None:
        s = self.scale
        sw = WORLD_W * s
        sh = WORLD_H * s
        self.stage.width = sw
        self.stage.height = sh
        self.stack.width = sw
        self.stack.height = sh
        self.ground_ctrl.width = sw
        self.ground_ctrl.top = GROUND_TOP * s
        self.ground_ctrl.height = (WORLD_H - GROUND_TOP) * s
        self.overlay.width = sw
        self.overlay.height = sh

    # ---------- 画面 ----------

    def _render(self) -> None:
        s = self.scale
        e = self.engine
        # 恐龙
        dh = DINO_DUCK_H if e.ducking else DINO_STAND_H
        self.dino_ctrl.left = DINO_X * s
        self.dino_ctrl.top = e.dino_top * s
        self.dino_ctrl.width = DINO_W * s
        self.dino_ctrl.height = dh * s
        # 眼睛（相对恐龙本体，靠右上）
        ew = self.dino_ctrl.width * 0.22
        eh = self.dino_ctrl.height * 0.22
        self.dino_eye.width = ew
        self.dino_eye.height = eh
        self.dino_eye.left = self.dino_ctrl.width * 0.5
        self.dino_eye.top = self.dino_ctrl.height * 0.16

        # 障碍（按对象 id 复用控件）
        live_ids = set()
        new_children = [self.ground_ctrl]
        for o in e.obstacles:
            oid = id(o)
            live_ids.add(oid)
            ctrl = self._obstacle_ctrls.get(oid)
            if ctrl is None:
                ctrl = ft.Container(border_radius=2)
                self._obstacle_ctrls[oid] = ctrl
            ctrl.bgcolor = BIRD if o.kind == "bird" else CACTUS
            ctrl.left = o.x * s
            ctrl.top = o.y * s
            ctrl.width = o.w * s
            ctrl.height = o.h * s
            new_children.append(ctrl)
        # 清理已消失的障碍控件
        for oid in list(self._obstacle_ctrls.keys()):
            if oid not in live_ids:
                del self._obstacle_ctrls[oid]
        new_children.append(self.dino_ctrl)
        new_children.append(self.overlay)
        self.stack.controls = new_children

        # 信息
        self.score_text.value = str(int(e.score))
        self.best_text.value = str(max(self._best, int(e.score)))
        self.speed_text.value = f"{e.speed:.1f}"
        if not e.started:
            self.status_text.value = ""
            self.overlay.visible = True
            self.overlay_text.value = t("dino.start_hint",
                                       default="空格 / 点击 开始")
            self.overlay_text.color = T.TEXT_PRIMARY
        elif not e.alive:
            self.status_text.value = t("dino.over", default="游戏结束")
            self.status_text.color = T.DANGER
            self.overlay.visible = True
            self.overlay_text.value = (
                t("dino.over", default="游戏结束")
                + f"\n{int(e.score)}  ·  {t('dino.restart_hint', default='R / 点击 重开')}")
            self.overlay_text.color = T.DANGER
        elif e.paused:
            self.status_text.value = t("dino.paused", default="已暂停")
            self.status_text.color = T.WARNING
            self.overlay.visible = True
            self.overlay_text.value = t("dino.paused", default="已暂停")
            self.overlay_text.color = T.WARNING
        else:
            self.status_text.value = ""
            self.overlay.visible = False
        self.pause_label.value = (t("dino.resume", default="继续")
                                  if e.paused else t("dino.pause", default="暂停"))

    def _refresh(self) -> None:
        self._render()
        self.page.update()

    # ---------- 输入 ----------

    _KEY_ALIAS = {
        "space": "jump",
        "arrowup": "jump", "up": "jump", "w": "jump",
        "arrowdown": "duck", "down": "duck", "s": "duck",
        "p": "pause",
        "r": "restart",
    }

    def _act(self, action: str) -> None:
        e = self.engine
        if action == "jump":
            if not e.alive:
                self._restart()
                return
            e.jump()
        elif action == "duck":
            e.request_duck(0.5)
        elif action == "duck_release":
            e.release_duck()
        elif action == "pause":
            e.toggle_pause()
        elif action == "restart":
            self._restart()
            return
        else:
            return
        self._refresh()

    def _on_key(self, e: ft.KeyboardEvent):
        # flet 把空格上报为 " "（单个空格），strip 后会变成空串，这里单独归一
        # 成 "space"，否则按空格根本无法开始游戏（启动提示里写的就是「空格」）。
        raw = (e.key or "").strip().lower()
        if raw == "" or raw == "spacebar":
            raw = "space"
        action = self._KEY_ALIAS.get(raw)
        if action:
            self._act(action)

    # ---------- 画面上手势（手机：下滑下蹲 / 点击跳跃） ----------

    @staticmethod
    def _tap_y(e) -> Optional[float]:
        """取 TapEvent 的局部 y 坐标。

        flet 的 :class:`TapEvent` 只有 ``local_position``（``Offset``，含 x/y），
        **没有** ``local_y`` 字段。早先按 ``local_y`` 读取恒为 None，导致点击
        手势被整段吞掉（空格能玩、鼠标点击没反应）。这里兼容两种写法。
        """
        pos = getattr(e, "local_position", None)
        if pos is not None:
            y = getattr(pos, "y", None)
            if y is not None:
                return float(y)
        y = getattr(e, "local_y", None)
        return float(y) if y is not None else None

    def _swipe_start(self, e):
        self._drag_from = self._tap_y(e)
        self._tap_handled = False

    def _swipe_end(self, e):
        start = self._drag_from
        self._drag_from = None
        y = self._tap_y(e)
        # 坐标拿不到时也不能吞掉点击：直接按「轻点」处理。
        if start is not None and y is not None and y - start > 18:
            self._act("duck")
        else:
            self._act("jump")
        self._tap_handled = True

    def _on_stage_tap(self, e):
        """点击兜底：万一 on_tap_up 因手势竞争没触发，仍要能跳。

        Flutter 的顺序是 tapDown → tapUp → onTap；_tap_handled 保证同一次
        点击只跳一次，同时下滑（tap 被取消）不会被误判成跳跃盖掉下蹲。
        """
        if self._tap_handled:
            self._tap_handled = False
            return
        self._act("jump")

    def _swipe_cancel(self, e):
        # 滑动被识别成拖拽时 tap 会取消：只清状态，不动作（下蹲另有触屏键）。
        self._drag_from = None

    # ---------- 主循环 ----------

    async def _loop(self):
        """每帧都重读 self.engine，所以重开换了新引擎后循环能立刻接着跑。

        关键：死亡时**不能 return**。早先在结束态直接退出任务，重开虽然换了
        新引擎却再也没人调用 step()，画面就一直静止（「重开什么也没发生」）。
        现在结束态只空转等待重开，日志靠 _log_saved 保证只落一次。
        """
        try:
            while True:
                await asyncio.sleep(INTERVAL)
                e = self.engine
                if not e.alive:
                    if not self._log_saved:
                        self._refresh()
                        self._save_match_log()
                    continue
                if not e.started or e.paused:
                    # 待开始 / 暂停：由输入事件的 _refresh 驱动刷新，不空转 update
                    continue
                e.step(1.0)
                self._render()
                if not e.alive:
                    self._refresh()
                    self._save_match_log()
                    continue
                self.page.update()
        except asyncio.CancelledError:
            raise
        except Exception:                   # noqa: BLE001 — 页面没了就收工
            return

    # ---------- 生命周期 ----------

    def _attach(self):
        self._prev_keyboard = self.page.on_keyboard_event
        self.page.on_keyboard_event = self._on_key
        try:
            self._prev_resize = self.page.on_resize
            self.page.on_resize = self._on_resize
        except Exception:                   # noqa: BLE001
            self._prev_resize = None
        try:
            self._task = self.page.run_task(self._loop)
        except Exception:                   # noqa: BLE001
            self._task = None

    def _on_resize(self, e):
        self._layout()
        self._apply_stage_size()
        self._refresh()

    def _detach(self):
        if self._task is not None:
            try:
                self._task.cancel()
            except Exception:               # noqa: BLE001
                pass
            self._task = None
        try:
            self.page.on_keyboard_event = self._prev_keyboard
        except Exception:  # noqa: BLE001
            pass
        try:
            self.page.on_resize = self._prev_resize
        except Exception:                   # noqa: BLE001
            pass
        self.pad.detach()

    def _restart(self, start: bool = True):
        """重开一局，默认**立即起跑**。

        若停在「待开始」界面，玩家还得再按一次空格，看起来就像重开没反应；
        所以死后按空格 / 点击 / R / 重开按钮，都直接换成一局正在跑的新引擎。
        主循环每帧重读 self.engine，下一帧就会接着 step。
        """
        self._best = max(self._best, int(self.engine.score))
        self.engine = Dino()
        self.engine.best = self._best
        if start:
            self.engine.start()
        self._log_saved = False
        self._obstacle_ctrls.clear()
        self._refresh()

    def _toggle_pause(self):
        self.engine.toggle_pause()
        self._refresh()

    # ---------- 历史记录 ----------

    def _save_match_log(self) -> None:
        if self._log_saved:
            return
        e = self.engine
        # 先标记再判分数：结束态主循环每帧都会走到这里，0 分不落盘时也要
        # 避免反复重试（重开时 _restart 会把标记重置）。
        self._log_saved = True
        if e.score <= 0:
            return
        self._best = max(self._best, int(e.score))
        meta = {
            "状态": "游戏结束",
            "分数": str(int(e.score)),
            "最高分": str(self._best),
            "速度": f"{e.speed:.2f}",
            "模式": "单人",
        }
        lines = [
            f"分数：{int(e.score)}",
            f"最高分：{self._best}",
            f"最终速度：{e.speed:.2f}",
            "结果：游戏结束",
        ]
        try:
            from core import history
            history.save_match_log("dino", lines, meta)
        except Exception as exc:          # noqa: BLE001
            print(f"[dino] 保存历史记录失败：{exc!r}")


def build(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    return _PlayPage(page, navigate).build()
