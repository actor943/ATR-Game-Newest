# -*- coding: utf-8 -*-
"""掼蛋牌桌的「电脑代打」那一半：由 asyncio 协程驱动 AI 出牌。

由 :class:`games.guandan.views.play_view._Play` 以 mixin 的方式继承。
"""

from __future__ import annotations

import asyncio

from games.guandan.ai import choose
from games.guandan.engine import IllegalMove
from games.guandan.views.play_const import (
    AI_DELAY,
    BOMB_COLOR,
    HUMAN_POLL,
    MUTED,
    NAMES,
    TEAM_COLOR,
    WIN_COLOR,
    _is_bomb,
    combo_wild_note,
)

class PlayAiMixin:
    """电脑代打：协程驱动 AI 出牌。"""

    def _start_ai(self):

        """起一个协程，按座位轮流替电脑出牌。"""
        if self._ai_task is None or self._ai_task.done():
            self._ai_task = self.page.run_task(self._ai_loop)

    async def _ai_loop(self):
        # 联机时**只有房主跑电脑代打**：房主每步都会重推快照，客人照抄即可；
        # 两边都跑 AI 只会无故分歧（0.4.8-fix）。
        """AI 主循环：等轮到某个电脑位 → 让它出一手 → 继续等。"""
        if self.net is not None and not self.is_host:
            return
        while self.alive:
            if self.match.winner is not None:
                return
            # ---- 进贡阶段：电脑位自动进贡 / 还贡 ----
            tr = self.hand.tribute
            if tr is not None and tr.active and not tr.done:
                await asyncio.sleep(AI_DELAY)
                if not self.alive:
                    return
                tr = self.hand.tribute
                if tr is None or not tr.active or tr.done:
                    continue
                act = tr.current()
                if act is None:
                    continue
                if not self._is_auto(act.player):
                    await asyncio.sleep(HUMAN_POLL)   # 等真人，无倒计时
                    continue
                self._tribute_ai_step(tr)
                self._refresh()
                self._push_state()
                continue
            if self.hand.ended:
                return
            turn = self.hand.turn
            if not self._is_auto(turn):
                await asyncio.sleep(HUMAN_POLL)     # 等真人，无倒计时
                continue
            await asyncio.sleep(AI_DELAY)
            if self.hand.ended or self.match.winner is not None:
                return
            turn = self.hand.turn                  # 等待期间可能已换人
            if not self._is_auto(turn):
                continue
            self._ai_step(turn)
            self._after_action()
            self._push_state()

    def _ai_step(self, turn: int):

        """让某个电脑位出一手牌（交给 AI 模块选牌）。"""
        combo = choose(self.hand, turn)
        try:
            if combo is None:
                self.hand.pass_turn(turn)
                self._log(f"{NAMES[turn]} 过", MUTED)
                return
            played = self.hand.play(turn, combo.cards)
        except IllegalMove as e:
            # 理论上不会发生；出现就跳过，避免协程空转
            self._log(f"{NAMES[turn]} 出牌异常：{e}", BOMB_COLOR)
            return
        bomb = _is_bomb(played)
        self._log_play(turn, played, bomb)
        if turn in self.hand.out_order:
            self._log(f"★ {NAMES[turn]} 出完（{len(self.hand.out_order)}游）",
                      WIN_COLOR, bold=True)

    def _log_play(self, seat: int, combo, bomb: bool):
        """出牌日志：牌型 + 队色；用了逢人配时追加「当什么用、原本是谁的」。"""
        note = combo_wild_note(combo.cards, self.hand.ctx,
                               self.cfg.team_of(seat), combo)
        self._log(f"{NAMES[seat]} 出 {combo}" + (f"    {note}" if note else ""),
                  BOMB_COLOR if bomb else TEAM_COLOR[self.cfg.team_of(seat)],
                  bold=bomb)
