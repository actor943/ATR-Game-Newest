# -*- coding: utf-8 -*-
"""主窗口几何信息共享（Windows/Linux 的无边框台球窗口跟随用）。

flet-webview 在 Windows/Linux 是**主动报错的占位控件**，Flet 核心也没有
任何 WebView / Html / iframe 控件，所以 3D 台球无法真正成为 Flet 的子控件。

这里退而求其次：主进程起一个只监听 127.0.0.1 的微型 HTTP 服务，把 Flet
主窗口的位置 / 尺寸 / 最小化状态暴露出来；台球那边用无边框 pywebview
窗口按这个几何信息移动和缩放，看起来就像嵌在应用里。

不依赖 pywin32 / python-xlib，纯标准库；Wayland 等平台若不允许窗口移动，
台球窗口仍可正常使用，只是不能跟随。
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

_state = {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0, "minimized": False}
_lock = threading.Lock()
_server: Optional[ThreadingHTTPServer] = None
_url = ""
_page = None
_poller: Optional[threading.Thread] = None


class _Handler(BaseHTTPRequestHandler):
    """只给台球子窗口读的几何快照。"""

    def log_message(self, fmt: str, *args) -> None:  # noqa: A002
        return

    def do_GET(self) -> None:  # noqa: N802
        with _lock:
            body = json.dumps(dict(_state)).encode("utf-8")
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


def _read_page(page) -> None:
    """从 Flet 的 page.window 读一次几何；读不到时用视口尺寸兜底。"""
    try:
        window = page.window
        try:
            x = float(getattr(window, "left", None) or 0)
        except (TypeError, ValueError):
            x = 0.0
        try:
            y = float(getattr(window, "top", None) or 0)
        except (TypeError, ValueError):
            y = 0.0
        try:
            w = float(getattr(window, "width", None) or 0)
            h = float(getattr(window, "height", None) or 0)
        except (TypeError, ValueError):
            w = h = 0.0
        if w <= 0 or h <= 0:
            from core import responsive
            w, h = responsive.size(page)
        minimized = bool(getattr(window, "minimized", False))
    except Exception:                                  # noqa: BLE001
        return
    with _lock:
        _state.update(x=x, y=y, w=w, h=h, minimized=minimized)


def _poll() -> None:
    """窗口属性不一定会回写 Python 侧；定时再读一次做兜底。"""
    import time
    while True:
        page = _page
        if page is not None:
            _read_page(page)
        time.sleep(0.3)


def start(page) -> str:
    """启动（只启动一次）几何服务，返回快照 URL。"""
    global _server, _url, _page, _poller
    if _server is None:
        _server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(
            target=_server.serve_forever,
            name="billiards3d-geometry",
            daemon=True,
        ).start()
        host, port = _server.server_address[:2]
        _url = f"http://{host}:{port}/geometry"
    _page = page
    _read_page(page)
    # 原生窗口移动 / 缩放事件：能拿到就立刻刷新一次
    try:
        page.window.on_event = lambda _e: _read_page(page)
    except Exception:                                  # noqa: BLE001
        pass
    if _poller is None:
        _poller = threading.Thread(target=_poll, name="billiards3d-geometry-poll",
                                   daemon=True)
        _poller.start()
    return _url


def snapshot() -> dict:
    with _lock:
        return dict(_state)
