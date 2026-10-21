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
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


APP_DIR_NAME = "ATR Game"


def _config_dir() -> Path:
    """返回用户配置目录，跨平台。"""
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
            data=raw.get("data", {}) or {},
        )

    def save(self, path: Optional[Path] = None) -> None:
        path = path or (_config_dir() / "settings.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
