# -*- coding: utf-8 -*-
"""应用入口：配置 Page、注册核心路由、启动路由。"""

from __future__ import annotations

import flet as ft

# 触发游戏插件的注册（import 即注册）
import games  # noqa: F401

from core import registry
from core import theme
from core import ui_theme
from core.router import Router
from core.settings import Settings
from core.window import apply_window_mode
from core.views import (
    build_menu,
    build_multiplayer,
    build_profile,
    build_room,
    build_settings,
    build_single,
)

# 应用名（窗口标题 / Dock / 设置目录都用它）
APP_NAME = "ATR Game"
APP_VERSION = "0.4.7"


def _register_core_routes() -> None:
    """核心框架自带的路由：主菜单 / 单人 / 多人 / 房间 / 我的 / 设置。"""
    registry.add_route(registry.RouteSpec("/", APP_NAME, build_menu))
    registry.add_route(registry.RouteSpec("/single", "单人游戏", build_single))
    registry.add_route(registry.RouteSpec("/multiplayer", "多人游戏",
                                          build_multiplayer))
    # 房间详情页：从全局会话里取当前房间（core.net.session.current）
    registry.add_route(registry.RouteSpec("/room", "多人房间", build_room))
    registry.add_route(registry.RouteSpec("/profile", "我的", build_profile))
    registry.add_route(registry.RouteSpec("/settings", "设置", build_settings))


def run(page: ft.Page) -> None:
    """主入口。``ft.run(run)`` 启动后会调用本函数。"""
    page.title = APP_NAME
    page.padding = 0
    page.scroll = ft.ScrollMode.AUTO

    # 应用持久化的主题与窗口模式（设置页切换后写回 settings.json）
    settings = Settings.load()
    theme.set_mode(settings.theme)
    # 按设置穿上界面风格（默认材料风 / 暗黑2 石砖风 / 以后的社区包）
    ui_theme.ensure_loaded()
    theme.apply_to_page(page)
    apply_window_mode(page, settings)

    _register_core_routes()

    router = Router(page)
    router.navigate("/")
