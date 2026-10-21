"""核心框架层：路由、主题、UI 组件、设置、游戏注册表。

``core`` 不依赖任何具体游戏；游戏通过 ``games/<id>/`` 子包按插件协议注册。
"""

from .registry import (  # noqa: F401
    GamePlugin,
    MenuItem,
    NavigateFn,
    RouteSpec,
    ViewBuilder,
    add_menu_item,
    add_route,
    get_route,
    menu_items,
    register_game,
)

__all__ = [
    "GamePlugin",
    "MenuItem",
    "NavigateFn",
    "RouteSpec",
    "ViewBuilder",
    "register_game",
    "add_menu_item",
    "add_route",
    "get_route",
    "menu_items",
]
