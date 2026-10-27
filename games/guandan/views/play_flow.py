# -*- coding: utf-8 -*-
"""掼蛋牌桌的「流转」那一半：结算、落盘、离开确认、发下一手。

由 :class:`games.guandan.views.play_view._Play` 以 mixin 的方式继承。
"""

from __future__ import annotations

import flet as ft

from core import history
from core.net import session as _sess
from core.theme import T
from games.guandan.engine import Hand, settle
from games.guandan.views.history_view import open_history
from games.guandan.views.play_const import (
    BOMB_COLOR,
    HEAD_COLOR,
    LEVEL_GOLD,
    MUTED,
    NAMES,
    WIN_COLOR,
    _plan_summary,
)

class PlayFlowMixin:
    """流转：结算 / 落盘 / 离开确认 / 发下一手。"""

    # ============================================================
    # 流转
    # ============================================================

    # ---------- 结算与落盘 ----------
    def _after_action(self):
        """任何一次出牌/过牌之后：结算或继续。"""
        if self.hand.ended:
            self.result = settle(self.match, self.hand)
            self._result_hand_no = self.match.hand_no
            r = self.result
            self._log(
                "本局结束：" + "  ".join(NAMES[p] for p in r.out_order), MUTED)
            if r.match_over:
                self._log(f"◆ 整场结束 · 队{r.winner_team} 获胜",
                          WIN_COLOR, bold=True)
                # 联机客人不在此刻落盘：他的日志要等房主快照补齐，
                # 统一在 _apply_state 里确认 winner 后才写（见那里）
                if self.net is None or self.is_host:
                    self._save_match_log()
            else:
                self._log(
                    f"队{r.winner_team} 升 {r.upgrade} 级 → "
                    f"{r.levels_after[0]}/{r.levels_after[1]}", HEAD_COLOR)
                plan = self.match.pending_tribute
                if plan is not None:
                    self._log(
                        f"下一手进贡：{_plan_summary(plan)}", LEVEL_GOLD)
            self.selected.clear()
        self._refresh()

    def _save_match_log(self, finished: bool = True) -> None:
        """把这一场的完整出牌记录落盘到应用数据目录。

        整场结束（``finished=True``）会存，**中途离开也会存**（标成「中途结束」），
        这样历史记录里每一场都留得下，不会白打。同一场只写一次文件。
        """
        if self._log_saved or not self._log_lines:
            return
        self._log_saved = True
        state = "整场结束" if finished else "中途结束（未打完）"
        winner = (f"队{self.result.winner_team}" if self.result
                  else ("未分胜负" if not finished else "未知"))
        lines = list(self._log_lines) + [
            f"◆ 记录结束：{state} · 打完 {self.match.hand_no} 局 · "
            f"级数 {self.match.levels[0]}/{self.match.levels[1]}",
        ]
        try:
            path = history.save_match_log(
                "guandan", lines,
                meta={
                    "状态": state,
                    "胜方": winner,
                    "局数": self.match.hand_no,
                    "级数": f"{self.match.levels[0]}/{self.match.levels[1]}",
                    "座位": self._seat_summary(),
                },
            )
        except Exception as e:                      # noqa: BLE001
            self._log(f"保存出牌记录失败：{e}", BOMB_COLOR)
            return
        if path and str(path):
            self._log(f"出牌记录已保存：{path}", MUTED)
        else:
            self._log("出牌记录保存失败（数据目录不可写？）", BOMB_COLOR)

    def _in_progress(self) -> bool:
        """当前是否还有没打完的对局（整场结束 / 已分胜负就不算）。"""
        if self.match.winner is not None:
            return False
        return not (self.result is not None and self.result.match_over)

    # ---------- 离开牌桌 ----------
    def _leave_target(self) -> str:
        """回哪：这局是从联机房间开起来的就回房间，否则回掼蛋子菜单。"""
        return "/room" if _sess.current() is not None else "/g/guandan"

    def _on_back(self, _e):
        """顶栏返回：牌没打完先问一句，避免误触丢掉这一局。"""
        if self._in_progress():
            self._confirm_leave(lambda: self.navigate(self._leave_target()))
            return
        self._save_match_log(False)
        self.alive = False
        self._detach_net()
        self.navigate(self._leave_target())

    def _on_history(self, _e):
        """顶栏「历史记录」：看往期出牌记录（同理先确认）。"""
        if self._in_progress():
            self._confirm_leave(lambda: open_history(self.navigate))
            return
        self._save_match_log(False)
        self.alive = False
        self._detach_net()
        open_history(self.navigate)

    def _confirm_leave(self, go):
        """离开前确认；``go`` 是确认后真正执行的跳转。"""
        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("离开当前对局？"),
                content=ft.Text(
                    "这局还没打完：离开后无法继续打，但出牌记录会自动存进"
                    "「历史记录」。", size=13),
                actions=[
                    ft.TextButton(content=ft.Text("取消"),
                                  on_click=lambda _e: self.page.pop_dialog()),
                    ft.TextButton(content=ft.Text("离开"),
                                  on_click=lambda _e: self._leave_to(go)),
                ],
            )
        )

    def _leave_to(self, go):

        """确认离开并跳到目标页面。"""
        self.page.pop_dialog()
        self._save_match_log(False)     # 中途退出也留一份记录
        self.alive = False
        self._detach_net()
        go()

    def _on_after_hand(self, _e):

        """一手结束后的提示（要不要继续下一手）。"""
        r = self.result
        if r is not None and r.match_over:
            self.alive = False
            self._detach_net()
            self.navigate(self._leave_target())
            return
        if self.net is not None and not self.is_host:
            # 客人不洗牌：请房主发下一手，快照回来自然换手（0.4.8-fix：
            # 此前客人本地 Hand() 会自己随机发一副，又变成各玩各的）
            self.net.send_game_to_host({"k": "next"})
            self.hint_text.value = "已请求房主发下一手…"
            self.hint_text.color = T.TEXT_MUTED
            self._refresh()
            return
        self._deal_next_hand()

    def _deal_next_hand(self):
        """本地（房主 / 单人）发下一手，并把新局面推给联机房间。"""
        r = self.result
        self.result = None
        self.match.next_leader = (
            r.out_order[0] if r is not None else self.match.next_leader
        )
        self.hand = Hand(self.match)
        self.selected.clear()
        self.tribute_sel.clear()
        self.gift_marks.clear()          # 上一轮进贡得来的标记只管那一轮
        self._log(f"── 第 {self.match.hand_no + 1} 局 ──", HEAD_COLOR, bold=True)
        tr = self.hand.tribute
        if tr is not None and (tr.active or tr.refused):
            # 先发牌再进贡：进贡用的是这一手刚发好的牌（抗贡时 summary 说抗贡）
            self._log(tr.summary(), LEVEL_GOLD)
            if tr.refused:
                self._log(f"抗贡不换牌，由{NAMES[self.hand.turn]}先出",
                          HEAD_COLOR)
        self._refresh()
        self._start_ai()
        self._push_state()

    def dispose(self):
        """视图被丢弃：兜底再存一次（正常退出走 _on_back，这里是保险）。"""
        self._save_match_log(False)
        self.alive = False
        self._detach_net()
