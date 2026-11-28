# -*- coding: utf-8 -*-
"""3D 台球：规则菜单 + 平台分流。

* Android / iOS / macOS：用 ``flet-webview`` 把台球页面作为全屏控件嵌进应用，
  没有 Flet 顶部栏，手机与桌面体验一致；
* Windows / Linux：官方 WebView 扩展不支持，退回 :mod:`standalone` 独立窗口。

两种路径跑的是同一份精简后的 TypeScript 静态资源。
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import flet as ft

from core.i18n import t
from core.registry import NavigateFn
from core.theme import T
from core.ui_common import app_bar, grid_cards, menu_card, page_padding

from .local_server import game_url

try:
    from flet_webview import WebView
except ImportError:  # 没装扩展时也能用独立窗口路径
    WebView = None  # type: ignore[assignment]

# key, URL 参数, 图标, 英文兜底名
_GAMES = [
    ("nineball", "", "🎱", "9-Ball"),
    ("eightball", "ruletype=eightball", "🎯", "8-Ball"),
    # 中八：上游重建后的 Chinese8Ball 规则（本地双人 1P/2P 分组）
    ("chinese8", "ruletype=chinese8", "🇨🇳", "Chinese 8-Ball"),
    ("threecushion", "ruletype=threecushion", "🧊", "Three Cushion"),
    ("snooker", "ruletype=snooker", "🏆", "Snooker"),
    ("practice", "ruletype=eightball&practice", "📈", "Practice"),
    ("sagu", "ruletype=sagu", "🏅", "Sagu"),
]

# 多人游戏从房间进来不走模式设置，直接开自由摆球（练习模式）
_FREE_PRACTICE_PARAMS = "ruletype=eightball&practice"
_FREE_PRACTICE_NAME = "自由摆球"

_IN_APP_PLATFORMS = {
    ft.PagePlatform.ANDROID,
    ft.PagePlatform.IOS,
    ft.PagePlatform.MACOS,
}

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
# 每个 page 当前选择的规则：id(page) -> (params, title)
_state: dict[int, tuple[str, str]] = {}
# 多人 / 非内嵌平台：每次进对局只拉起一次独立窗口
_standalone_launched: set[int] = set()


def _can_embed(page: ft.Page) -> bool:
    return WebView is not None and page.platform in _IN_APP_PLATFORMS


def _python_cmd() -> list[str]:
    if not getattr(sys, "frozen", False):
        return [sys.executable]
    exe = Path(sys.executable).resolve()
    for candidate in (
        exe.parent / "python",
        exe.parent / "python3",
        exe.parent.parent / "Resources" / "bin" / "python3",
    ):
        if candidate.is_file():
            return [str(candidate)]
    return [sys.executable]


def _launch_standalone(params: str, title: str, *, page: ft.Page | None = None,
                       follow: bool = False) -> None:
    cmd = [*_python_cmd(), "-m", "games.billiards3d.standalone", params, title]
    if follow and page is not None:
        # Windows / Linux：开无边框窗口并跟随主窗口，观感接近内嵌。
        from .geometry import start as start_geometry
        cmd += [start_geometry(page), "1"]
    try:
        subprocess.Popen(cmd, cwd=str(_PROJECT_ROOT))
    except OSError as exc:
        raise RuntimeError(
            t("billiards3d.launch_failed",
              default="无法启动 3D 台球独立窗口：{err}").format(err=exc)
        ) from exc


def _license_dialog() -> ft.AlertDialog:
    return ft.AlertDialog(
        modal=True,
        title=ft.Text(t("billiards3d.license", default="开源许可 GPL-3.0")),
        content=ft.Text(
            t("billiards3d.license_text",
              default="台球引擎来自 tailuge/billiards（GPL-3.0）。"
                      "完整源码与许可证见项目 third_party/billiards/。"),
            size=13,
        ),
        actions=[ft.Button("OK", on_click=lambda _e: _pop_dialog())],
    )


_page_ref: dict[int, ft.Page] = {}


def _pop_dialog() -> None:
    for page in _page_ref.values():
        try:
            page.pop_dialog()
        except Exception:  # noqa: BLE001
            pass


def build_home(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """规则菜单：支持内嵌的平台进入全屏页，其余平台拉起独立窗口。"""
    _page_ref[id(page)] = page
    _standalone_launched.discard(id(page))

    def _on_rule(params: str, name: str):
        def _handler(_e) -> None:
            if _can_embed(page):
                _state[id(page)] = (params, name)
                navigate("/g/billiards3d/play")
                return
            try:
                _launch_standalone(params, f"3D 台球 · {name}",
                                   page=page, follow=True)
            except Exception as exc:  # noqa: BLE001
                page.show_dialog(ft.AlertDialog(
                    modal=True,
                    title=ft.Text(t("route.billiards3d", default="3D 台球")),
                    content=ft.Text(str(exc), size=13),
                    actions=[ft.Button("OK", on_click=lambda _e: _pop_dialog())],
                ))

        return _handler

    cards = []
    for key, params, icon, fallback_title in _GAMES:
        title = t(f"billiards3d.{key}", default=fallback_title)
        desc = t(f"billiards3d.{key}.desc", default="")
        cards.append(
            menu_card(title, desc, icon, on_click=_on_rule(params, title))
        )

    body = ft.Column(
        [
            ft.Text(
                t("billiards3d.intro",
                  default="开源 3D 台球：真实物理、完整网页版界面，本地资源运行。"),
                size=13,
                color=T.TEXT_SECONDARY,
            ),
            ft.Container(height=12),
            grid_cards(page, cards, ideal_w=300, spacing=16, max_cols=3),
            ft.Container(height=12),
            ft.Text(
                t("billiards3d.hint",
                  default="手机 / macOS 在游戏内全屏显示；Windows / Linux 会打开独立窗口。"),
                size=11,
                color=T.TEXT_MUTED,
            ),
        ],
        spacing=0,
    )
    return ft.Column(
        [
            app_bar(
                t("route.billiards3d", default="3D 台球"),
                on_back=lambda _e: navigate("/"),
                actions=[
                    ft.IconButton(
                        icon=ft.Icons.GAVEL,
                        tooltip=t("billiards3d.license", default="开源许可 GPL-3.0"),
                        on_click=lambda _e: page.show_dialog(_license_dialog()),
                    )
                ],
            ),
            page_padding(body),
        ],
        expand=True,
    )


_overlay_ref: dict[int, ft.Control] = {}
_prev_scroll: dict[int, object] = {}
# 每个 page 只提示一次本地资源错误；外链失败不打扰用户
_resource_warned: set[int] = set()


def _detach_back(page: ft.Page) -> None:
    overlay = _overlay_ref.pop(id(page), None)
    if overlay is None:
        return
    try:
        if overlay in page.overlay:
            page.overlay.remove(overlay)
            page.update()
    except Exception:  # noqa: BLE001
        pass


def build_play(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """全屏台球页：WebView 直接作为根控件，返回键走 overlay。

    0.5：多人房间点「开始」也走这里。房间内不做模式设置，一律直接进入
    自由摆球（上游的 practice 模式），保证房主和客人的画面一致。
    """
    from core.net import session as _sess

    in_room = _sess.current() is not None
    params, name = _state.get(id(page), ("", ""))
    if in_room or not params:
        params, name = _FREE_PRACTICE_PARAMS, _FREE_PRACTICE_NAME
        _state[id(page)] = (params, name)

    if not _can_embed(page):
        # Windows / Linux 没有内嵌 WebView：多人也照常把自由摆球开起来，
        # 只是走独立原生窗口；这里留一个可返回的说明页，而不是打回菜单。
        if not in_room:
            return build_home(page, navigate)
        pid = id(page)
        if pid not in _standalone_launched:
            _standalone_launched.add(pid)
            try:
                _launch_standalone(params, f"3D 台球 · {name}",
                                   page=page, follow=True)
            except Exception as exc:                  # noqa: BLE001
                _standalone_launched.discard(pid)
                return ft.Column(
                    [
                        app_bar("3D 台球", on_back=lambda _e: navigate("/room")),
                        page_padding(ft.Text(str(exc), size=13)),
                    ],
                    expand=True,
                )
        return ft.Column(
            [
                app_bar("3D 台球 · 自由摆球",
                        on_back=lambda _e: navigate("/room")),
                page_padding(ft.Column(
                    [
                        ft.Text("已在独立窗口打开 3D 台球（自由摆球）。",
                                size=14),
                        ft.Container(height=8),
                        ft.Text("多人房间保持连接；返回这里可回到房间。",
                                size=12, color=T.TEXT_MUTED),
                    ],
                    spacing=0,
                )),
            ],
            expand=True,
        )

    # 真实 App 在 app.run 里把 page.scroll 设成了 AUTO；WebView 作为可滚动
    # 页面的子控件在 macOS 上会拿到零高度，表现就是整页白屏。进游戏时临时
    # 关掉，返回时恢复。
    _prev_scroll[id(page)] = page.scroll
    page.scroll = None
    page.update()

    def _back(_e) -> None:
        from core.router import Router
        _detach_back(page)
        _resource_warned.discard(id(page))
        page.scroll = _prev_scroll.pop(id(page), ft.ScrollMode.AUTO)
        page.update()
        if Router.current is not None:
            Router.current.invalidate("/g/billiards3d/play")
        navigate("/room" if in_room else "/g/billiards3d")

    # 返回键不能和 WebView 一起放进 Stack：实测那样动态加入后原生 WebView
    # 收不到 load_request。挂 page.overlay 不影响导航，也不会出现 Flet 顶栏。
    _detach_back(page)
    back = ft.Container(
        content=ft.IconButton(
            icon=ft.Icons.ARROW_BACK,
            tooltip=("返回房间" if in_room else
                     t("billiards3d.back", default="返回规则菜单")),
            on_click=_back,
            bgcolor=T.SURFACE,
        ),
        top=12,
        left=12,
    )
    _overlay_ref[id(page)] = back
    page.overlay.append(back)

    def _resource_error(e) -> None:
        data = str(getattr(e, "data", e))
        # 上游网页里有 Google 字体、About 外链等：离线时必然报错，但游戏
        # 本身完全跑本地资源，不该让用户看到「台球资源加载失败」弹窗。
        if "127.0.0.1" not in data and not data.startswith("/"):
            return
        pid = id(page)
        if pid in _resource_warned:
            return
        _resource_warned.add(pid)

        def _close(_e):
            _pop_dialog()
            _resource_warned.discard(pid)

        try:
            page.show_dialog(ft.AlertDialog(
                modal=True,
                title=ft.Text(t("billiards3d.load_failed", default="资源加载失败")),
                content=ft.Text(data, size=12),
                actions=[ft.Button("OK", on_click=_close)],
            ))
        except Exception:  # noqa: BLE001
            _resource_warned.discard(pid)

    url = game_url(params)
    webview = WebView(
        url=url,
        expand=True,
        # 右上角 Anon 胶囊已用 CSS 隐藏；再拦一层，防止误触跳到外网大厅。
        prevent_links=["https://billiards.tailuge.workers.dev/"],
        on_web_resource_error=_resource_error,
    )

    # 动态加入的 WebView 不消费构造时的 url，必须挂载后显式 load_request。
    async def _load() -> None:
        for _ in range(50):
            if webview.page is not None:
                break
            await asyncio.sleep(0.1)
        if webview.page is not None:
            await asyncio.sleep(0.5)
            await webview.load_request(url)

    page.run_task(_load)
    return webview
