# -*- coding: utf-8 -*-
"""内置音乐的资源定位与曲库扫描（0.4.10 新增）。

歌曲放在项目根 ``assets/songs/``，由 :mod:`main` 通过 ``assets_dir`` 交给
Flutter 侧；本模块要在 **Python 侧**拿到同一批 mp3 的真实路径，才能把它们
喂给音频后端（pygame.mixer）。开发态 / 打包态的资源根目录可能不同，所以这里
按下面的优先级逐个试探，取第一个真实存在的目录：

1. ``FLET_ASSETS_DIR``（flet 运行时显式指定的资源根）；
2. 本文件上溯两级得到的 ``assets/``（源码运行）；
3. 当前工作目录 / 启动脚本旁的 ``assets/``（打包后的常见布局）。

本模块不依赖 flet，也不导入 pygame，便于命令行自检。
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SONGS_DIR_NAME = "songs"

# 常见的 MP3 帧头码率表（kbps）：下标是帧头里的 bitrate_index。
_BITRATE_MPEG1 = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128,
                  160, 192, 224, 256, 320, 0)
_BITRATE_MPEG2 = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96,
                  112, 128, 144, 160, 0)
_SAMPLE_RATES = {
    3: (44100, 48000, 32000),   # MPEG-1
    2: (22050, 24000, 16000),   # MPEG-2
    0: (11025, 12000, 8000),    # MPEG-2.5
}


@dataclass(frozen=True)
class Track:
    """一首内置歌曲：显示名 + 文件名 + 磁盘路径。"""

    name: str
    filename: str
    path: Path

    @property
    def duration(self) -> float:
        """近似时长（秒）；读不出来时返回 0。"""
        return mp3_duration(self.path)


def assets_root() -> Path | None:
    """返回可用的 assets 根目录（找不到就返回 None）。"""
    here = Path(__file__).resolve()
    candidates = [
        os.environ.get("FLET_ASSETS_DIR", ""),
        str(here.parents[2] / "assets"),       # core/music/library.py → 项目根
        str(Path.cwd() / "assets"),
        str(Path(sys.argv[0]).resolve().parent / "assets"),
    ]
    for raw in candidates:
        if not raw:
            continue
        path = Path(raw).expanduser()
        if path.is_dir():
            return path
    return None


def songs_dir() -> Path | None:
    """内置歌曲目录；资源不可用时返回 None。"""
    root = assets_root()
    if root is None:
        return None
    songs = root / SONGS_DIR_NAME
    return songs if songs.is_dir() else None


def display_name(filename: str) -> str:
    """把文件名整理成人看的歌名（去掉序号 / Official 之类后缀）。"""
    name = Path(filename).stem
    name = re.sub(r"^\d{1,2}\s*[-_.]?\s*", "", name)       # "07 Liminal…" 的序号
    name = re.sub(r"\s*\(\s*Official.*?\)\s*$", "", name,
                  flags=re.IGNORECASE)
    name = re.sub(r"\s*-\s*Official Music Video\s*$", "", name,
                  flags=re.IGNORECASE)
    name = name.replace("_", " ").strip()
    return name or Path(filename).stem


def discover() -> list[Track]:
    """按文件名列出全部内置 mp3（目录缺失或读取失败时返回空表）。"""
    directory = songs_dir()
    if directory is None:
        return []
    tracks: list[Track] = []
    try:
        for path in sorted(directory.glob("*.mp3"),
                           key=lambda p: p.name.casefold()):
            tracks.append(Track(display_name(path.name), path.name, path))
    except OSError:
        return []
    return tracks


# ------------------------------------------------------------------
# 时长估算（不解码整首歌）
# ------------------------------------------------------------------

def _syncsafe(data: bytes) -> int:
    """ID3v2 的同步安全整数（每字节只取低 7 位）。"""
    return ((data[0] & 0x7F) << 21) | ((data[1] & 0x7F) << 14) | \
           ((data[2] & 0x7F) << 7) | (data[3] & 0x7F)


def mp3_duration(path: Path) -> float:
    """估算 mp3 时长。

    pygame 的 music 对象只有 ``get_pos()`` 没有 ``get_length()``；用
    ``Sound(path).get_length()`` 又要整首解码（本曲库单曲 6~14MB，代价太大）。
    这里读文件头的第一个有效 MPEG 帧拿码率，再按 CBR 估算：对 CBR 文件准确，
    VBR 文件有偏差但足够画进度条。装了 mutagen 时优先用 mutagen 的精确结果。
    """
    try:
        from mutagen.mp3 import MP3       # 可选依赖，没有就走帧头估算
        return float(MP3(str(path)).info.length)
    except Exception:                     # noqa: BLE001 — 没装 / 文件不是标准 mp3
        pass
    try:
        size = path.stat().st_size
        with open(path, "rb") as fh:
            head = fh.read(10)
            start = 0
            if head[:3] == b"ID3" and len(head) >= 10:
                # 有些曲子内嵌大幅封面，ID3 标签本身就有好几 MB，
                # 必须先 seek 过去再读帧头（只读开头 256KB 会全落在标签里）
                start = 10 + _syncsafe(head[6:10])
                if head[5] & 0x10:        # footer flag
                    start += 10
            fh.seek(min(start, max(size - 1, 0)))
            data = fh.read(131072)
    except OSError:
        return 0.0

    if start >= size:
        return 0.0

    bitrate = 0
    for i in range(0, max(len(data) - 4, 0)):
        if data[i] != 0xFF or (data[i + 1] & 0xE0) != 0xE0:
            continue
        version = (data[i + 1] >> 3) & 0x03
        layer = (data[i + 1] >> 1) & 0x03
        index = (data[i + 2] >> 4) & 0x0F
        rate_index = (data[i + 2] >> 2) & 0x03
        if version not in _SAMPLE_RATES or layer != 1 or rate_index == 3:
            continue
        table = _BITRATE_MPEG1 if version == 3 else _BITRATE_MPEG2
        if index in (0, 15) or not table[index]:
            continue
        bitrate = table[index] * 1000
        start += i                        # 音频真正开始的位置
        break
    if bitrate <= 0 or size <= start:
        return 0.0
    return (size - start) * 8.0 / bitrate
