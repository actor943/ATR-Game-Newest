# -*- coding: utf-8 -*-
"""国际象棋的「棋谱落盘」那一半：记录着法、赛后存文件。

与掼蛋共用 :mod:`core.history` 的落盘逻辑（同一套数据目录、同一套文件名规则）。
由 :class:`games.chess.views.ChessPlayView` 以 mixin 的方式继承。
"""

from __future__ import annotations

from core import history

class ChessRecordMixin:
    """棋谱记录与落盘。"""

    # ------------------------------------------------------------------
    # 对局记录（与掼蛋共用 core/history 的落盘逻辑）
    # ------------------------------------------------------------------
    def _mode_label(self) -> str:
        """这一局的模式，写进记录元信息。"""
        if self.net is None:
            return "本地双人"
        if self.role == "spectator":
            return "联网-观战"
        return "联网-" + ("白方" if self.role == "w" else "黑方")

    @staticmethod
    def _coord(r: int, c: int) -> str:
        """棋盘坐标 (row, col) → 国际象棋记谱坐标，如 e2、a7。"""
        return chr(ord("a") + c) + str(8 - r)

    def _record_ply(self, color: str, fr: int, fc: int, tr: int, tc: int,
                    promo) -> None:
        """把一步着法追加到落盘日志（纯文本，赛后保存用）。"""
        self._ply += 1
        move_no = (self._ply + 1) // 2          # 第几个完整回合（1 起）
        side = "白" if color == "w" else "黑"
        promo_s = ("=" + promo) if promo else ""
        san = (f"{move_no}. {side} {self._coord(fr, fc)}"
               f"-{self._coord(tr, tc)}{promo_s}")
        if self.game.is_checkmate():
            san += " #"                          # 将死
        elif self.game.in_check(self.game.turn):
            san += "+"                           # 将军
        self._log_lines.append(san)

    def _maybe_save_on_end(self) -> None:
        """对局结束（将死 / 逼和）且还没保存过，就落盘。"""
        if self.game.is_game_over() and not self._log_saved:
            self._save_match_log(finished=True)

    def _save_match_log(self, finished: bool = True,
                        opponent_left: bool = False) -> None:
        """把这一局的完整着法落盘到应用数据目录（``logs/chess/``）。

        将死 / 逼和 / 对手离场 会存；中途离开（``on_back``）也存（标「中途结束」），
        这样历史记录里每一局都留得下。同一局只写一次文件。
        """
        if self._log_saved or not self._log_lines:
            return
        self._log_saved = True
        if opponent_left:
            winner = "白方" if self.role == "w" else "黑方"
            state = "对手离场判胜"
        elif self.game.is_checkmate():
            # 轮到走棋的一方被将死 → 对方获胜
            winner = "黑方" if self.game.turn == "w" else "白方"
            state = "整场结束"
        elif self.game.is_stalemate():
            winner = "和棋"
            state = "整场结束"
        elif not finished:
            winner = "未分胜负"
            state = "中途结束（未打完）"
        else:
            winner = "未分胜负"
            state = "中途结束（未打完）"
        mode = self._mode_label()
        lines = list(self._log_lines) + [
            f"◆ 记录结束：{state} · 共 {self._ply} 步 · {mode}",
        ]
        try:
            history.save_match_log(
                "chess", lines,
                meta={
                    "状态": state,
                    "胜方": winner,
                    "步数": self._ply,
                    "模式": mode,
                },
            )
        except Exception:                          # noqa: BLE001
            pass     # 数据目录不可写时静默失败，不影响对局
