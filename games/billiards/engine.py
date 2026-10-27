# -*- coding: utf-8 -*-
"""台球规则引擎（纯逻辑，**不依赖 flet**，可命令行自检）。

采用的规则（中式八球简化版）
----------------------------
* 15 颗目标球：1~7 实色、8 号黑球、9~15 花色，外加一颗白球。
* **开球**：谁先合法打进一颗球，那颗球的花色就是他的组（实色 / 花色）。
* 打进**自己组**的球 → 继续击球；否则换手。
* 犯规（判给对方自由球）：白球落袋、白球没碰到任何球（空杆）、
  先碰到对方组的球、打进对方组的球。
* 自己组的球全部进袋后，才可以打 8 号球；此时打进 8 号球即获胜。
  **提前**打进 8 号球 → 直接判负。
* 犯规后对方获得自由球：可以把白球放在台面任意合法位置。

物理在 :mod:`games.billiards.physics`，这里只做「规则判断」，
所以物理可以独立跑测试、规则也可以单独跑测试。

状态是确定性的，:meth:`BilliardsEngine.to_dict` / :meth:`from_dict`
能完整往返 —— 联机时房主生成快照、客人还原即可。
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from .physics import (
    BASE_H, BASE_W, KIND_CUE, KIND_EIGHT, KIND_SOLID, KIND_STRIPE, Ball,
    Table, all_stopped, find_spot, kind_of, legal_spot, rack_balls, step,
)

# ============================================================
# 常量
# ============================================================

GROUP_SOLID = KIND_SOLID      # "solid"
GROUP_STRIPE = KIND_STRIPE    # "stripe"
GROUP_EIGHT = KIND_EIGHT      # "eight"

PHASE_AIM = "aim"             # 等着出杆
PHASE_SHOOT = "shoot"         # 球还在滚
PHASE_OVER = "over"           # 分出胜负

# 犯规原因（界面据此显示提示）
FOUL_SCRATCH = "scratch"            # 白球落袋
FOUL_NO_CONTACT = "no_contact"      # 空杆：白球没碰到任何球
FOUL_WRONG_FIRST = "wrong_first"    # 先碰到了对方组的球
FOUL_WRONG_BALL = "wrong_ball"      # 打进了对方组的球
FOUL_EIGHT_EARLY = "eight_early"    # 提前打进 8 号球


# ============================================================
# 引擎
# ============================================================


class BilliardsEngine:
    """一局台球：桌上的球、轮到谁、双方花色、胜负、犯规。"""

    def __init__(self, width: float = BASE_W, height: float = BASE_H):
        self.table = Table(width, height)
        self.balls: List[Ball] = []
        self.turn = 0                 # 当前该谁击球（0 / 1）
        self.groups: List[Optional[str]] = [None, None]   # 双方花色
        self.potted: List[int] = []    # 已落袋的球号（按顺序）
        self.phase = PHASE_AIM
        self.result: Optional[int] = None   # 胜者（0 / 1），None = 还没分出
        self.ball_in_hand = False      # 当前击球方握有自由球
        self.shots: List[dict] = []    # 每一杆的记录（写历史用）
        self.fouls: List[str] = []     # 最近一杆的犯规原因
        self.message = ""              # 最近一条状态说明
        self._ev_potted: List[int] = []
        self._ev_first: Optional[int] = None
        self._ev_hits = 0
        self.reset()

    # ============================================================
    # 开新局
    # ============================================================

    def reset(self) -> None:
        """重新摆球、开新局。"""
        self.balls = rack_balls(self.table)
        self.balls.append(Ball(x=self.table.head_x, y=self.table.head_y,
                               radius=self.table.ball_radius,
                               number=0, kind=KIND_CUE))
        self.turn = 0
        self.groups = [None, None]
        self.potted = []
        self.phase = PHASE_AIM
        self.result = None
        self.ball_in_hand = False
        self.shots = []
        self.fouls = []
        self.message = ""
        self._ev_potted = []
        self._ev_first = None
        self._ev_hits = 0

    # ============================================================
    # 查询
    # ============================================================

    @property
    def cue(self) -> Optional[Ball]:
        """白球（不在台面上时返回 None）。"""
        for b in self.balls:
            if b.number == 0:
                return b
        return None

    def ball(self, number: int) -> Optional[Ball]:
        for b in self.balls:
            if b.number == number:
                return b
        return None

    @staticmethod
    def group_of(number: int) -> str:
        """球号 → 所属组（solid / stripe / eight / cue）。"""
        return kind_of(number)

    def on_table(self, group: str) -> int:
        """桌上还剩几颗属于该组的球。"""
        return sum(1 for b in self.balls
                   if b.active and b.kind == group)

    def cleared(self, player: int) -> bool:
        """某位玩家的组是不是已经全部进袋。"""
        group = self.groups[player]
        if group is None:
            return False
        return self.on_table(group) == 0

    def is_over(self) -> bool:
        return self.phase == PHASE_OVER

    def can_shoot(self) -> bool:
        """现在能不能出杆（没分胜负、球停着、白球在台面上）。"""
        if self.phase != PHASE_AIM:
            return False
        cue = self.cue
        return cue is not None and cue.active

    # ============================================================
    # 击球
    # ============================================================

    def shoot(self, dx: float, dy: float, power: float) -> bool:
        """给白球一个初速度（``dx``/``dy`` 是方向，``power`` 是 0~1）。

        返回是否成功出杆。方向会归一化，所以传什么长度都行。
        """
        if not self.can_shoot():
            return False
        n = math.hypot(dx, dy)
        if n <= 1e-9:
            return False
        cue = self.cue
        if cue is None:
            return False
        p = max(0.05, min(1.0, float(power)))
        cue.vx = dx / n * self.table.max_speed * p
        cue.vy = dy / n * self.table.max_speed * p
        self.phase = PHASE_SHOOT
        self.ball_in_hand = False
        self._ev_potted = []
        self._ev_first = None
        self._ev_hits = 0
        return True

    def advance(self, dt: float) -> bool:
        """推进物理；返回 True 表示这一杆已经停稳（可以判规则了）。"""
        if self.phase != PHASE_SHOOT:
            return False
        ev = step(self.balls, self.table, dt)
        self._ev_potted.extend(ev["potted"])       # type: ignore[arg-type]
        if self._ev_first is None and ev["first_contact"] is not None:
            self._ev_first = int(ev["first_contact"])  # type: ignore[arg-type]
        self._ev_hits += int(ev["hits"])           # type: ignore[arg-type]
        if all_stopped(self.balls):
            self.phase = PHASE_AIM
            self.resolve()
            return True
        return False

    # ============================================================
    # 规则判定
    # ============================================================

    def resolve(self) -> dict:
        """一杆结束后的规则判定：换手 / 犯规 / 分出胜负。

        返回一个描述这一杆的小字典（联机时原样传给界面显示）。
        """
        shooter = self.turn
        potted = [n for n in self._ev_potted if n != 0]
        scratch = 0 in self._ev_potted
        first = self._ev_first
        my_group = self.groups[shooter]
        other_group = self.groups[1 - shooter]

        fouls: List[str] = []
        # 1) 白球落袋
        if scratch:
            fouls.append(FOUL_SCRATCH)
        # 2) 空杆：白球没碰到任何球
        if first is None:
            fouls.append(FOUL_NO_CONTACT)
        # 3) 先碰到对方组的球
        if first is not None:
            fg = self.group_of(first)
            if my_group is not None and fg not in (my_group, GROUP_EIGHT):
                fouls.append(FOUL_WRONG_FIRST)
            elif my_group is None and other_group is not None \
                    and fg == other_group:
                fouls.append(FOUL_WRONG_FIRST)
        # 4) 打进对方组的球
        if my_group is not None:
            for n in potted:
                g = self.group_of(n)
                if g == GROUP_EIGHT:
                    continue
                if g != my_group:
                    fouls.append(FOUL_WRONG_BALL)
                    break
        elif other_group is not None:
            for n in potted:
                g = self.group_of(n)
                if g == other_group:
                    fouls.append(FOUL_WRONG_BALL)
                    break

        # 5) 8 号球：清了组才能打；提前打进直接判负
        if GROUP_EIGHT in [self.group_of(n) for n in potted]:
            if my_group is None or not self.cleared(shooter):
                fouls.append(FOUL_EIGHT_EARLY)
            self.fouls = list(fouls)
            self._record(shooter, potted, self.fouls)
            if FOUL_EIGHT_EARLY in fouls:
                self.result = 1 - shooter
                self.phase = PHASE_OVER
                self.message = FOUL_EIGHT_EARLY
                return {"winner": self.result, "fouls": list(self.fouls),
                        "turn": self.turn}
            self.result = shooter
            self.phase = PHASE_OVER
            self.message = "win"
            return {"winner": self.result, "fouls": list(self.fouls),
                    "turn": self.turn}

        # 6) 正常流程：记落袋、定花色、换不换手
        for n in potted:
            self.potted.append(n)
        if my_group is None and not fouls:
            for n in potted:
                g = self.group_of(n)
                if g in (GROUP_SOLID, GROUP_STRIPE):
                    self.groups[shooter] = g
                    my_group = g
                    break

        if fouls:
            self.fouls = list(fouls)
            self.turn = 1 - shooter
            self.ball_in_hand = True
            self._spot_cue()
            self.message = ",".join(fouls)
        else:
            self.fouls = []
            own = [n for n in potted
                   if my_group is not None and self.group_of(n) == my_group]
            if own:
                self.message = "continue"          # 进了自己的球，继续
            else:
                self.turn = 1 - shooter
                self.ball_in_hand = False
                self.message = "turn"
        self._record(shooter, potted, self.fouls)
        return {"winner": None, "fouls": list(self.fouls), "turn": self.turn}

    def judge(self, potted: Sequence[int],
              first_contact: Optional[int]) -> dict:
        """直接按「这一杆进了哪些球、白球先碰到谁」判规则。

        正常流程里这些信息来自物理（:meth:`advance` 调 :meth:`resolve`）；
        这个入口给自检和「房主收到结果直接判定」用。
        """
        self._ev_potted = [int(n) for n in potted]
        self._ev_first = None if first_contact is None \
            else int(first_contact)
        return self.resolve()

    def _spot_cue(self) -> None:
        """白球落袋后归位（放在开球线附近的空位）。"""
        cue = self.cue
        if cue is None:
            return
        if not cue.active:
            x, y = find_spot(self.balls, self.table,
                              self.table.head_x, self.table.head_y)
            cue.x, cue.y = x, y
            cue.active = True
        cue.stop()

    def _record(self, shooter: int, potted: List[int],
                fouls: List[str]) -> None:
        """把这一杆记进对局记录（写历史文件用）。"""
        self.shots.append({
            "player": shooter,
            "potted": list(potted),
            "fouls": list(fouls),
        })

    # ============================================================
    # 自由球（犯规后摆放白球）
    # ============================================================

    def can_place_cue(self, x: float, y: float) -> bool:
        """这个位置能不能放白球。"""
        if not self.ball_in_hand:
            return False
        return legal_spot(self.balls, self.table, x, y, ignore=self.cue)

    def place_cue(self, x: float, y: float) -> bool:
        """把白球放到指定位置（自由球）；成功返回 True。"""
        if not self.can_place_cue(x, y):
            return False
        cue = self.cue
        if cue is None:
            return False
        cue.x, cue.y = x, y
        cue.stop()
        cue.active = True
        self.ball_in_hand = False
        return True

    # ============================================================
    # 序列化（联机快照 / 回放）
    # ============================================================

    def to_dict(self) -> dict:
        """整局快照（可以直接 JSON 化）。"""
        return {
            "table": self.table.to_dict(),
            "turn": self.turn,
            "groups": list(self.groups),
            "potted": list(self.potted),
            "phase": self.phase,
            "result": self.result,
            "ball_in_hand": self.ball_in_hand,
            "shots": list(self.shots),
            "fouls": list(self.fouls),
            "message": self.message,
            "balls": [b.to_dict() for b in self.balls],
        }

    @classmethod
    def from_dict(cls, data: dict,
                  size: Optional[Tuple[float, float]] = None) -> "BilliardsEngine":
        """从快照还原。

        ``size`` 给的是**本机**的桌面尺寸：联机时两台机器的球桌可能大小
        不同（手机 vs 电脑），快照里的坐标会按比例换算到本机尺寸。
        """
        tw, th = data.get("table") or [BASE_W, BASE_H]
        src_w = float(tw) or BASE_W          # 快照里的球桌尺寸
        src_h = float(th) or BASE_H
        tw, th = src_w, src_h
        if size is not None:
            tw, th = float(size[0]), float(size[1])
        eng = cls(tw, th)
        eng.turn = int(data.get("turn", 0) or 0)
        groups = list(data.get("groups") or [None, None])
        eng.groups = [groups[0] if len(groups) > 0 else None,
                      groups[1] if len(groups) > 1 else None]
        eng.potted = [int(n) for n in (data.get("potted") or [])]
        eng.phase = str(data.get("phase") or PHASE_AIM)
        result = data.get("result")
        eng.result = None if result is None else int(result)
        eng.ball_in_hand = bool(data.get("ball_in_hand", False))
        eng.shots = list(data.get("shots") or [])
        eng.fouls = list(data.get("fouls") or [])
        eng.message = str(data.get("message") or "")
        sx = eng.table.width / src_w
        sy = eng.table.height / src_h
        balls: List[Ball] = []
        for item in data.get("balls") or []:
            number = int(item[0])
            balls.append(Ball(
                x=float(item[1]) * sx, y=float(item[2]) * sy,
                radius=eng.table.ball_radius, number=number,
                kind=kind_of(number), active=bool(item[3]),
            ))
        if balls:
            eng.balls = balls
        return eng
