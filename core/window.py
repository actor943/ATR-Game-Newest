# -*- coding: utf-8 -*-
"""窗口模式：全屏 / 最大化 / 窗口，默认全屏。

Mac 上默认窗口只有手机大小（800×980）且位置随机，所以 0.4.6 起默认全屏；
用户仍可在设置页改回「最大化」或固定窗口大小。
"""

from __future__ import annotations

from typing import Optional

import flet as ft

from .settings import Settings

# 窗口模式
FULLSCREEN = "fullscreen"
MAXIMIZED = "maximized"
WINDOWED = "window"

MODES = (FULLSCREEN, MAXIMIZED, WINDOWED)
# 字面文案（中文）保留为兜底；界面上请一律用 :func:`mode_label`，它按当前语言取
MODE_LABELS = {
    FULLSCREEN: "全屏（默认）",
    MAXIMIZED: "最大化",
    WINDOWED: "窗口",
}
MODE_LABEL_KEYS = {
    FULLSCREEN: "window.fullscreen",
    MAXIMIZED: "window.maximized",
    WINDOWED: "window.windowed",
}

# 窗口模式下的默认尺寸（仅 WINDOWED 使用）
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 800
# 下限原来 640×700：小尺寸笔记本 / 横屏手机上几乎没法缩小窗口，
# 也挡住了用户「先还原再最大化」的操作。放宽到常见的最小值。
MIN_WIDTH = 480
MIN_HEIGHT = 560


def normalize(mode: Optional[str]) -> str:
    """容错：未知模式一律回落到全屏。"""
    return mode if mode in MODES else FULLSCREEN


def mode_label(mode: Optional[str]) -> str:
    """该窗口模式在当前语言下的名字（设置页下拉与状态文字都用它）。"""
    from .i18n import t
    key = MODE_LABEL_KEYS[normalize(mode)]
    return t(key, default=MODE_LABELS[normalize(mode)])


def apply_window_mode(page: ft.Page, settings: Settings) -> None:
    """把设置里的窗口模式应用到 Page。

    全屏直接用 ``window.full_screen``（铺满设备分辨率）；最大化退一级；
    窗口模式给一个桌面级的默认尺寸并居中，避免又变回手机大小 + 随机位置。
    """
    mode = normalize(getattr(settings, "window_mode", None))

    page.window.min_width = MIN_WIDTH
    page.window.min_height = MIN_HEIGHT
    # 明确允许缩放 / 最大化（某些平台默认会禁掉最大化按钮，
    # 用户就会以为「这个程序没法最大化」）。
    for attr in ("resizable", "maximizable"):
        try:
            setattr(page.window, attr, True)
        except Exception:                   # noqa: BLE001 — 平台不支持就忽略
            pass

    if mode == FULLSCREEN:
        page.window.full_screen = True
        page.window.maximized = False
    elif mode == MAXIMIZED:
        page.window.full_screen = False
        page.window.maximized = True
    else:
        page.window.full_screen = False
        page.window.maximized = False
        page.window.width = DEFAULT_WIDTH
        page.window.height = DEFAULT_HEIGHT
        page.window.center = True
