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
MODE_LABELS = {
    FULLSCREEN: "全屏（默认）",
    MAXIMIZED: "最大化",
    WINDOWED: "窗口",
}

# 窗口模式下的默认尺寸（仅 WINDOWED 使用）
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 800
MIN_WIDTH = 640
MIN_HEIGHT = 700


def normalize(mode: Optional[str]) -> str:
    """容错：未知模式一律回落到全屏。"""
    return mode if mode in MODES else FULLSCREEN


def apply_window_mode(page: ft.Page, settings: Settings) -> None:
    """把设置里的窗口模式应用到 Page。

    全屏直接用 ``window.full_screen``（铺满设备分辨率）；最大化退一级；
    窗口模式给一个桌面级的默认尺寸并居中，避免又变回手机大小 + 随机位置。
    """
    mode = normalize(getattr(settings, "window_mode", None))

    page.window.min_width = MIN_WIDTH
    page.window.min_height = MIN_HEIGHT

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
