# -*- coding: utf-8 -*-
"""掼蛋对局回放：结构化帧录制、落盘与还原。

旧版的出牌记录（``core.history``）只有纯文本，看不出每一手时各家的手牌，
没法真正「复盘」。本模块把每一次局面变化录成一帧：

* 直接用 :func:`games.guandan.serialize.serialize_match` 的快照格式（联机
  同步已经在用，天然包含四家的全部手牌、级牌、进贡进度、当前待压与结算）；
* 每帧再附带「这一刻看到的日志条数」与各家最近一手牌，回放时就能逐帧还原
  牌桌，并把所有人的牌**明着**摆出来。

落盘文件与文本日志同目录、同主名，后缀 ``.replay.json``：

    logs/guandan/guandan-YYYYmmdd-HHMMSS-xxxxxx.txt
    logs/guandan/guandan-YYYYmmdd-HHMMSS-xxxxxx.replay.json

旧记录没有对应的 ``.replay.json``，自然不会出现在回放列表里；历史页仍能
照常看它们的文字记录。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from core import history

from .engine import (
    Hand,
    HandResult,
    MatchState,
    load_match,
    new_match,
    result_from_json,
    serialize_match,
)
from .rules import Combo
from .serialize import _combo_from_json, _combo_to_json

REPLAY_VERSION = 1
REPLAY_SUFFIX = ".replay.json"


class ReplayRecorder:
    """录一整场：每调用一次 :meth:`capture` 存一帧。"""

    def __init__(self) -> None:
        self.frames: List[Dict[str, Any]] = []

    def __len__(self) -> int:
        return len(self.frames)

    def capture(self, match: MatchState, hand: Hand,
                result: Optional[HandResult], label: str,
                log_count: int,
                last_plays: Optional[Dict[int, Combo]] = None) -> None:
        """录下当前局面。

        ``log_count`` 是当时已写出的日志条数；回放时只显示前 ``log_count`` 条，
        这样「打到哪一步」和「事件记录到哪一行」永远对齐，不用把日志复制
        几百份。
        """
        plays: Dict[str, Any] = {}
        for seat, combo in (last_plays or {}).items():
            raw = _combo_to_json(combo)
            if raw is not None:
                plays[str(seat)] = raw
        self.frames.append({
            "label": str(label),
            "log": max(0, int(log_count)),
            "s": serialize_match(match, hand, result),
            "plays": plays,
        })


def replay_path_for_log(log_path: Path) -> Path:
    """文本日志路径 -> 同主名的回放文件路径。"""
    return Path(log_path).with_suffix(REPLAY_SUFFIX)


def save_replay(log_path: Path, recorder: ReplayRecorder, *,
                meta: Dict[str, Any], logs: Sequence[str],
                log_meta: Sequence[Tuple[str, bool]],
                seats: Sequence[str], local_seat: int,
                controllers: Sequence[str]) -> Path:
    """把录好的帧写到文本日志旁边；失败返回空 ``Path``（不抛异常）。"""
    try:
        path = replay_path_for_log(log_path)
        doc = {
            "version": REPLAY_VERSION,
            "game": "guandan",
            "created": datetime.now().isoformat(timespec="seconds"),
            "meta": {str(k): str(v) for k, v in meta.items()},
            "logs": [str(x) for x in logs],
            "log_meta": [[str(c), bool(b)] for c, b in log_meta],
            "seats": [str(x) for x in seats],
            "local_seat": int(local_seat),
            "controllers": [str(x) for x in controllers],
            "frames": list(recorder.frames),
        }
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return path
    except Exception:                                  # noqa: BLE001
        return Path()


def load_replay(path: Path) -> Optional[Dict[str, Any]]:
    """读回放文件；格式不对 / 文件坏了一律返回 ``None``。"""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or doc.get("game") != "guandan":
        return None
    if not isinstance(doc.get("frames"), list) or not doc["frames"]:
        return None
    doc.setdefault("logs", [])
    doc.setdefault("log_meta", [])
    doc.setdefault("meta", {})
    doc.setdefault("seats", ["human", "ai", "ai", "ai"])
    doc.setdefault("local_seat", 0)
    doc.setdefault("controllers", ["你", "电脑", "电脑", "电脑"])
    return doc


def list_replays() -> List[Tuple[Path, Dict[str, Any]]]:
    """按时间倒序列出所有可回放的对局 ``[(路径, 文档), ...]``。"""
    try:
        directory = history.logs_dir("guandan")
        pairs: List[Tuple[Path, Dict[str, Any]]] = []
        for path in directory.glob("*" + REPLAY_SUFFIX):
            doc = load_replay(path)
            if doc is not None:
                pairs.append((path, doc))
    except OSError:
        return []
    pairs.sort(key=lambda item: item[0].stat().st_mtime, reverse=True)
    return pairs


def frame_state(doc: Dict[str, Any], index: int) -> Optional[Dict[str, Any]]:
    """把第 ``index`` 帧还原成牌桌能直接用的局面；坏帧返回 ``None``。"""
    frames = doc.get("frames") or []
    if not (0 <= index < len(frames)):
        return None
    frame = frames[index]
    if not isinstance(frame, dict):
        return None
    raw = frame.get("s") or {}
    match = new_match()
    hand = load_match(match, raw)
    if hand is None:
        return None
    result = result_from_json(raw.get("res"))

    plays: Dict[int, Combo] = {}
    for key, combo_raw in (frame.get("plays") or {}).items():
        try:
            seat = int(key)
        except (TypeError, ValueError):
            continue
        combo = _combo_from_json(combo_raw)
        if combo is not None:
            plays[seat] = combo

    logs = list(doc.get("logs") or [])
    metas = list(doc.get("log_meta") or [])
    try:
        count = max(0, int(frame.get("log", 0)))
    except (TypeError, ValueError):
        count = 0
    count = min(count, len(logs))
    return {
        "match": match,
        "hand": hand,
        "result": result,
        "plays": plays,
        "label": str(frame.get("label", "")),
        "logs": logs[:count],
        "log_meta": metas[:count],
    }
