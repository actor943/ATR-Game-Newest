# -*- coding: utf-8 -*-
"""台球对局页的「手势」那一半：拖白球拉弓瞄准、犯规后摆白球。

交互方案：**拉弓（slingshot）**
-----------------------------
1. 按住白球（按在球附近才算抓住）；
2. 往后拖 —— 击球方向 = 白球 − 指针（像拉弓），拖得越远力度越大；
3. 松手出杆。

犯规后的**自由球**用同一个手势：这次拖动不是拉弓，而是把白球挪到
想要的位置（松手落定）。

手感要点：屏幕坐标就是物理坐标（手势层的 ``local_position`` 与球桌
坐标系一一对应），所以不需要任何换算，拖到哪就是哪。
"""

from __future__ import annotations

import math


class PlayGestureMixin:
    """拖拽手势：瞄准击球 / 摆放白球。"""

    # ============================================================
    # 手势
    # ============================================================

    def _max_pull(self) -> float:
        """拉满弓需要的距离（拖得越远力度越大）。"""
        return max(30.0, self.engine.table.height * 0.42)

    def _on_pan_start(self, x: float, y: float) -> None:
        """按下开始拖拽：瞄准模式可在桌面任意位置起手（手机更好戳）。

        过去必须按在母球上（半径 2.4 倍内）才算抓住，白球只有二十几像素、
        手指触控面积大，经常抓空。现在放宽：只要轮到你、母球在台面上，
        在桌子任意位置按下都能拉弓 —— 方向仍是「母球 − 指针」，
        所以「往后拉、球往前走」的手感不变，只是起点不用精准命中小球。
        """
        self._drag = None
        self._aim = None
        if not self._may_act():
            return
        cue = self.engine.cue
        if cue is None or not cue.active:
            return
        self._drag = "place" if self.engine.ball_in_hand else "aim"
        if self._drag == "place":
            self._place_preview(x, y)

    def _on_pan_update(self, x: float, y: float) -> None:
        """拖动：摆白球 / 拉弓瞄准。"""
        if self._drag == "place":
            self._place_preview(x, y)
            return
        if self._drag != "aim":
            return
        cue = self.engine.cue
        if cue is None:
            return
        # 拉弓：击球方向 = 母球 - 指针（往后拉，球往前走）
        dx = cue.x - x
        dy = cue.y - y
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            return
        power = min(1.0, dist / self._max_pull())
        self._aim = (dx / dist, dy / dist, power)
        self.table_view.set_aim(cue.x, cue.y, dx / dist, dy / dist, power)
        self._render_power(power)
        self.page.update()

    def _on_pan_end(self, x: float, y: float) -> None:
        """松手：摆好白球 / 打一杆。"""
        mode = self._drag
        self._drag = None
        if mode == "place":
            self._commit_place()
            return
        if mode != "aim":
            return
        aim = self._aim
        self._aim = None
        self.table_view.clear_aim()
        self._render_power(0.0)
        if aim and aim[2] >= 0.06:
            self._shoot(aim[0], aim[1], aim[2])
        self._render_side()
        self.page.update()

    # ---------- 自由球 ----------

    def _place_preview(self, x: float, y: float) -> None:
        """拖动时把母球跟着指针走（只放在合法位置）。"""
        t = self.engine.table
        r = t.ball_radius
        x = max(r, min(t.width - r, x))
        y = max(r, min(t.height - r, y))
        if not self.engine.can_place_cue(x, y):
            return
        cue = self.engine.cue
        if cue is None:
            return
        cue.x, cue.y = x, y
        self.table_view.sync()
        self.page.update()

    def _commit_place(self) -> None:
        """摆好白球：本地直接生效；联机请房主确认。"""
        cue = self.engine.cue
        if cue is None:
            return
        x, y = cue.x, cue.y
        if self.net is None:
            self.engine.place_cue(x, y)
        elif self.net.is_host:
            if self.engine.place_cue(x, y):
                self._broadcast_state()
        else:
            # 先本地摆好（手感即时），再请房主确认
            self.engine.place_cue(x, y)
            self._send_to_host({"k": "req_place", "x": x, "y": y,
                                "from": self._my_mid()})
        self._render_side()
        self.page.update()
