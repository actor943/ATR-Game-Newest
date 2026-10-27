# games/chess/engine.py
# -*- coding: utf-8 -*-
"""国际象棋规则引擎（无 UI 依赖，可独立单测）。

坐标约定
--------
``board[r][c]`` 为一个 ``8×8`` 的二维表：

* ``r`` ：行（row），``0`` 在最上方（黑方底线 / rank 8），``7`` 在最下方（白方底线 / rank 1）。
* ``c`` ：列（col），``0`` 在最左（a 文件），``7`` 在最右（h 文件）。

格子内容为一个棋子代号字符串，或直接 ``None``（空格）：

* 首字符为颜色：``'w'``（白）/ ``'b'``（黑）。
* 次字符为兵种：``'K'`` 王 / ``'Q'`` 后 / ``'R'`` 车 / ``'B'`` 象 / ``'N'`` 马 / ``'P'`` 兵。

白方向上走（``r`` 减小），黑方向下走（``r`` 增大），符合常见的人类视角。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# 类型别名
Square = Tuple[int, int]          # (row, col)
Move = Tuple[int, int, int, int]  # (fr, fc, tr, tc)
FullMove = Tuple[int, int, int, int, Optional[str]]  # 末项为升变兵种

_KNIGHT_DELTAS = (
    (-2, -1), (-2, 1), (-1, -2), (-1, 2),
    (1, -2), (1, 2), (2, -1), (2, 1),
)
_KING_DELTAS = (
    (-1, -1), (-1, 0), (-1, 1), (0, -1),
    (0, 1), (1, -1), (1, 0), (1, 1),
)
_ORTHO = ((-1, 0), (1, 0), (0, -1), (0, 1))
_DIAG = ((-1, -1), (-1, 1), (1, -1), (1, 1))

# 起始局面
_INITIAL = [
    ["bR", "bN", "bB", "bQ", "bK", "bB", "bN", "bR"],
    ["bP", "bP", "bP", "bP", "bP", "bP", "bP", "bP"],
    [None] * 8,
    [None] * 8,
    [None] * 8,
    [None] * 8,
    ["wP", "wP", "wP", "wP", "wP", "wP", "wP", "wP"],
    ["wR", "wN", "wB", "wQ", "wK", "wB", "wN", "wR"],
]

# 升变默认兵种顺序（用于弹窗）
PROMO_ORDER = ("Q", "R", "B", "N")
_PROMO_NAMES = {"Q": "后", "R": "车", "B": "象", "N": "马"}


def _inside(r: int, c: int) -> bool:
    return 0 <= r < 8 and 0 <= c < 8


def _opp(color: str) -> str:
    return "b" if color == "w" else "w"


def _clone_board(board) -> List[List[Optional[str]]]:
    return [row[:] for row in board]


class ChessGame:
    """可玩的国际象棋对局状态机。

    支持：所有兵种走法、王车易位、吃过路兵、兵的升变、将军 / 将死 /
    困毙（stalemate）判定、以及悔棋（基于整局状态的快照栈）。
    """

    def __init__(self) -> None:
        self._history: List[dict] = []
        self._push_initial()

    # ------------------------------------------------------------------
    # 内部状态管理
    # ------------------------------------------------------------------
    def _push_initial(self) -> None:
        self._board = _clone_board(_INITIAL)
        self._turn = "w"
        self._castling = {"wK": True, "wQ": True, "bK": True, "bQ": True}
        self._ep: Optional[Square] = None          # 可被吃过路兵的目标格
        self._last_move: Optional[FullMove] = None
        self._halfmove = 0
        self._snapshot()

    def _snapshot(self) -> None:
        self._history.append({
            "board": _clone_board(self._board),
            "turn": self._turn,
            "castling": dict(self._castling),
            "ep": self._ep,
            "last_move": self._last_move,
            "halfmove": self._halfmove,
        })

    # ------------------------------------------------------------------
    # 公开只读访问
    # ------------------------------------------------------------------
    @property
    def turn(self) -> str:
        return self._turn

    @property
    def last_move(self) -> Optional[FullMove]:
        return self._last_move

    def get_piece(self, r: int, c: int) -> Optional[str]:
        if not _inside(r, c):
            return None
        return self._board[r][c]

    def in_check(self, color: Optional[str] = None) -> bool:
        color = color or self._turn
        kr, kc = self._find_king(self._board, color)
        if kr is None:
            return False
        return self._is_attacked(self._board, kr, kc, _opp(color))

    def is_checkmate(self) -> bool:
        return self.in_check(self._turn) and not self.legal_moves(self._turn)

    def is_stalemate(self) -> bool:
        return (not self.in_check(self._turn)) and not self.legal_moves(self._turn)

    def is_game_over(self) -> bool:
        return bool(self.legal_moves(self._turn)) is False

    def status_text(self) -> str:
        if self.is_checkmate():
            return ("黑方胜（将死）" if self._turn == "w" else "白方胜（将死）")
        if self.is_stalemate():
            return "和棋（困毙）"
        return "白方走棋" if self._turn == "w" else "黑方走棋"

    # ------------------------------------------------------------------
    # 走法生成
    # ------------------------------------------------------------------
    def get_valid_moves(self, r: int, c: int) -> List[Square]:
        """返回从 (r, c) 出发的全部合法目标格。"""
        piece = self.get_piece(r, c)
        if not piece or piece[0] != self._turn:
            return []
        targets = []
        for mv in self.legal_moves(self._turn):
            if mv[0] == r and mv[1] == c:
                targets.append((mv[2], mv[3]))
        return targets

    def legal_moves(self, color: str) -> List[FullMove]:
        """生成 ``color`` 方所有「走后己方王不被将军」的合法着法。"""
        pseudo = self._pseudo_moves(color)
        legal: List[FullMove] = []
        for mv in pseudo:
            nb = self._apply(self._board, self._castling, self._ep, mv)
            kr, kc = self._find_king(nb["board"], color)
            if kr is None:
                continue
            if not self._is_attacked(nb["board"], kr, kc, _opp(color)):
                legal.append(mv)
        return legal

    def _pseudo_moves(self, color: str) -> List[FullMove]:
        moves: List[FullMove] = []
        for r in range(8):
            for c in range(8):
                p = self._board[r][c]
                if not p or p[0] != color:
                    continue
                kind = p[1]
                if kind == "P":
                    moves += self._pawn_moves(r, c, color)
                elif kind == "N":
                    for dr, dc in _KNIGHT_DELTAS:
                        self._try_step(moves, r, c, r + dr, c + dc, color)
                elif kind == "K":
                    for dr, dc in _KING_DELTAS:
                        self._try_step(moves, r, c, r + dr, c + dc, color)
                    moves += self._castling_moves(r, c, color)
                elif kind in ("B", "R", "Q"):
                    dirs = []
                    if kind in ("B", "Q"):
                        dirs += _DIAG
                    if kind in ("R", "Q"):
                        dirs += _ORTHO
                    for dr, dc in dirs:
                        nr, nc = r + dr, c + dc
                        while _inside(nr, nc):
                            tgt = self._board[nr][nc]
                            if tgt is None:
                                moves.append((r, c, nr, nc, None))
                            else:
                                if tgt[0] != color:
                                    moves.append((r, c, nr, nc, None))
                                break
                            nr += dr
                            nc += dc
        return moves

    def _try_step(self, moves, fr, fc, tr, tc, color) -> None:
        if not _inside(tr, tc):
            return
        tgt = self._board[tr][tc]
        if tgt is None or tgt[0] != color:
            moves.append((fr, fc, tr, tc, None))

    def _pawn_moves(self, r, c, color) -> List[FullMove]:
        moves: List[FullMove] = []
        dr = -1 if color == "w" else 1
        start_row = 6 if color == "w" else 1
        promo_row = 0 if color == "w" else 7

        # 前进一格
        nr = r + dr
        if _inside(nr, c) and self._board[nr][c] is None:
            if nr == promo_row:
                for pc in PROMO_ORDER:
                    moves.append((r, c, nr, c, pc))
            else:
                moves.append((r, c, nr, c, None))
                # 前进两格
                if r == start_row:
                    nr2 = r + 2 * dr
                    if self._board[nr2][c] is None:
                        moves.append((r, c, nr2, c, None))

        # 吃子（含吃过路兵）
        for dc in (-1, 1):
            nc = c + dc
            if not _inside(nr, nc):
                continue
            tgt = self._board[nr][nc]
            if tgt is not None and tgt[0] != color:
                if nr == promo_row:
                    for pc in PROMO_ORDER:
                        moves.append((r, c, nr, nc, pc))
                else:
                    moves.append((r, c, nr, nc, None))
            elif self._ep == (nr, nc):
                # 吃过路兵：目标格为空，但落子是斜前方、且正对过路兵
                moves.append((r, c, nr, nc, None))
        return moves

    def _castling_moves(self, r, c, color) -> List[FullMove]:
        moves: List[FullMove] = []
        if color == "w" and r != 7:
            return moves
        if color == "b" and r != 0:
            return moves
        enemy = _opp(color)
        kside = "wK" if color == "w" else "bK"
        qside = "wQ" if color == "w" else "bQ"
        # 王本身不能被将军、且不能经过被攻击的格
        if self._is_attacked(self._board, r, c, enemy):
            return moves
        # 王侧：f/g 空，e1->g1（白）
        if self._castling.get(kside):
            if (self._board[r][5] is None and self._board[r][6] is None
                    and self._board[r][7] == color + "R"):
                if (not self._is_attacked(self._board, r, 5, enemy)
                        and not self._is_attacked(self._board, r, 6, enemy)):
                    moves.append((r, c, r, 6, None))
        # 后侧：b/c/d 空，e1->c1
        if self._castling.get(qside):
            if (self._board[r][1] is None and self._board[r][2] is None
                    and self._board[r][3] is None
                    and self._board[r][0] == color + "R"):
                if (not self._is_attacked(self._board, r, 3, enemy)
                        and not self._is_attacked(self._board, r, 2, enemy)):
                    moves.append((r, c, r, 2, None))
        return moves

    # ------------------------------------------------------------------
    # 应用走法（纯函数，返回新状态字典）
    # ------------------------------------------------------------------
    def _apply(self, board, castling, ep, mv: FullMove) -> dict:
        fr, fc, tr, tc, promo = mv
        nb = _clone_board(board)
        piece = nb[fr][fc]
        color = piece[0]
        nb[fr][fc] = None

        new_ep: Optional[Square] = None
        # 吃过路兵：斜吃到空格
        if piece[1] == "P" and fc != tc and board[tr][tc] is None:
            # 被吃掉的兵在 (fr, tc)
            nb[fr][tc] = None
        # 兵走两格 → 设置过路兵目标
        if piece[1] == "P" and abs(tr - fr) == 2:
            new_ep = ((fr + tr) // 2, tc)

        # 王车易位：同步移动车
        if piece[1] == "K" and abs(tc - fc) == 2:
            if tc > fc:  # 王侧
                nb[tr][5] = nb[tr][7]
                nb[tr][7] = None
            else:         # 后侧
                nb[tr][3] = nb[tr][0]
                nb[tr][0] = None

        # 落子 / 升变
        if piece[1] == "P" and tr in (0, 7):
            nb[tr][tc] = color + (promo or "Q")
        else:
            nb[tr][tc] = piece

        # 更新易位权
        ncas = dict(castling)
        if piece[1] == "K":
            ncas[color + "K"] = False
            ncas[color + "Q"] = False
        if (fr, fc) == (7, 0):
            ncas["wQ"] = False
        if (fr, fc) == (7, 7):
            ncas["wK"] = False
        if (fr, fc) == (0, 0):
            ncas["bQ"] = False
        if (fr, fc) == (0, 7):
            ncas["bK"] = False
        # 车在原位被吃也剥夺易位权
        if (tr, tc) == (7, 0):
            ncas["wQ"] = False
        if (tr, tc) == (7, 7):
            ncas["wK"] = False
        if (tr, tc) == (0, 0):
            ncas["bQ"] = False
        if (tr, tc) == (0, 7):
            ncas["bK"] = False

        return {"board": nb, "castling": ncas, "ep": new_ep}

    # ------------------------------------------------------------------
    # 对外操作
    # ------------------------------------------------------------------
    def move(self, fr: int, fc: int, tr: int, tc: int,
             promotion: Optional[str] = None) -> bool:
        """执行一步合法走法；成功返回 ``True``，非法返回 ``False``。"""
        piece = self.get_piece(fr, fc)
        if not piece or piece[0] != self._turn:
            return False
        candidates = [
            mv for mv in self.legal_moves(self._turn)
            if mv[0] == fr and mv[1] == fc and mv[2] == tr and mv[3] == tc
        ]
        if not candidates:
            return False

        # 升变分支：优先采用用户指定兵种，否则默认升变为「后」
        if promotion:
            chosen = next((mv for mv in candidates if mv[4] == promotion), candidates[0])
        else:
            chosen = next((mv for mv in candidates if mv[4] == "Q"), candidates[0])
            if chosen[4] is None:
                chosen = candidates[0]
        if chosen is None:
            return False

        res = self._apply(self._board, self._castling, self._ep, chosen)
        self._board = res["board"]
        self._castling = res["castling"]
        self._ep = res["ep"]
        self._last_move = chosen
        self._turn = _opp(self._turn)
        self._halfmove += 1
        self._snapshot()
        return True

    def undo(self) -> bool:
        """悔棋：回退一步。成功返回 ``True``。"""
        if len(self._history) <= 1:
            return False
        self._history.pop()  # 丢弃当前快照
        prev = self._history[-1]
        self._board = _clone_board(prev["board"])
        self._turn = prev["turn"]
        self._castling = dict(prev["castling"])
        self._ep = prev["ep"]
        self._last_move = prev["last_move"]
        self._halfmove = prev["halfmove"]
        return True

    def reset(self) -> None:
        """重开一局。"""
        self._history.clear()
        self._push_initial()

    # ------------------------------------------------------------------
    # 网络同步：把整盘局面序列化 / 还原（用于迟到者追平局面）
    # ------------------------------------------------------------------
    def serialize(self) -> Dict[str, Any]:
        """导出当前完整局面（可被 JSON 编码）。"""
        return {
            "board": [row[:] for row in self._board],
            "turn": self._turn,
            "castling": dict(self._castling),
            "ep": list(self._ep) if self._ep is not None else None,
            "last_move": list(self._last_move) if self._last_move else None,
            "halfmove": self._halfmove,
        }

    def load_state(self, d: Dict[str, Any]) -> None:
        """从 ``serialize`` 的结果还原局面，并保留悔棋能力。"""
        board = d["board"]
        self._board = [[(cell if cell is not None else None) for cell in row]
                       for row in board]
        self._turn = d["turn"]
        self._castling = dict(d.get("castling",
                                   {"wK": True, "wQ": True,
                                    "bK": True, "bQ": True}))
        ep = d.get("ep")
        self._ep = tuple(ep) if isinstance(ep, (list, tuple)) else ep
        lm = d.get("last_move")
        self._last_move = tuple(lm) if isinstance(lm, (list, tuple)) else lm
        self._halfmove = int(d.get("halfmove", 0))
        # 重建历史快照，让后续悔棋仍可用
        self._history = [{
            "board": _clone_board(self._board), "turn": self._turn,
            "castling": dict(self._castling), "ep": self._ep,
            "last_move": self._last_move, "halfmove": self._halfmove,
        }]

    # ------------------------------------------------------------------
    # 攻击 / 王位置查询
    # ------------------------------------------------------------------
    def _find_king(self, board, color: str) -> Tuple[Optional[int], Optional[int]]:
        target = color + "K"
        for r in range(8):
            for c in range(8):
                if board[r][c] == target:
                    return r, c
        return None, None

    def _is_attacked(self, board, r: int, c: int, by: str) -> bool:
        # 兵：白兵在下方、向上吃，故攻击 (r-1, c±1)；黑兵反之
        for dc in (-1, 1):
            rr = r + (1 if by == "w" else -1)
            cc = c + dc
            if _inside(rr, cc) and board[rr][cc] == by + "P":
                return True
        # 马
        for dr, dc in _KNIGHT_DELTAS:
            rr, cc = r + dr, c + dc
            if _inside(rr, cc) and board[rr][cc] == by + "N":
                return True
        # 王（贴身）
        for dr, dc in _KING_DELTAS:
            rr, cc = r + dr, c + dc
            if _inside(rr, cc) and board[rr][cc] == by + "K":
                return True
        # 车 / 后：正交滑动
        for dr, dc in _ORTHO:
            rr, cc = r + dr, c + dc
            while _inside(rr, cc):
                p = board[rr][cc]
                if p is not None:
                    if p[0] == by and p[1] in ("R", "Q"):
                        return True
                    break
                rr += dr
                cc += dc
        # 象 / 后：斜向滑动
        for dr, dc in _DIAG:
            rr, cc = r + dr, c + dc
            while _inside(rr, cc):
                p = board[rr][cc]
                if p is not None:
                    if p[0] == by and p[1] in ("B", "Q"):
                        return True
                    break
                rr += dr
                cc += dc
        return False

    # ------------------------------------------------------------------
    # 调试 / 渲染辅助
    # ------------------------------------------------------------------
    def board_copy(self):
        return _clone_board(self._board)

    def __str__(self) -> str:
        rows = []
        for r in range(8):
            row = []
            for c in range(8):
                p = self._board[r][c]
                row.append(p if p else "..")
            rows.append(" ".join(row))
        return "\n".join(rows)
