# -*- coding: utf-8 -*-
"""UI 包（界面皮肤）：默认材料风 + 暗黑2/MC 石砖风。

用法（视图层只面向 :mod:`core.ui_theme`）::

    from core import ui_theme as ui
    ui.button("建立房间", "⚒", on_click)
    ui.panel(ui.text("房间名", 14, "gold"))

想加第三套皮：写一个模块继承 :class:`core.ui_packs.base.BasePack`，
实现同名零件工厂，末尾 ``register(YourPack())``，设置页自动多一项。
"""

from .base import BasePack, ColorTokens, PackMeta
from .registry import all, default_id, get, ids, register

__all__ = [
    "BasePack", "ColorTokens", "PackMeta",
    "register", "get", "all", "ids", "default_id",
]
