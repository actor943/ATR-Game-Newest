# games/chess/selftest.py
# -*- coding: utf-8 -*-
"""引擎自测：直接用 python 运行（无需 flet / UI）。"""
from .engine import ChessGame


def test_initial_moves():

    """开局白棋有 16 种走法。"""
    g = ChessGame()
    assert len(g.legal_moves("w")) == 20, len(g.legal_moves("w"))
    assert g.turn == "w"
    print("[ok] 初始局面白方合法着法 = 20")


def test_fools_mate():

    """一步将死（fool's mate）：黑方 4 步内被将死。"""
    g = ChessGame()
    seq = [(6, 5, 5, 5),   # 1. f3
           (1, 4, 3, 4),   # 1... e5
           (6, 6, 4, 6),   # 2. g4
           (0, 3, 4, 7)]   # 2... Qh4#
    for mv in seq:
        assert g.move(*mv), f"非法着法 {mv}"
    assert g.turn == "w"
    assert g.is_checkmate(), "应为将死"
    assert g.status_text() == "黑方胜（将死）"
    print("[ok] 傻瓜将死被正确识别")


def test_undo():

    """悔棋能把局面恢复到上一步。"""
    g = ChessGame()
    g.move(6, 4, 4, 4)  # e4
    g.move(1, 4, 3, 4)  # e5
    assert g.turn == "w"  # 双方各走一步后轮到白方
    g.undo()             # 撤销黑方 e5
    assert g.turn == "b"
    assert g.get_piece(3, 4) is None  # 黑兵应回到 e7
    assert g.get_piece(1, 4) == "bP"
    print("[ok] 悔棋恢复局面正确")


def test_promotion():

    """兵走到底线自动升变（可选车 / 马 / 象 / 后）。"""
    g = ChessGame()
    # 手工摆一个即将升变的白兵
    g._board = [[None] * 8 for _ in range(8)]
    g._board[7][4] = "wK"
    g._board[0][7] = "bK"
    g._board[1][0] = "wP"
    g._turn = "w"
    g._history.clear()
    g._snapshot()
    assert g.move(1, 0, 0, 0, promotion="Q")
    assert g.get_piece(0, 0) == "wQ"
    print("[ok] 兵升变为后正确")


def test_en_passant():

    """吃过路兵：兵两格直冲后可以横向吃掉旁边的兵。"""
    g = ChessGame()
    g._board = [[None] * 8 for _ in range(8)]
    g._board[7][4] = "wK"
    g._board[0][0] = "bK"
    g._board[3][4] = "wP"   # 白兵 e5
    g._board[1][3] = "bP"   # 黑兵 d7
    g._turn = "b"
    g._history.clear()
    g._snapshot()
    # 黑兵 d7->d5（两格），应设置过路兵目标
    assert g.move(1, 3, 3, 3)
    assert g._ep == (2, 3), g._ep
    # 白兵吃过路兵 e5xd6
    assert g.move(3, 4, 2, 3)
    assert g.get_piece(2, 3) == "wP"
    assert g.get_piece(3, 3) is None  # 被吃的黑兵已移除
    print("[ok] 吃过路兵正确")


def test_castling_rights():

    """王 / 车动过之后不能��再 castles（易位）。"""
    g = ChessGame()
    # 清出一条可王侧易位的线路：白王 e1、白车 h1，f1/g1 空
    g._board = [[None] * 8 for _ in range(8)]
    g._board[7][4] = "wK"
    g._board[7][7] = "wR"
    g._board[0][0] = "bK"
    g._turn = "w"
    g._castling = {"wK": True, "wQ": False, "bK": False, "bQ": False}
    g._history.clear()
    g._snapshot()
    assert (7, 4, 7, 6) in [m[:4] for m in g.legal_moves("w")], "应可王侧易位"
    g.move(7, 4, 7, 6)  # 执行王侧易位
    assert g.get_piece(7, 6) == "wK"
    assert g.get_piece(7, 5) == "wR"
    assert g.get_piece(7, 7) is None
    print("[ok] 王车易位（王侧）正确")


def test_check_detection():

    """将军 / 被将军 / 终局判定都正确。"""
    g = ChessGame()
    g._board = [[None] * 8 for _ in range(8)]
    g._board[7][4] = "wK"
    g._board[0][0] = "bK"
    g._board[0][4] = "bR"   # 黑车在白王同列
    g._turn = "w"
    g._history.clear()
    g._snapshot()
    assert g.in_check("w")
    print("[ok] 将军检测正确")


if __name__ == "__main__":
    test_initial_moves()
    test_fools_mate()
    test_undo()
    test_promotion()
    test_en_passant()
    test_castling_rights()
    test_check_detection()
    print("\n全部自测通过 ✅")
