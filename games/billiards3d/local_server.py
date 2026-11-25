# -*- coding: utf-8 -*-
"""为 3D 台球静态站点提供本地 HTTP 服务。

开源项目 billiards 是纯前端站点（three.js + WebGL），由独立原生窗口
（pywebview）加载。为了让 three.js 的 fetch / glTF 资源稳定加载，这里用
标准库起一个仅监听 127.0.0.1 的静态服务器，把 ``assets/billiards3d``
作为站点根目录（完全本地，不经过外网、不调用系统浏览器）。

服务器是进程级单例，首次调用 :func:`ensure_server` 时启动，daemon 线程，
应用退出时自动结束，不会占用固定端口。
"""

from __future__ import annotations

import functools
import http.server
import sys
import threading
from pathlib import Path

_SITE_DIR_NAME = "billiards3d"

_server: http.server.ThreadingHTTPServer | None = None
_server_url: str | None = None
_lock = threading.Lock()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    """静默版静态文件处理器（避免每次资源请求都刷控制台）。"""

    def log_message(self, fmt: str, *args) -> None:  # noqa: A002
        return


def site_root() -> Path:
    """定位打包在 assets 里的台球站点目录。

    开发态从源码目录向上找；打包态从可执行文件或当前工作目录向上找
    （macOS .app 的资源通常在 ``Contents/Resources/assets``）。
    """
    candidates: list[Path] = []
    for base in (Path(__file__).resolve(), Path(sys.executable).resolve()):
        for parent in [base.parent, *base.parents][:8]:
            path = parent / "assets" / _SITE_DIR_NAME
            if path not in candidates:
                candidates.append(path)
    cwd_candidate = Path.cwd() / "assets" / _SITE_DIR_NAME
    if cwd_candidate not in candidates:
        candidates.append(cwd_candidate)
    for path in candidates:
        if (path / "index.html").is_file():
            return path
    raise FileNotFoundError(
        "找不到 3D 台球资源目录 assets/billiards3d（已尝试："
        + ", ".join(str(p) for p in candidates)
        + "）"
    )


def _new_server(root: Path) -> http.server.ThreadingHTTPServer:
    handler = functools.partial(_QuietHandler, directory=str(root))
    last_error: OSError | None = None
    for _ in range(10):
        try:
            return http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        except OSError as exc:  # 端口 0 一般总能成功，重试只是兜底
            last_error = exc
    assert last_error is not None
    raise last_error


def ensure_server() -> str:
    """返回站点首页 URL，例如 ``http://127.0.0.1:54321/index.html``。"""
    global _server, _server_url
    with _lock:
        if _server is None or _server_url is None:
            root = site_root()
            _server = _new_server(root)
            threading.Thread(
                target=_server.serve_forever,
                name="billiards3d-http",
                daemon=True,
            ).start()
            host, port = _server.server_address[:2]
            _server_url = f"http://{host}:{port}/index.html"
        return _server_url


def game_url(params: str = "", page_name: str = "index.html") -> str:
    """打开台球页面（可带 URL 参数，如 ``ruletype=eightball&practice``）。"""
    base = ensure_server()
    root = base.rsplit("/", 1)[0]
    url = f"{root}/{page_name}"
    return f"{url}?{params}" if params else url
