# -*- coding: utf-8 -*-
"""台球对局页的「联机」那一半：身份、击球请求、状态同步。

分成 mixin 是为了守住「单文件不超过 500 行」的规矩（见 CODE_INDEX.md）：
``views_play.py`` 只管画面与主循环，网络的事都放在这里。

联机模型
--------
* **房主权威**：只有房主判规则（换手 / 犯规 / 胜负）。
* **击球只传方向 + 力度**：手机和电脑的球桌尺寸不同，绝对速度没有
  可比性；方向和力度（0~1）两端都能换算成自己的速度。
* **两端各跑各的物理**：动画才顺滑；一杆结束后房主广播整局快照，
  所有人按快照对齐，最终状态一定一致。
"""

from __future__ import annotations

from typing import Optional

from .engine import BilliardsEngine, PHASE_AIM, PHASE_SHOOT


class PlayNetMixin:
    """联机同步：算身份、发请求、收消息、对齐快照。"""

    # ============================================================
    # 身份
    # ============================================================

    def _compute_role(self) -> None:
        """按房间席位表算本机身份（1 号 / 2 号 / 观战）。"""
        if self.net is None:
            self.role = "local"
            return
        try:
            members = self.net.roster()
            seated = sorted((m for m in members if m.seat >= 0),
                            key=lambda m: m.seat)
            players = [m for m in seated if m.seat < self.players]
        except Exception as exc:            # 手机端红屏比降级成观战糟糕得多
            print(f"[billiards] 算身份失败，先按观战处理：{exc!r}")
            players = []
        me = getattr(self.net, "me", None)
        my_mid = getattr(me, "mid", None)
        self.role = "spectator"
        for i, m in enumerate(players[:2]):
            if m.mid == my_mid:
                self.role = f"p{i}"
                break

    def _my_index(self) -> Optional[int]:
        """本机是几号选手（0 / 1）；观战或本地返回 None。"""
        if self.role in ("p0", "p1"):
            return int(self.role[1])
        return None

    def _index_of_mid(self, mid: str) -> Optional[int]:
        """房间成员 id → 选手序号（0 / 1）。"""
        if not mid or self.net is None:
            return None
        try:
            members = self.net.roster()
            seated = sorted((m for m in members if m.seat >= 0),
                            key=lambda m: m.seat)
            players = [m for m in seated if m.seat < self.players]
        except Exception:                   # noqa: BLE001
            return None
        for i, m in enumerate(players[:2]):
            if m.mid == mid:
                return i
        return None

    def _my_mid(self) -> str:
        """本机在房间里的成员 id（发请求时带上，房主才知道是谁）。"""
        me = getattr(self.net, "me", None)
        return str(getattr(me, "mid", "") or "")

    def _may_act(self) -> bool:
        """本机现在能不能操作母球。"""
        if self.engine.is_over() or self.engine.phase != PHASE_AIM:
            return False
        if self.net is None:
            return True                     # 本地双人：轮到谁谁打
        idx = self._my_index()
        return idx is not None and idx == self.engine.turn

    # ============================================================
    # 击球
    # ============================================================

    def _shoot(self, dx: float, dy: float, power: float) -> None:
        """本机玩家出了一杆。"""
        if self.engine.is_over() or self.engine.phase != PHASE_AIM:
            return
        if self.net is not None:
            if self._my_index() != self.engine.turn:
                return                      # 不是自己的回合
            if self.net.is_host:
                if self._apply_shot(dx, dy, power):
                    self._broadcast({"k": "shot", "dir": [dx, dy],
                                     "power": power})
            else:
                # 客人：把请求交给房主，房主校验后才算数
                self._send_to_host({"k": "req_shoot", "dir": [dx, dy],
                                    "power": power, "from": self._my_mid()})
            return
        self._apply_shot(dx, dy, power)

    def _apply_shot(self, dx: float, dy: float, power: float) -> bool:
        """真的给母球一个初速度（本地物理开始跑）。"""
        ok = self.engine.shoot(dx, dy, power)
        if ok:
            self.table_view.clear_aim()
            self._render_side()
        return ok

    # ============================================================
    # 收发
    # ============================================================

    def _broadcast(self, data: dict) -> None:
        """房主把一帧玩法数据发给房间里其他所有人。"""
        if self.net is None:
            return
        try:
            self.net.send_game(data)
        except Exception:                   # noqa: BLE001 — 网络断开不崩
            pass

    def _broadcast_state(self) -> None:
        """房主广播整局快照（唯一权威状态）。"""
        self._broadcast({"k": "state", "s": self.engine.to_dict()})

    def _send_to_host(self, data: dict) -> None:
        """客人把请求单播给房主。"""
        if self.net is None:
            return
        try:
            self.net.send_game_to_host(data)
        except Exception:                   # noqa: BLE001
            pass

    def _on_net(self, msg) -> None:
        """收到房间里的玩法消息（网络线程直接调用，所以要兜住异常）。"""
        if not self._attached or self.net is None:
            return
        try:
            self._handle_net(msg)
        except Exception as exc:             # noqa: BLE001 — 不能拖垮网络线程
            print(f"[billiards] 处理玩法消息出错：{exc!r}")

    def _handle_net(self, msg) -> None:
        """玩法消息的实际处理。"""
        data = (msg or {}).get("data") or {}
        k = data.get("k")
        if k == "shot":
            # 房主说「开杆了」：照着跑一遍本地物理
            if self.engine.phase != PHASE_AIM:
                return
            dirv = data.get("dir") or [1.0, 0.0]
            self._apply_shot(float(dirv[0]), float(dirv[1]),
                             float(data.get("power", 0.5)))
        elif k == "req_shoot":
            self._host_shoot(data)
        elif k == "state":
            st = data.get("s")
            if st:
                if self.engine.phase == PHASE_SHOOT:
                    # 本地物理还没停，先存着；停稳后再对齐
                    self._pending_state = st
                else:
                    self._apply_state(st)
        elif k == "req_state":
            if self.net.is_host:
                self._broadcast_state()
        elif k == "req_reset":
            if self.net.is_host:
                self._engine_reset()
                self._broadcast_state()
        elif k == "req_place":
            self._host_place(data)
        self._compute_role()

    def _host_shoot(self, data: dict) -> None:
        """房主收到客人的击球请求：校验轮次后开杆并广播。"""
        if self.net is None or not self.net.is_host:
            return
        idx = self._index_of_mid(str(data.get("from") or ""))
        if idx is None or idx != self.engine.turn:
            return
        if self.engine.phase != PHASE_AIM:
            return
        dirv = data.get("dir") or [1.0, 0.0]
        dx, dy = float(dirv[0]), float(dirv[1])
        power = float(data.get("power", 0.5))
        if not self._apply_shot(dx, dy, power):
            return
        self._broadcast({"k": "shot", "dir": [dx, dy], "power": power})

    def _host_place(self, data: dict) -> None:
        """房主收到客人的摆球请求：校验后落定并广播。"""
        if self.net is None or not self.net.is_host:
            return
        idx = self._index_of_mid(str(data.get("from") or ""))
        if idx is None or idx != self.engine.turn:
            return
        if self.engine.place_cue(float(data.get("x", 0.0)),
                                 float(data.get("y", 0.0))):
            self._broadcast_state()

    def _apply_state(self, data: dict) -> None:
        """按房主的快照重建局面（联机唯一权威）。"""
        if not data:
            return
        size = (self.engine.table.width, self.engine.table.height)
        self.engine = BilliardsEngine.from_dict(data, size=size)
        self.table_view.engine = self.engine
        self.table_view.sync()
        self._render_side()
        self.page.update()
