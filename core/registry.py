# -*- coding: utf-8 -*-
"""游戏插件注册表。

任何具体游戏（掼蛋、跳刀、斗地主……）都通过本模块注册：

* :func:`register_game` 把一个 :class:`GamePlugin` 加入全局表
* :func:`get_route` / :func:`menu_items` 用于路由层查询

注册表本身**不依赖 flet**，方便单测和命令行工具复用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import flet as ft

# ============================================================
# 协议
# ============================================================

# 一个视图构建器：拿到当前 Page 与 navigate 钩子，返回一个 flet Control。
NavigateFn = Callable[[str], None]
ViewBuilder = Callable[[ft.Page, NavigateFn], ft.Control]


@dataclass(frozen=True)
class RouteSpec:
    """一条路由：路径 + 标题 + 构建器。

    ``title`` 是写死的兜底文案；想让标题跟着语言走就再给 ``title_key``
    （见 :mod:`core.i18n`），取标题一律用 :attr:`label`。
    """

    path: str           # 例如 "/g/guandan/board"
    title: str          # 显示在顶栏与菜单
    builder: ViewBuilder
    group: str = ""     # 用于面包屑/分组（可选）
    title_key: str = ""  # i18n 键；给了就用当前语言翻译 title

    @property
    def label(self) -> str:
        """当前语言下的标题（没登记 title_key 就用写死的 title）。"""
        if not self.title_key:
            return self.title
        from core.i18n import t
        return t(self.title_key, default=self.title)


@dataclass(frozen=True)
class MenuItem:
    """主菜单上的一张卡：代表一款游戏。"""

    id: str
    title: str
    icon: str           # emoji 或图标名
    description: str
    available: bool = True
    home_path: str = ""  # 点击后跳到的子菜单路径
    title_key: str = ""  # i18n 键（标题）
    desc_key: str = ""   # i18n 键（说明）

    @property
    def label(self) -> str:
        """当前语言下的卡名。"""
        if not self.title_key:
            return self.title
        from core.i18n import t
        return t(self.title_key, default=self.title)

    @property
    def desc(self) -> str:
        """当前语言下的卡说明。"""
        if not self.desc_key:
            return self.description
        from core.i18n import t
        return t(self.desc_key, default=self.description)


@dataclass(frozen=True)
class GamePlugin:
    """游戏插件的最小契约。

    每个 ``games/<id>/`` 子包导出一个满足本结构的实例，并通过
    :func:`register_game` 把自己挂到全局表上。
    """

    id: str
    menu_item: MenuItem
    routes: list[RouteSpec]
    # 该游戏「上场」所需的玩家数；多于这个数的人进房间后即为观战。
    # 默认 4（掼蛋这类 4 人局），棋类通常填 2。
    players: int = 4


# ============================================================
# 全局注册表（进程内单例）
# ============================================================

_menu_items: list[MenuItem] = []
_routes: list[RouteSpec] = []
_route_index: dict[str, RouteSpec] = {}
_game_players: dict[str, int] = {}


def add_menu_item(item: MenuItem) -> None:
    """主菜单：注册一张游戏卡。"""
    _menu_items.append(item)


def add_route(spec: RouteSpec) -> None:
    """注册一条路由。同一 path 重复注册会覆盖。"""
    _route_index[spec.path] = spec
    # 同步列表（去重旧的同 path 项）
    _routes[:] = [r for r in _routes if r.path != spec.path]
    _routes.append(spec)


def register_game(plugin: GamePlugin) -> None:
    """一键注册一款游戏：添加它的菜单项与所有路由。"""
    add_menu_item(plugin.menu_item)
    for spec in plugin.routes:
        add_route(spec)
    _game_players[plugin.id] = plugin.players


def game_players(game_id: str) -> int:
    """该游戏上场所需的玩家数（默认 4）。"""
    return _game_players.get(game_id, 4)


def menu_items() -> list[MenuItem]:
    return list(_menu_items)


def get_route(path: str) -> Optional[RouteSpec]:
    return _route_index.get(path)


def all_routes() -> list[RouteSpec]:
    return list(_routes)


def reset() -> None:
    """清空注册表（仅用于测试）。"""
    _menu_items.clear()
    _routes.clear()
    _route_index.clear()
