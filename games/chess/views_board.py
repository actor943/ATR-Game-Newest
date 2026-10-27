# -*- coding: utf-8 -*-
"""国际象棋棋盘的「画面与走子」那一半：画格子、点格子、升变对话框。

由 :class:`games.chess.views.ChessPlayView` 以 mixin 的方式继承。
"""

from __future__ import annotations

import flet as ft

from core.theme import T
from core.ui_common import page_width

from .assets import piece_image_src
from .engine import PROMO_ORDER

# 棋盘配色（木质风格，不随主题卡片色变化，避免视觉冲突）
LIGHT_SQ = "#F0D9B5"
DARK_SQ = "#B58863"
SELECTED = "#7B61FF"
LASTMOVE = "#C8E6C9"
CHECK_TINT = "#FF8A80"

class ChessBoardMixin:
    """棋盘画面、点格子走子、升变选择。"""

    # ---------- 棋盘绘制 ----------
    def _cell_size(self) -> int:

        """算棋盘一格该画多大（跟着窗口宽度走）。"""
        avail = page_width(self.page) - 2 * getattr(T, "PADDING", 16) - 12
        board_w = min(avail, 460)
        return max(34, int(board_w / 8))

    def _render_board(self):

        """重画整个棋盘：8×8 的格子 + 棋子 + 高亮。"""
        size = self._cell_size()
        row_idxs = list(range(8)) if not self.flip else list(range(7, -1, -1))
        col_idxs = list(range(8)) if not self.flip else list(range(7, -1, -1))

        valid = set()
        if self.selected_pos:
            valid = {(r, c) for (r, c) in self.game.get_valid_moves(*self.selected_pos)}

        lm = self.game.last_move
        last_set = set()
        if lm:
            last_set = {(lm[0], lm[1]), (lm[2], lm[3])}

        rows = []
        for r in row_idxs:
            cells = []
            for c in col_idxs:
                cells.append(self._make_cell(r, c, size, valid, last_set))
            rows.append(ft.Row(cells, spacing=0))
        self.board_container.content = ft.Column(rows, spacing=0)
        self.board_container.width = size * 8 + 4

    def _make_cell(self, r, c, size, valid, last_set) -> ft.Control:

        """画一格：底色（深浅相间）+ 该格子的棋子或高亮标记。"""
        piece = self.game.get_piece(r, c)
        is_light = (r + c) % 2 == 0
        bgcolor = LIGHT_SQ if is_light else DARK_SQ

        if (r, c) == self.selected_pos:
            bgcolor = SELECTED
        elif (r, c) in last_set:
            bgcolor = LASTMOVE
        if self.game.in_check(self.game.turn) and piece == self.game.turn + "K":
            bgcolor = CHECK_TINT

        img = None
        if piece:
            img = ft.Image(
                src=piece_image_src(piece, self.theme),
                width=size - 6, height=size - 6,
                fit=ft.BoxFit.CONTAIN,
            )
        base = ft.Container(
            content=img, alignment=ft.alignment.Alignment(0, 0),
            width=size, height=size,
        )

        if (r, c) in valid:
            dot = ft.Container(
                width=14 if not piece else size - 10,
                height=14 if not piece else size - 10,
                border_radius=7 if not piece else (size - 10) / 2,
                bgcolor=None if piece else SELECTED,
                border=None if not piece else ft.Border.all(3, SELECTED),
                opacity=0.55,
            )
            base = ft.Stack(
                [
                    ft.Container(content=img, alignment=ft.alignment.Alignment(0, 0),
                                 width=size, height=size),
                    ft.Container(content=dot, alignment=ft.alignment.Alignment(0, 0),
                                 width=size, height=size),
                ],
                width=size, height=size,
            )

        return ft.Container(
            content=base,
            bgcolor=bgcolor,
            width=size, height=size,
            on_click=lambda e, row=r, col=c: self._on_cell_click(row, col),
        )

    # ------------------------------------------------------------------
    def _on_cell_click(self, r: int, c: int):
        # 联网：对手已离场，对局结束，不能再走
        """点格子：判断是选子、落子还是无效操作。"""
        if self.opponent_left:
            self._toast("对局已结束（对手离场）")
            return
        # 联网观战：不能操作棋盘
        if self.net is not None and self.role == "spectator":
            self._toast("你正在观战，不能走子")
            return
        # 联网对局：只能走「轮到自己」的那一方
        if self.net is not None and self.role not in ("w", "b"):
            return
        if self.net is not None and self.role != self.game.turn:
            self._toast("还没轮到你")
            return

        # 1. 已选中棋子且点击合法目标 → 走子（可能需要升变）
        if self.selected_pos:
            fr, fc = self.selected_pos
            if (r, c) in self.game.get_valid_moves(fr, fc):
                piece = self.game.get_piece(fr, fc)
                if piece and piece[1] == "P" and r in (0, 7):
                    self.promotion_pending = (fr, fc, r, c)
                    self._open_promo(piece[0])
                    return
                self._do_move(fr, fc, r, c, None)
                return

        # 2. 选中 / 取消选中自己的棋子
        piece = self.game.get_piece(r, c)
        if piece and piece[0] == self.game.turn:
            self.selected_pos = (r, c)
        else:
            self.selected_pos = None
        self._render_board()
        self.page.update()

    def _do_move(self, fr, fc, tr, tc, promo):

        """真的走这一步：更新局面、记棋谱、通知对手。"""
        color = self.game.turn               # 走子方颜色（走之前）
        ok = self.game.move(fr, fc, tr, tc, promotion=promo)
        if ok:
            self._record_ply(color, fr, fc, tr, tc, promo)
            self.selected_pos = None
            self._render_board()
            self._update_status()
            # 联网：把这一步可靠地发给房间里其他人
            if self.net is not None and self.role in ("w", "b"):
                self.net.send_game({"k": "mv", "fr": fr, "fc": fc,
                                    "tr": tr, "tc": tc, "p": promo or ""})
            self._maybe_save_on_end()

    # ------------------------------------------------------------------
    def _open_promo(self, color: str):

        """兵走到底线：弹出升变选择框（车 / 马 / 象 / 后）。"""
        btns = []
        for pc in PROMO_ORDER:
            code = color + pc
            btns.append(
                ft.Container(
                    content=ft.Image(src=piece_image_src(code, self.theme),
                                     width=46, height=46, fit=ft.BoxFit.CONTAIN),
                    ink=True,
                    on_click=lambda e, p=pc: self._choose_promo(p),
                )
            )
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("选择升变兵种"),
            content=ft.Row(btns, spacing=10, alignment=ft.MainAxisAlignment.CENTER),
            actions=[ft.TextButton("取消", on_click=self._cancel_promo)],
        )
        self.page.show_dialog(dlg)

    def _choose_promo(self, promo: str):

        """玩家选好了升变哪只棋子。"""
        self.page.pop_dialog()
        if self.promotion_pending:
            fr, fc, tr, tc = self.promotion_pending
            self.promotion_pending = None
            self._do_move(fr, fc, tr, tc, promo)

    def _cancel_promo(self, _e):

        """取消升变：把这步撤销。"""
        self.page.pop_dialog()
        self.promotion_pending = None

    # ------------------------------------------------------------------
    def _on_theme_change(self, e):

        """界面主题变了：重画棋盘（配色要跟着换）。"""
        self.theme = e.control.value
        self._render_board()
        self.page.update()

    def _update_status(self):
        # 联网：对手中途离场，直接判在场方获胜
        """刷新顶部状态条（轮到谁 / 局面摘要 / 联机状态）。"""
        if self.opponent_left:
            side = "白方" if self.role == "w" else "黑方"
            self.status_text.value = f"🏁 对方离开，{side}获胜！"
            self.status_text.color = T.DANGER
            self._save_match_log(opponent_left=True)
            self.page.update()
            return
        txt = self.game.status_text()
        color = T.TEXT_PRIMARY
        if self.game.is_checkmate():
            color = T.DANGER
            txt = "🏁 " + txt
        elif self.game.in_check(self.game.turn):
            color = T.WARNING
            txt = "⚠ " + ("白方被将军！" if self.game.turn == "w" else "黑方被将军！")
        self.status_text.value = txt
        self.status_text.color = color
        self.page.update()
