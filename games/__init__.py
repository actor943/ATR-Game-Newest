"""游戏插件包。

每个子包（``guandan`` / 未来 ``doudizhu`` 等）实现 :class:`GamePlugin` 协议
并在本包 import 时通过 ``registry.register_game`` 自动注册。
"""

from core.registry import (  # noqa: F401
    GamePlugin,
    MenuItem,
    NavigateFn,
    RouteSpec,
    ViewBuilder,
    add_menu_item,
    add_route,
    all_routes,
    get_route,
    menu_items,
    register_game,
    reset as reset_registry,
)

# 触发各游戏的注册（import 即注册）
from . import guandan  # noqa: F401
# 占位子游戏：只有名字与插件框架，游戏逻辑尚未实现
from . import splendor, chess, chinese_chess  # noqa: F401

__all__ = [
    "GamePlugin",
    "MenuItem",
    "RouteSpec",
    "register_game",
    "menu_items",
    "get_route",
    "all_routes",
    "reset_registry",
]
