# -*- coding: utf-8 -*-
"""3D 台球插件自检：资源目录、两条渲染路径依赖、本地服务与 URL。"""

from __future__ import annotations

import urllib.request

import webview
from flet_webview import WebView

from . import geometry, standalone
from .local_server import game_url, site_root


def _run() -> None:
    assert callable(webview.create_window)
    assert callable(standalone.main)
    assert callable(WebView.load_file)
    root = site_root()
    assert (root / "index.html").is_file()
    assert (root / "index.js").is_file()
    assert (root / "three_core.js").is_file()
    # 0.5：移除 Anon 胶囊 + 默认中文 / 游戏内语言切换
    assert (root / "atr-overrides.css").is_file()
    assert (root / "atr_i18n.js").is_file()
    html = (root / "index.html").read_text(encoding="utf-8")
    assert "atr-overrides.css" in html and "atr_i18n.js" in html
    css = (root / "atr-overrides.css").read_text(encoding="utf-8")
    assert "#lobbyOverlay" in css and "#atrStandaloneBack" in css
    # 0.5：Windows / Linux 无边框跟随窗口桥
    assert callable(geometry.start) and callable(geometry.snapshot)
    assert callable(standalone._FollowBridge.atr_sync)
    assert "atr_sync" in html and "atrStandaloneBack" in html
    url = game_url("ruletype=eightball")
    assert url.startswith("http://127.0.0.1:")
    assert url.endswith("/index.html?ruletype=eightball")
    with urllib.request.urlopen(url, timeout=5) as resp:
        assert resp.status == 200
        assert b"viewP1" in resp.read()
    print("billiards3d selftest OK", root)


if __name__ == "__main__":
    _run()
