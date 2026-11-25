# -*- coding: utf-8 -*-
"""3D 台球独立渲染窗口入口。

这个进程不依赖 Flet：用 pywebview 创建系统原生窗口（macOS 为 WKWebView，
Windows 为 Edge WebView2，Linux 为 WebKitGTK），直接加载构建好的 TypeScript
台球站点。窗口有自己的标题栏和完整网页 UI，没有 ATR Game 的 Flet 顶栏。

由 Flet 主程序以子进程方式启动::

    python -m games.billiards3d.standalone "ruletype=eightball" "八球"
"""

from __future__ import annotations

import sys

import webview

from .local_server import game_url

_WINDOW_WIDTH = 1180
_WINDOW_HEIGHT = 800


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    params = args[0] if args else ""
    title = args[1] if len(args) > 1 else "3D 台球"
    url = game_url(params)
    webview.create_window(
        title,
        url,
        width=_WINDOW_WIDTH,
        height=_WINDOW_HEIGHT,
        min_size=(760, 560),
        resizable=True,
        fullscreen=False,
    )
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
