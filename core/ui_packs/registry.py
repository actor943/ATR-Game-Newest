# -*- coding: utf-8 -*-
"""UI 包注册表：内置两套，社区包以后往这里 register 就行。

和 ``core/registry.py``（游戏插件）是同一套思路：**注册即可用**。
设置页的「界面风格」列的就是 :func:`all` 的结果，所以新包不需要改设置页。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .base import BasePack, ColorTokens, PackMeta

_PACKS: Dict[str, BasePack] = {}
_BUILTIN_LOADED = False


def register(pack: BasePack) -> None:
    """登记一个界面包（同名覆盖，便于热更新 / 调试）。"""
    _PACKS[pack.meta.id] = pack


def get(pack_id: Optional[str]) -> Optional[BasePack]:
    """按 id 取包；取不到回落到默认包（保证界面永远有皮可穿）。"""
    _ensure_builtin()
    return _PACKS.get(pack_id or "") or _PACKS.get("default")


def all() -> List[BasePack]:
    """全部可用包（内置在前，社区包按 id 排序跟在后面）。"""
    _ensure_builtin()
    builtin = [p for p in _PACKS.values() if p.meta.builtin]
    extra = [p for p in _PACKS.values() if not p.meta.builtin]
    builtin.sort(key=lambda p: p.meta.id)
    extra.sort(key=lambda p: p.meta.id)
    return builtin + extra


def ids() -> List[str]:
    return [p.meta.id for p in all()]


def default_id() -> str:
    return "default"


def _ensure_builtin() -> None:
    """惰性加载内置包：避免 import 循环（包 → 主题 → 包）。"""
    global _BUILTIN_LOADED
    if _BUILTIN_LOADED:
        return
    _BUILTIN_LOADED = True
    from . import material as _material     # noqa: F401  （import 即注册）
    from . import rustic as _rustic         # noqa: F401
