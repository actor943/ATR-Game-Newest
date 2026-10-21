# -*- coding: utf-8 -*-
"""设置视图：主题 / 界面风格 / 快捷键提示 / 窗口模式 / 路径展示。

**界面风格**（0.4.7 新增）
--------------------------
列出 :func:`core.ui_theme.all_packs` 里注册的所有界面包：默认材料风、
暗黑2/MC 石砖风，以后社区包往 ``core/ui_packs/`` 里一注册就会出现在这里。
选中后立即：写回设置 → 覆写 ``theme.T`` → 清掉全部路由缓存 → 重建当前页，
所以整个应用（含掼蛋牌桌）当场换皮，不需要重启。
"""

from __future__ import annotations

import flet as ft

from core import theme
from core import ui_theme as ui
from core.registry import NavigateFn
from core.router import Router
from core.settings import Settings, _config_dir
from core.theme import T
from core.ui_common import app_bar, page_padding
from core.window import (
    MODE_LABELS,
    MODES,
    apply_window_mode,
    normalize,
)


def _section_title(text: str) -> ft.Container:
    return ft.Container(
        padding=ft.Padding.only(top=12, bottom=4),
        content=ft.Text(text, size=12, weight=ft.FontWeight.BOLD,
                        color=T.TEXT_SECONDARY),
    )


def build(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    state = {"settings": Settings.load()}

    theme_text = ft.Text(
        f"当前：{'浅色' if state['settings'].theme == 'light' else '深色'}",
        size=13, color=T.TEXT_PRIMARY,
    )

    shortcut_text = ft.Text(
        "开" if state["settings"].show_shortcut_hint else "关",
        size=13, color=T.TEXT_PRIMARY,
    )

    window_text = ft.Text(
        MODE_LABELS[normalize(state["settings"].window_mode)],
        size=13, color=T.TEXT_PRIMARY,
    )

    info = ft.Text(
        f"用户数据目录：{_config_dir()}",
        size=11, color=T.TEXT_MUTED,
    )

    def go_back(_e):
        navigate("/")

    def _rebuild_current_view():
        """清掉视图缓存并重建当前页，让新配色立刻生效。"""
        router = Router.current
        if router is not None:
            router.invalidate()
            router.navigate(router.current_path())
        else:
            page.update()

    def toggle_theme(e):
        s = state["settings"]
        s.theme = "dark" if e.control.value else "light"
        s.save()
        theme.set_mode(s.theme)
        # 明暗开关要重新穿一次当前的皮：材料包会按明暗重新取令牌，
        # 石砖包本来就是暗色，保持不变。
        ui.apply(ui.current_id(), persist=False)
        theme.apply_to_page(page)
        _rebuild_current_view()

    def toggle_shortcut(e):
        s = state["settings"]
        s.show_shortcut_hint = bool(e.control.value)
        s.save()
        shortcut_text.value = "开" if s.show_shortcut_hint else "关"
        page.update()

    def change_window_mode(e):
        s = state["settings"]
        s.window_mode = normalize(e.control.value)
        s.save()
        window_text.value = MODE_LABELS[s.window_mode]
        # 立刻应用：全屏 / 最大化即时生效，窗口模式改尺寸
        apply_window_mode(page, s)
        page.update()

    def row(label: str, value_text: ft.Text, on_change,
            initial_value: bool) -> ft.Container:
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border=ft.Border.only(
                bottom=ft.BorderSide(1, T.DIVIDER)),
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Text(label, size=14, color=T.TEXT_PRIMARY),
                        expand=True,
                    ),
                    value_text,
                    ft.Container(width=12),
                    ft.Switch(value=initial_value, on_change=on_change),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    # ---------------- 界面风格 ----------------

    packs = ui.all_packs()
    current_pack_id = ui.current_id()
    pack_state = {"id": current_pack_id}
    pack_hint = ft.Text(
        next((p.meta.description for p in packs if p.meta.id == current_pack_id),
             ""),
        size=11, color=T.TEXT_MUTED,
    )

    def pick_pack(pack_id: str):
        def _handler(_e=None) -> None:
            if pack_id == pack_state["id"]:
                return
            if not ui.apply(pack_id):        # 写设置 + 覆写 theme.T
                return
            pack_state["id"] = pack_id
            pack_hint.value = next(
                (p.meta.description for p in ui.all_packs()
                 if p.meta.id == pack_id), "")
            _render_pack_row()
            page.update()
            # 换皮要重建**所有**视图：旧的控件树是按老配色建出来的
            ui.refresh(page, navigate)

        return _handler

    pack_row = ft.Row(wrap=True, spacing=10,
                      vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _render_pack_row() -> None:
        kids: list[ft.Control] = []
        for p in ui.all_packs():
            active = p.meta.id == pack_state["id"]
            kids.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ui.text(p.meta.name, 13,
                                    "on_primary" if active else "",
                                    ft.FontWeight.BOLD),
                            ui.text(
                                f"by {p.meta.author}"
                                + ("" if p.meta.builtin else " · 社区包"),
                                10, "on_primary" if active else "dim"),
                        ],
                        spacing=2,
                        horizontal_alignment=ft.CrossAxisAlignment.START,
                    ),
                    bgcolor=(ui.tone("primary") if active
                             else ui.colors().surface_alt),
                    border=ft.Border.all(
                        2 if active else 1,
                        ui.tone("primary") if active
                        else ui.colors().border),
                    border_radius=8,
                    padding=ft.Padding.symmetric(horizontal=14, vertical=10),
                    width=190, ink=True, on_click=pick_pack(p.meta.id),
                )
            )
        pack_row.controls = kids

    _render_pack_row()

    body = ft.Column(
        [
            _section_title("界面风格"),
            ft.Container(
                border=ft.Border.all(1, T.BORDER),
                border_radius=8,
                padding=ft.Padding.all(12),
                content=ft.Column(
                    [
                        pack_row,
                        ft.Container(height=8),
                        pack_hint,
                        ft.Container(height=4),
                        ft.Text("切换后整个应用（含掼蛋牌桌）立刻换皮；"
                                "以后接入社区包也会出现在这里。",
                                size=11, color=T.TEXT_MUTED),
                    ],
                    spacing=0,
                ),
            ),
            _section_title("外观"),
            ft.Container(
                border=ft.Border.all(1, T.BORDER),
                border_radius=8,
                content=ft.Column(
                    [
                        row("深色主题", theme_text, toggle_theme,
                            initial_value=(state["settings"].theme == "dark")),
                        ft.Container(
                            padding=ft.Padding.symmetric(
                                horizontal=12, vertical=8),
                            content=ft.Text(
                                "提示：暗黑2 / MC 石砖风本身就是暗色，"
                                "深浅开关只对默认风格有意义。",
                                size=11, color=T.TEXT_MUTED),
                        ),
                    ],
                    spacing=0,
                ),
            ),
            _section_title("界面"),
            ft.Container(
                border=ft.Border.all(1, T.BORDER),
                border_radius=8,
                content=ft.Column(
                    [
                        row("显示快捷键提示", shortcut_text, toggle_shortcut,
                            initial_value=state["settings"].show_shortcut_hint),
                        ft.Container(
                            padding=ft.Padding.symmetric(
                                horizontal=12, vertical=10),
                            content=ft.Row(
                                [
                                    ft.Container(
                                        content=ft.Text("窗口模式", size=14,
                                                        color=T.TEXT_PRIMARY),
                                        expand=True,
                                    ),
                                    window_text,
                                    ft.Container(width=12),
                                    ft.Dropdown(
                                        width=150,
                                        value=normalize(
                                            state["settings"].window_mode),
                                        options=[
                                            ft.dropdown.Option(
                                                m, MODE_LABELS[m])
                                            for m in MODES
                                        ],
                                        on_select=change_window_mode,
                                    ),
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                        ),
                    ],
                    spacing=0,
                ),
            ),
            ft.Container(height=20),
            info,
        ],
        spacing=0,
    )

    return ft.Column(
        [
            app_bar("设置", on_back=go_back),
            page_padding(ft.Container(content=body, expand=True)),
        ],
        expand=True,
    )
