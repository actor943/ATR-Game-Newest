# -*- coding: utf-8 -*-
"""3D 台球独立渲染窗口入口。

Windows / Linux 没有内嵌 WebView（flet-webview 在这两个平台是报错占位控件），
所以用 pywebview 开原生窗口：

* 默认仍是普通独立窗口，双击 / 关闭都由系统管理；
* 从应用内进入时传 ``<几何URL> 1``，做成**无边框窗口**，网页里的
  ``atr_sync`` 定时拉取主窗口几何并 ``move/resize``，视觉上像嵌在应用里；
  网页上的「返回游戏」按钮调用 ``atr_close`` 关掉子窗口。

用法::

    python -m games.billiards3d.standalone "ruletype=eightball" "八球"
    python -m games.billiards3d.standalone "..." "八球" "http://127.0.0.1:PORT/geometry" 1
"""

from __future__ import annotations

import json
import sys
import urllib.request

import webview

from .local_server import game_url

_WINDOW_WIDTH = 1180
_WINDOW_HEIGHT = 800


class _FollowBridge:
    """暴露给网页的 pywebview.api：atr_sync / atr_close。"""

    def __init__(self, geometry_url: str) -> None:
        self.geometry_url = geometry_url
        self.window = None
        self._last: tuple[int, int, int, int] | None = None

    def _fetch(self) -> dict | None:
        try:
            with urllib.request.urlopen(self.geometry_url, timeout=1) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:                               # noqa: BLE001
            return None

    def atr_sync(self) -> None:
        """由网页定时器调用；运行中的窗口跟着 Flet 主窗口走。"""
        data = self._fetch()
        win = self.window
        if data is None or win is None:
            return
        if bool(data.get("minimized", False)):
            try:
                win.hide()
            except Exception:                           # noqa: BLE001
                pass
            return
        try:
            win.show()
        except Exception:                               # noqa: BLE001
            pass
        try:
            x = max(0, int(float(data.get("x", 0))))
            y = max(0, int(float(data.get("y", 0))))
            w = max(320, int(float(data.get("w", _WINDOW_WIDTH))))
            h = max(240, int(float(data.get("h", _WINDOW_HEIGHT))))
        except (TypeError, ValueError):
            return
        rect = (x, y, w, h)
        if rect == self._last:
            return
        self._last = rect
        try:
            win.resize(w, h)
            win.move(x, y)
        except Exception:                               # noqa: BLE001
            # Wayland / 某些 Linux 组合器不允许移动窗口：游戏照常可用。
            pass

    def atr_close(self) -> None:
        win = self.window
        if win is None:
            return
        try:
            win.destroy()
        except Exception:                               # noqa: BLE001
            pass


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    params = args[0] if args else ""
    title = args[1] if len(args) > 1 else "3D 台球"
    geometry_url = args[2] if len(args) > 2 else ""
    follow = len(args) > 3 and args[3] == "1"
    url = game_url(params)

    options = {
        "width": _WINDOW_WIDTH,
        "height": _WINDOW_HEIGHT,
        "min_size": (760, 560),
        "resizable": True,
        "fullscreen": False,
    }
    bridge: _FollowBridge | None = None
    if follow and geometry_url:
        bridge = _FollowBridge(geometry_url)
        options.update(
            frameless=True,
            easy_drag=False,
            shadow=False,
            on_top=True,
            js_api=bridge,
        )

    window = webview.create_window(title, url, **options)
    if bridge is not None:
        bridge.window = window
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
