"""掼蛋视图：每个路由对应一个 ``build(page, navigate) -> Control`` 函数。"""

from .home_view import build as build_home
from .play_view import build as build_play
from .history_view import build as build_history
from .board_view import build as build_board
from .advisor_view import build as build_advisor
from .simulator_view import build as build_simulator
from .types_view import build as build_types

__all__ = [
    "build_home",
    "build_play",
    "build_history",
    "build_board",
    "build_advisor",
    "build_simulator",
    "build_types",
]