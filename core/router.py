# -*- coding: utf-8 -*-
"""轻量路由：按路径查 ``Registry`` 拿视图，控制单实例化（不依赖 Flet 路由）。"""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from . import registry
from .registry import NavigateFn, RouteSpec


class Router:
    """负责「根据路径显示对应视图」。

    设计上不直接绑 ``page.on_route_change``，而是把 ``navigate(path)`` 暴露给
    所有视图使用，方便测试和将来脱离 flet 路由。
    """

    # 进程内当前路由器实例；视图（如设置页）可借它强制重建界面。
    current: Optional["Router"] = None

    def __init__(self, page: ft.Page):
        self.page = page
        self._cache: dict[str, ft.Control] = {}
        self._current_path: str = ""
        Router.current = self

    # ---- 公开接口 ----

    def navigate(self, path: str) -> None:
        """跳转到指定路径。同一路径的视图会缓存，状态保留。"""
        spec = registry.get_route(path)
        if spec is None:
            # 回退到主菜单
            spec = registry.get_route("/")
            if spec is None:
                return
            path = spec.path
        control = self._get_or_build(spec)
        self._swap(control, path)

    def current_path(self) -> str:
        return self._current_path

    # ---- 内部 ----

    def _get_or_build(self, spec: RouteSpec) -> ft.Control:
        cached = self._cache.get(spec.path)
        if cached is not None:
            return cached
        control: ft.Control = spec.builder(self.page, self.navigate)
        self._cache[spec.path] = control
        return control

    def _swap(self, control: ft.Control, path: str) -> None:
        self.page.controls.clear()
        self.page.add(control)
        self._current_path = path
        self.page.update()

    def invalidate(self, path: Optional[str] = None) -> None:
        """强制重建某个（或全部）缓存视图。"""
        if path is None:
            self._cache.clear()
        else:
            self._cache.pop(path, None)
