"""框架自带的核心视图（不属于任何具体游戏）。"""

from .menu_view import build as build_menu
from .multiplayer_view import build as build_multiplayer
from .profile_view import build as build_profile
from .room_view import build as build_room
from .settings_view import build as build_settings
from .single_view import build as build_single

__all__ = [
    "build_menu",
    "build_multiplayer",
    "build_profile",
    "build_room",
    "build_settings",
    "build_single",
]
