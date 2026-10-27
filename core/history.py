# -*- coding: utf-8 -*-
"""比赛记录（出牌记录）的落盘。

把一局的对战过程（出牌 / 过牌等文本行）连同少量元信息写到本地数据目录下的
文本文件，供事后回看。只使用标准库、不依赖 flet，方便单测。

各平台的应用**数据**目录（与 :mod:`core.settings` 使用的**配置**目录语义不同，
按平台惯例分开处理）：

* macOS：``~/Library/Application Support/ATR Game``
* Windows：``%APPDATA%\\ATR Game``（取不到时回退 ``~/.atr-game``）
* Linux 等：``${XDG_DATA_HOME:-~/.local/share}/ATR Game``

日志统一放在 ``<数据目录>/logs[/<game_id>]/`` 下。
"""

from __future__ import annotations

import logging
import os
import platform
import uuid
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

APP_DIR_NAME = "ATR Game"


def data_dir() -> Path:
    """返回应用**数据**目录，跨平台。

    先判断 :func:`platform.system`，避免在 Windows 上调用不存在的 ``os.uname``。
    """
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_DIR_NAME
        return Path.home() / ".atr-game"
    # Linux 及其他类 Unix：遵循 XDG 规范
    xdg = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(xdg) / APP_DIR_NAME


def logs_dir(game_id: str = "") -> Path:
    """返回日志目录 ``<data_dir>/logs[/game_id]``，不存在就创建。"""
    path = data_dir() / "logs"
    if game_id:
        path = path / game_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _build_header(now: datetime, game_id: str,
                  meta: Optional[dict] = None) -> List[str]:
    """生成文件头部元信息，每行 ``key: value``。"""
    header = [
        f"生成时间: {now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"game_id: {game_id}",
    ]
    if meta:
        for key, value in meta.items():
            header.append(f"{key}: {value}")
    return header


def _unique_log_path(directory: Path, game_id: str, now: datetime) -> Path:
    """生成不冲突的日志路径（同秒多次保存也不会互相覆盖）。"""
    stamp = now.strftime("%Y%m%d-%H%M%S")
    while True:
        suffix = uuid.uuid4().hex[:6]
        path = directory / f"{game_id}-{stamp}-{suffix}.txt"
        if not path.exists():
            return path


def save_match_log(game_id: str, lines: Iterable[str],
                   meta: Optional[dict] = None) -> Path:
    """把一局比赛记录写入文本文件，返回实际写入的路径。

    Args:
        game_id: 游戏 id，用于子目录与文件名。
        lines: 可迭代的字符串（list / deque / 生成器均可），每个元素一行。
        meta: 可选元信息，写入文件头部。

    Returns:
        实际写入的文件路径；写入失败（如只读文件系统）时返回**空 Path**，
        原因记入日志，不抛异常。
    """
    try:
        directory = logs_dir(game_id)
        body = list(lines)          # lines 可能是生成器，先物化
        now = datetime.now()
        path = _unique_log_path(directory, game_id, now)
        header = _build_header(now, game_id, meta)
        content = "\n".join(header + [""] + body) + "\n"
        path.write_text(content, encoding="utf-8")
        return path
    except Exception as exc:  # 只读文件系统等：捕获且不抛出
        logger.warning("保存比赛记录失败 (game_id=%s): %s", game_id, exc)
        return Path()


def recent_logs(game_id: str = "", limit: int = 20) -> List[Path]:
    """按修改时间倒序返回最近的日志文件；目录不存在返回空列表。"""
    directory = data_dir() / "logs"
    if game_id:
        directory = directory / game_id
    if not directory.exists():
        return []
    try:
        files = [p for p in directory.iterdir()
                 if p.is_file() and p.suffix == ".txt"]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError as exc:
        logger.warning("读取比赛记录列表失败: %s", exc)
        return []
    return files[:limit]


def game_ids() -> List[str]:
    """列出「有记录」的游戏 id（目录里有 .txt 才算）。

    主菜单的「游玩记录」用它来决定筛选条上显示哪些游戏。
    """
    root = data_dir() / "logs"
    if not root.exists():
        return []
    result: List[str] = []
    try:
        for child in root.iterdir():
            if not child.is_dir():
                continue
            has_log = any(p.is_file() and p.suffix == ".txt"
                          for p in child.iterdir())
            if has_log:
                result.append(child.name)
    except OSError as exc:
        logger.warning("读取游戏记录目录失败: %s", exc)
        return []
    return sorted(result)


def recent_logs_all(limit: int = 200) -> List[Tuple[str, Path]]:
    """跨**所有**游戏返回最近记录：``[(game_id, 文件路径)]``，按时间倒序。

    主菜单的「游玩记录」页用它把各游戏的记录汇到一张表里。
    """
    root = data_dir() / "logs"
    if not root.exists():
        return []
    items: List[Tuple[str, Path]] = []
    try:
        for child in root.iterdir():
            if not child.is_dir():
                continue
            for path in child.iterdir():
                if path.is_file() and path.suffix == ".txt":
                    items.append((child.name, path))
    except OSError as exc:
        logger.warning("读取全部游戏记录失败: %s", exc)
        return []
    items.sort(key=lambda it: it[1].stat().st_mtime, reverse=True)
    return items[:limit]


def open_data_dir() -> Path:
    """返回数据目录（确保存在），供「在访达中打开」这类功能使用。"""
    path = data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path
