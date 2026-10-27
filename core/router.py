# -*- coding: utf-8 -*-
"""轻量路由：按路径查 ``Registry`` 拿视图，控制单实例化（不依赖 Flet 路由）。"""

from __future__ import annotations

import traceback
from typing import Optional

import flet as ft

from . import registry
from .registry import RouteSpec


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
        try:
            control: ft.Control = spec.builder(self.page, self.navigate)
        except Exception:                     # noqa: BLE001
            # 安全网：视图构建抛异常时，手机端（Android/iOS）会把它当成
            # 未捕获异常 → flet 直接弹 "Error running app" 红屏，整个应用
            # 不可用（0.4.8 联机象棋就是这么崩的：roster() 返回列表却被
            # 当字典调 .values()）。这里兜住：打完整栈、给一张错误页，
            # 应用继续可用，用户能返回上一页。
            traceback.print_exc()
            return self._error_page(spec.path)
        self._cache[spec.path] = control
        return control

    def _error_page(self, path: str) -> ft.Control:
        """视图构建失败时的占位页（不要让它变成红屏）。"""
        return ft.Column(
            [
                ft.Text("页面没能打开", size=18, weight=ft.FontWeight.BOLD),
                ft.Text(f"路径：{path}", size=12),
                ft.Text("详情见运行日志（终端 / ADB logcat）。", size=12),
                ft.Button(content=ft.Text("返回主菜单"),
                          on_click=lambda _e: self.navigate("/")),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )

    def _swap(self, control: ft.Control, path: str) -> None:
        try:
            self.page.controls.clear()
            self.page.add(control)
            self._current_path = path
            self.page.update()
        except Exception:                     # noqa: BLE001
            # 控件本身有问题（渲染期异常）也不能让整app 崩掉
            traceback.print_exc()

    def invalidate(self, path: Optional[str] = None) -> None:
        """强制重建某个（或全部）缓存视图。"""
        if path is None:
            self._cache.clear()
        else:
            self._cache.pop(path, None)
