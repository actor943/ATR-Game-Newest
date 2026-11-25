# -*- coding: utf-8 -*-
"""3D 台球插件自检：资源目录、两条渲染路径依赖、本地服务与 URL。"""

from __future__ import annotations

import urllib.request

import webview
from flet_webview import WebView

from . import standalone
from .local_server import game_url, site_root


def _run() -> None:
    assert callable(webview.create_window)
    assert callable(standalone.main)
    assert callable(WebView.load_file)
    root = site_root()
    assert (root / "index.html").is_file()
    assert (root / "index.js").is_file()
    assert (root / "three_core.js").is_file()
    url = game_url("ruletype=eightball")
    assert url.startswith("http://127.0.0.1:")
    assert url.endswith("/index.html?ruletype=eightball")
    with urllib.request.urlopen(url, timeout=5) as resp:
        assert resp.status == 200
        assert b"viewP1" in resp.read()
    print("billiards3d selftest OK", root)


if __name__ == "__main__":
    _run()
