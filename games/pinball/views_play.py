# -*- coding: utf-8 -*-
"""弹球机对局页：键盘 / 触屏输入 + 60FPS 物理主循环 + 落盘。

操作
----
* **键盘**：``←/A``、``→/D`` 拍两片挡板，``空格`` 蓄力（蓄满自动发射，
  也可再按一次提前松手），``P`` 暂停，``R`` 重开；
* **触屏**：底部「左挡板 / 发射 / 右挡板 / 暂停」四个键，前三个按住有效，
  发射键按住蓄力、松手弹射。

键盘事件只有「按下」没有「抬起」（flet 的 ``KeyboardEvent`` 不带类型），
所以键盘挡板是 0.24 秒的**脉冲**；触屏按住给 3 秒上限，即便松手事件
丢了也会自动落下，不会卡在抬起状态。

离开页面必须 ``_detach()``：取消主循环任务、还原键盘回调、注销 resize
订阅、放下挡板。
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

import flet as ft

from core import responsive
from core.i18n import t
from core.registry import NavigateFn
from core.theme import T

from .engine import OVER, PinballEngine
from .views_board import TableView
from .views_layout import LayoutMixin
from .views_pad import TouchPad

KEYBOARD_PULSE = 0.24          # 键盘拍一下挡板持续多久（秒）
TOUCH_HOLD = 3.0               # 触屏按住的最长时限（秒）
NARROW_W = 620                 # 小于这个宽度按「手机竖屏」处理


class _PlayPage(LayoutMixin):
    """一页对局：持有引擎、台面控件、主循环任务。"""

    def __init__(self, page: ft.Page, navigate: NavigateFn):
        self.page = page
        self.navigate = navigate
        self.engine = PinballEngine()
        self.table = TableView(self.engine)
        self._task: Optional[asyncio.Task] = None
        self._prev_keyboard = None
        self._log_saved = False
        self._attached = False
        self._touch = False
        self.scale = 1.0
        self._left_until = 0.0
        self._right_until = 0.0

        # ---- 信息文字 ----
        self.score_text = ft.Text("0", size=20, weight=ft.FontWeight.BOLD,
                                  color=T.ACCENT)
        self.best_text = ft.Text("0", size=14, color=T.TEXT_SECONDARY)
        self.balls_text = ft.Text("●●●", size=16, color=T.DANGER,
                                  weight=ft.FontWeight.BOLD)
        self.status_text = ft.Text("", size=12, color=T.TEXT_SECONDARY)
        self.message_text = ft.Text("", size=13, color=T.SUCCESS,
                                    weight=ft.FontWeight.BOLD)
        self.pause_label = ft.Text(t("pinball.pause", default="暂停"),
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
        self.pause_btn = ft.GestureDetector(
            content=_pause_box, on_tap=lambda _e: self._act("pause"))
        self.pad = TouchPad(page, self._act)

    # ---------- 画面 ----------

    def _render_side(self) -> None:
        """刷新分数 / 剩余球 / 状态 / 短暂提示。"""
        s = self.engine.state
        self.score_text.value = str(s.score)
        self.best_text.value = str(max(s.best, s.score))
        self.balls_text.value = "●" * s.balls if s.balls else "—"
        if s.status == OVER:
            self.status_text.value = t("pinball.over", default="游戏结束")
            self.status_text.color = T.DANGER
        elif s.paused:
            self.status_text.value = t("pinball.paused", default="已暂停")
            self.status_text.color = T.WARNING
        elif s.waiting:
            self.status_text.value = t("pinball.waiting", default="待发射")
            self.status_text.color = T.TEXT_SECONDARY
        else:
            self.status_text.value = t("pinball.playing", default="进行中")
            self.status_text.color = T.SUCCESS
        self.message_text.value = s.message if s.message_ttl > 0 else ""
        self.pause_label.value = (t("pinball.resume", default="继续")
                                  if s.paused
                                  else t("pinball.pause", default="暂停"))

    def _refresh(self) -> None:
        self.table.sync()
        self._render_side()
        self.page.update()

    # ---------- 输入 ----------

    _KEY_ALIAS = {
        "arrowleft": "left_pulse", "a": "left_pulse",
        "arrowright": "right_pulse", "d": "right_pulse",
        "space": "plunge_down", "p": "pause", "r": "restart",
    }

    def _act(self, action: str) -> None:
        """键盘 / 触屏按键统一入口。"""
        now = time.monotonic()
        if action == "left_down":
            self._left_until = now + TOUCH_HOLD
        elif action == "left_up":
            self._left_until = 0.0
        elif action == "right_down":
            self._right_until = now + TOUCH_HOLD
        elif action == "right_up":
            self._right_until = 0.0
        elif action == "left_pulse":
            self._left_until = now + KEYBOARD_PULSE
        elif action == "right_pulse":
            self._right_until = now + KEYBOARD_PULSE
        elif action == "plunge_down":
            if self.engine.state.charging:
                self.engine.release_plunge()   # 键盘再按一次 = 提前松手
            else:
                self.engine.start_charge()
            self._refresh()
            return
        elif action == "plunge_up":
            self.engine.release_plunge()
            self._refresh()
            return
        elif action == "pause":
            self._toggle_pause()
            return
        elif action == "restart":
            self._restart()
            return
        else:
            return
        # 挡板状态下一帧由 _update_holds 同步给引擎
        self.engine.set_flipper("left", now < self._left_until)
        self.engine.set_flipper("right", now < self._right_until)
        self._refresh()

    def _on_key(self, e: ft.KeyboardEvent):
        # flet 把空格上报为 " "，strip 后变空串，这里归一为 "space"。
        raw = (e.key or "").strip().lower()
        if raw == "" or raw == "spacebar":
            raw = "space"
        action = self._KEY_ALIAS.get(raw)
        if action:
            self._act(action)

    def _update_holds(self, now: float) -> None:
        """每帧把「按住到几点」翻译成挡板状态。"""
        self.engine.set_flipper("left", now < self._left_until)
        self.engine.set_flipper("right", now < self._right_until)

    # ---------- 主循环 ----------

    async def _loop(self) -> None:
        """60FPS：按真实帧间隔推进物理，刷新台面与信息栏。"""
        last = time.monotonic()
        try:
            while self._attached:
                await asyncio.sleep(1 / 60)
                now = time.monotonic()
                dt = now - last
                last = now
                self._update_holds(now)
                self.engine.advance(dt)
                self.table.sync()
                self._render_side()
                if self.engine.is_over():
                    self._save_match_log()
                self.page.update()
        except asyncio.CancelledError:
            raise
        except Exception as exc:                # noqa: BLE001 — 循环不能死
            print(f"[pinball] 主循环出错：{exc!r}")

    # ---------- 生命周期 ----------

    def _attach(self) -> None:
        self._attached = True
        self._prev_keyboard = self.page.on_keyboard_event
        self.page.on_keyboard_event = self._on_key
        # 走全局 resize 分发器，不覆盖框架 / 其它页面的回调
        responsive.subscribe(self.page, "pinball.play", self._on_resize)
        try:
            self._task = self.page.run_task(self._loop)
        except Exception:                       # noqa: BLE001
            self._task = None

    def _on_resize(self, *_args) -> None:
        """窗口变了：只改台面缩放，球 / 分数 / 物理状态都不动。"""
        self._layout()
        self.table.rebuild(self.scale)
        self._refresh()

    def _detach(self) -> None:
        self._attached = False
        if self._task is not None:
            try:
                self._task.cancel()
            except Exception:                   # noqa: BLE001
                pass
            self._task = None
        try:
            self.page.on_keyboard_event = self._prev_keyboard
        except Exception:                       # noqa: BLE001
            pass
        responsive.unsubscribe(self.page, "pinball.play", self._on_resize)
        self.pad.detach()

    def _restart(self) -> None:
        best = max(self.engine.state.best, self.engine.state.score)
        self.engine.restart(best=best)
        self._log_saved = False
        self._left_until = self._right_until = 0.0
        self._refresh()

    def _toggle_pause(self) -> None:
        self.engine.toggle_pause()
        self._refresh()

    # ---------- 历史记录 ----------

    def _save_match_log(self) -> None:
        """3 球用尽时落盘一次（分数 / 最高分 / 命中数 / 用时）。"""
        if self._log_saved or not self.engine.is_over():
            return
        self._log_saved = True
        s = self.engine.state
        meta = {
            "状态": "游戏结束",
            "分数": str(s.score),
            "最高分": str(max(s.best, s.score)),
            "保险杠命中": str(s.bumper_hits),
            "挡板击球": str(s.flipper_hits),
            "用时": f"{int(s.elapsed)} 秒",
            "模式": "单人",
        }
        lines = [
            f"分数：{s.score}",
            f"最高分：{max(s.best, s.score)}",
            f"保险杠命中：{s.bumper_hits}",
            f"挡板击球：{s.flipper_hits}",
            f"用时：{int(s.elapsed)} 秒",
            "结果：3 球用尽，游戏结束",
        ]
        try:
            from core import history
            history.save_match_log("pinball", lines, meta)
        except Exception as exc:                # noqa: BLE001
            print(f"[pinball] 保存历史记录失败：{exc!r}")


def build(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """入口：新建一页对局并返回控件树。"""
    return _PlayPage(page, navigate).build()
