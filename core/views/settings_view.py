# -*- coding: utf-8 -*-
"""设置视图：语言 / 界面风格 / 主题 / 快捷键提示 / 窗口模式 / 路径展示。

**语言**（0.4.8 新增）
----------------------
列出 :func:`core.i18n.languages` 里登记的语种（简体中文 / English）。
选中后立即：写回设置 → 切换当前语言 → 清掉全部路由缓存 → 重建当前页。
视图里的文案都是 :func:`core.i18n.t` 取出来的，所以重建一次就整个应用换语言，
不需要重启。没翻到的键会自动说中文（见 :mod:`core.i18n`）。

**界面风格**（0.4.7 新增）
--------------------------
列出 :func:`core.ui_theme.all_packs` 里注册的所有界面包：默认材料风、
暗黑2/MC 石砖风，以后社区包往 ``core/ui_packs/`` 里一注册就会出现在这里。
选中后立即：写回设置 → 覆写 ``theme.T`` → 清掉全部路由缓存 → 重建当前页，
所以整个应用（含掼蛋牌桌）当场换皮，不需要重启。
"""

from __future__ import annotations

import flet as ft

from core import i18n
from core import theme
from core import ui_theme as ui
from core.i18n import t
from core.registry import NavigateFn
from core.router import Router
from core.settings import Settings, _config_dir
from core.theme import T
from core.ui_common import app_bar, page_padding
from core.window import (
    MODES,
    apply_window_mode,
    mode_label,
    normalize,
)


def _section_title(text: str) -> ft.Container:

    """一个小节标题（“语言”“界面风格”这类灰色小字）。"""
    return ft.Container(
        padding=ft.Padding.only(top=12, bottom=4),
        content=ft.Text(text, size=12, weight=ft.FontWeight.BOLD,
                        color=T.TEXT_SECONDARY),
    )


def build(page: ft.Page, navigate: NavigateFn) -> ft.Control:

    """设置页：语言 / 界面风格 / 明暗主题 / 快捷键 / 窗口模式 / 数据目录。"""
    state = {"settings": Settings.load()}

    theme_text = ft.Text(
        t("settings.theme_current",
          mode=t("settings.theme_light")
          if state["settings"].theme == "light" else t("settings.theme_dark")),
        size=13, color=T.TEXT_PRIMARY,
    )

    shortcut_text = ft.Text(
        t("common.on") if state["settings"].show_shortcut_hint
        else t("common.off"),
        size=13, color=T.TEXT_PRIMARY,
    )

    window_text = ft.Text(
        mode_label(state["settings"].window_mode),
        size=13, color=T.TEXT_PRIMARY,
    )

    info = ft.Text(
        t("settings.data_dir", path=_config_dir()),
        size=11, color=T.TEXT_MUTED,
    )

    def go_back(_e):

        """返回主菜单。"""
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

        """切换明暗主题。"""
        s = state["settings"]
        s.theme = "dark" if e.control.value else "light"
        s.save()
        theme_text.value = t("settings.theme_current",
                             mode=t("settings.theme_dark") if s.theme == "dark"
                             else t("settings.theme_light"))
        theme.set_mode(s.theme)
        # 明暗开关要重新穿一次当前的皮：材料包会按明暗重新取令牌，
        # 石砖包本来就是暗色，保持不变。
        ui.apply(ui.current_id(), persist=False)
        theme.apply_to_page(page)
        _rebuild_current_view()

    def toggle_shortcut(e):

        """开关「显示快捷键提示」。"""
        s = state["settings"]
        s.show_shortcut_hint = bool(e.control.value)
        s.save()
        shortcut_text.value = (t("common.on") if s.show_shortcut_hint
                               else t("common.off"))
        page.update()

    def change_window_mode(e):

        """切换窗口模式（全屏 / 窗口化）。"""
        s = state["settings"]
        s.window_mode = normalize(e.control.value)
        s.save()
        window_text.value = mode_label(s.window_mode)
        # 立刻应用：全屏 / 最大化即时生效，窗口模式改尺寸
        apply_window_mode(page, s)
        page.update()

    def row(label: str, value_text: ft.Text, on_change,
            initial_value: bool) -> ft.Container:

        """设置项的一行：左边标题、右边控件。"""
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

    # ---------------- 语言 ----------------

    lang_state = {"id": i18n.current()}
    lang_hint = ft.Text(
        i18n.language_name(lang_state["id"]),
        size=11, color=T.TEXT_MUTED,
    )
    lang_row = ft.Row(wrap=True, spacing=10,
                      vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def pick_lang(code: str):

        """选定语言后的处理函数。"""
        def _handler(_e=None) -> None:

            """点一下语言就切：写盘 → 换语言 → 重建当前页。"""
            if code == lang_state["id"]:
                return
            if not i18n.set_lang(code):       # 写设置 + 改当前语言
                return
            lang_state["id"] = code
            lang_hint.value = i18n.language_name(code)
            _render_lang_row()
            page.update()
            # 界面上的字都是按老语言建出来的：丢掉缓存重建，整应用换语言
            i18n.refresh(page, navigate)

        return _handler

    def _render_lang_row() -> None:

        """重画语言那一行（当前语言要高亮）。"""
        kids: list[ft.Control] = []
        for code, name, note in i18n.languages():
            active = code == lang_state["id"]
            kids.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ui.text(name, 13,
                                    "on_primary" if active else "",
                                    ft.FontWeight.BOLD),
                            ui.text(note or code, 10,
                                    "on_primary" if active else "dim"),
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
                    width=150, ink=True, on_click=pick_lang(code),
                )
            )
        lang_row.controls = kids

    _render_lang_row()

    # ---------------- 界面风格 ----------------

    def pack_name(meta) -> str:
        """包的名字：登记过 i18n 键就翻译，没有就显示包自带的（社区包）。"""
        return t(f"pack.{meta.id}.name", default=meta.name)

    def pack_desc(meta) -> str:

        """取界面包的说明文字。"""
        return t(f"pack.{meta.id}.desc", default=meta.description)

    packs = ui.all_packs()
    current_pack_id = ui.current_id()
    pack_state = {"id": current_pack_id}
    pack_hint = ft.Text(
        next((pack_desc(p.meta) for p in packs
              if p.meta.id == current_pack_id), ""),
        size=11, color=T.TEXT_MUTED,
    )

    def pick_pack(pack_id: str):

        """选定界面包后的处理函数。"""
        def _handler(_e=None) -> None:

            """点一下语言就切：写盘 → 换语言 → 重建当前页。"""
            if pack_id == pack_state["id"]:
                return
            if not ui.apply(pack_id):        # 写设置 + 覆写 theme.T
                return
            pack_state["id"] = pack_id
            pack_hint.value = next(
                (pack_desc(p.meta) for p in ui.all_packs()
                 if p.meta.id == pack_id), "")
            _render_pack_row()
            page.update()
            # 换皮要重建**所有**视图：旧的控件树是按老配色建出来的
            ui.refresh(page, navigate)

        return _handler

    pack_row = ft.Row(wrap=True, spacing=10,
                      vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _render_pack_row() -> None:

        """重画界面包那一行。"""
        kids: list[ft.Control] = []
        for p in ui.all_packs():
            active = p.meta.id == pack_state["id"]
            kids.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ui.text(pack_name(p.meta), 13,
                                    "on_primary" if active else "",
                                    ft.FontWeight.BOLD),
                            ui.text(
                                t("settings.pack_author", author=p.meta.author)
                                + ("" if p.meta.builtin
                                   else t("settings.pack_community")),
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
            _section_title(t("settings.section_language")),
            ft.Container(
                border=ft.Border.all(1, T.BORDER),
                border_radius=8,
                padding=ft.Padding.all(12),
                content=ft.Column(
                    [
                        lang_row,
                        ft.Container(height=8),
                        lang_hint,
                        ft.Container(height=4),
                        ft.Text(t("settings.language_note"),
                                size=11, color=T.TEXT_MUTED),
                    ],
                    spacing=0,
                ),
            ),
            _section_title(t("settings.section_pack")),
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
                        ft.Text(t("settings.pack_note"),
                                size=11, color=T.TEXT_MUTED),
                    ],
                    spacing=0,
                ),
            ),
            _section_title(t("settings.section_appearance")),
            ft.Container(
                border=ft.Border.all(1, T.BORDER),
                border_radius=8,
                content=ft.Column(
                    [
                        row(t("settings.dark_theme"), theme_text, toggle_theme,
                            initial_value=(state["settings"].theme == "dark")),
                        ft.Container(
                            padding=ft.Padding.symmetric(
                                horizontal=12, vertical=8),
                            content=ft.Text(t("settings.dark_note"),
                                            size=11, color=T.TEXT_MUTED),
                        ),
                    ],
                    spacing=0,
                ),
            ),
            _section_title(t("settings.section_ui")),
            ft.Container(
                border=ft.Border.all(1, T.BORDER),
                border_radius=8,
                content=ft.Column(
                    [
                        row(t("settings.shortcut_hint"), shortcut_text,
                            toggle_shortcut,
                            initial_value=state["settings"].show_shortcut_hint),
                        ft.Container(
                            padding=ft.Padding.symmetric(
                                horizontal=12, vertical=10),
                            content=ft.Row(
                                [
                                    ft.Container(
                                        content=ft.Text(
                                            t("settings.window_mode"), size=14,
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
                                            ft.dropdown.Option(m, mode_label(m))
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
            app_bar(t("settings.title"), on_back=go_back),
            page_padding(ft.Container(content=body, expand=True)),
        ],
        expand=True,
    )
