# -*- coding: utf-8 -*-
"""轻量路由：按路径查 ``Registry`` 拿视图，控制单实例化（不依赖 Flet 路由）。"""

from __future__ import annotations

import traceback
from typing import Optional

import flet as ft

from . import registry
from . import responsive
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
            # 视图根 Column 默认只给子控件「固有宽度」：顶栏、卡片列都缩在
            # 屏幕左侧。统一在这里改成 STRETCH，所有页面一行不用改就铺满。
            responsive.stretch_root(control)
            self.page.controls.clear()
            self.page.add(control)
            self._current_path = path
            self.page.update()
        except Exception:                     # noqa: BLE001
            # 控件本身有问题（渲染期异常）也不能让整app 崩掉
            traceback.print_exc()

    def reflow(self, is_safe) -> None:
        """窗口尺寸变了：只重建「无状态」的缓存页，绝不打断正在玩的对局。

        ``is_safe(path)`` 由 :func:`core.responsive.is_static_route` 提供。
        对局页 / 房间页的缓存保留原样（它们自己订阅 resize 原地改尺寸）；
        当前正好停在静态页时，丢掉缓存立刻重建，卡片列数跟着新宽度走。
        """
        for path in list(self._cache):
            if is_safe(path):
                self._cache.pop(path, None)
        path = self._current_path
        if path and is_safe(path):
            self.navigate(path)

    def invalidate(self, path: Optional[str] = None) -> None:
        """强制重建某个（或全部）缓存视图。"""
        if path is None:
            self._cache.clear()
        else:
            self._cache.pop(path, None)
