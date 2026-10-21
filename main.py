"""兼容入口：让 IDE / 用户可以直接 ``python main.py`` 启动。

实际逻辑在 :mod:`app` 里；本文件只是 ``ft.run(app.run)`` 的薄壳。

* ``name`` 会带进窗口标题 / 应用名，0.4.6 起统一叫 ATR Game；
* ``assets_dir`` 的取值分两种情况（**打包后必须走相对路径**）：
  - 开发态：绝对路径指向项目根 ``assets/``，这样无论从哪个工作目录启动，
    牌图 / 棋子图都能找到；
  - 打包态：``__file__`` 旁边那个绝对路径是**构建机上的**路径，在用户机器上
    根本不存在。flet 解析 ``assets_dir`` 时发现目录不存在会直接丢弃（当成
    没传），于是所有图片全挂 —— 所以此时退回 flet 约定的相对 ``assets``，
    由 app 所在目录去解析。
"""

from pathlib import Path

import flet as ft

from app import run

_DEV_ASSETS = Path(__file__).resolve().parent / "assets"

# 开发态用绝对路径（不依赖 cwd）；打包态用 flet 约定的相对 "assets"。
ASSETS_DIR = str(_DEV_ASSETS) if _DEV_ASSETS.is_dir() else "assets"

ft.run(run, name="ATR Game", assets_dir=ASSETS_DIR)
