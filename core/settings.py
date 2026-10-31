# -*- coding: utf-8 -*-
"""用户设置的持久化。

使用标准库 ``json``，写入各平台的应用数据目录：

* macOS：``~/Library/Application Support/ATR Game``
* Windows：``%APPDATA%\\ATR Game``
* Linux：``${XDG_CONFIG_HOME:-~/.config}/ATR Game``

本模块不依赖 flet，方便单测。
"""

from __future__ import annotations

import json
import os
import platform
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


APP_DIR_NAME = "ATR Game"


def _is_android() -> bool:
    """是否运行在 Android 上。

    Python 在安卓上也是 posix / Linux 内核，``platform.system()`` 同样是
    ``"Linux"``，必须用安卓专有标记把「安卓 Linux」和「桌面 Linux」区分开。
    """
    if platform.system() != "Linux":
        return False
    if os.environ.get("ANDROID_DATA") or os.environ.get("ANDROID_ROOT"):
        return True
    if os.path.exists("/system/build.prop"):
        return True
    try:
        return "android" in (os.uname().release or "").lower()
    except Exception:
        return False


def _config_dir() -> Path:
    """返回用户配置目录，跨平台。

    Android 特殊处理：flet 会把应用**持久数据目录**通过环境变量
    ``FLET_APP_STORAGE_DATA`` 暴露给 Python，该目录在安卓上既**可写**又
    **跨启动持久**（对应 App 私有数据目录）。旧实现走 ``~/.config``，在
    安卓沙箱里不可写，导致 profile / settings 的 ``save`` 静默失败 —— 表现
    就是「起名保存不生效、退出重启也不生效」。桌面端维持原路径不变，
    避免影响已有桌面用户的存档位置。
    """
    android_storage = os.environ.get("FLET_APP_STORAGE_DATA")
    if android_storage and _is_android():
        return Path(android_storage) / APP_DIR_NAME
    if os.name == "posix" and os.uname().sysname == "Darwin":  # type: ignore[attr-defined]
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return base / APP_DIR_NAME


@dataclass
class Settings:
    theme: str = "light"          # "light" | "dark"
    show_shortcut_hint: bool = True
    last_game: str = ""           # 最后一次进入的游戏 id
    window_mode: str = "fullscreen"   # "fullscreen" | "maximized" | "window"
    # 界面风格包（见 core/ui_packs）：默认材料风；"rustic" = 暗黑2/MC 石砖风。
    # 以后社区包往 ui_packs/ 里一注册，设置页就会多出一项。
    ui_pack: str = "default"
    # 界面语言（见 core/i18n）："zh_CN" 简体中文 / "en_US" English。
    # 未登记过的代号会被 i18n.normalize 回落到 zh_CN。
    language: str = "zh_CN"
    data: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Settings":
        path = path or (_config_dir() / "settings.json")
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        return cls(
            theme=raw.get("theme", "light"),
            show_shortcut_hint=raw.get("show_shortcut_hint", True),
            last_game=raw.get("last_game", ""),
            window_mode=raw.get("window_mode", "fullscreen"),
            ui_pack=raw.get("ui_pack", "default") or "default",
            language=raw.get("language", "zh_CN") or "zh_CN",
            data=raw.get("data", {}) or {},
        )

    def save(self, path: Optional[Path] = None) -> None:
        path = path or (_config_dir() / "settings.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
