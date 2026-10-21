# -*- coding: utf-8 -*-
"""掼蛋对局配置：座位分配（人 / 机）与预设。

单独成模块、不依赖 flet，方便单测，也方便将来把配置搬进独立文件
（``MatchConfig.to_dict`` / :meth:`MatchConfig.from_dict` 已按 JSON 友好设计）。

座位编号沿用引擎约定：0=甲 1=乙 2=丙 3=丁，其中甲丙一队、乙丁一队
（见 :data:`games.guandan.engine.TEAM_OF`）。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional, Tuple

# 座位类型
SEAT_HUMAN = "human"
SEAT_AI = "ai"

SEAT_NAMES = ("甲", "乙", "丙", "丁")
NUM_SEATS = 4

# 配置文件在 Settings.data 里的键
_SETTINGS_KEY = "guandan_match"


@dataclass(frozen=True)
class Preset:
    """一个可一键套用的座位预设。"""

    key: str
    title: str
    description: str
    seats: Tuple[str, ...]


# ============================================================
# 预设：默认给两种
# ============================================================

PRESETS: Dict[str, Preset] = {
    "single": Preset(
        key="single",
        title="单人",
        description="你 1 人，对面 3 个电脑。最快上手。",
        seats=(SEAT_HUMAN, SEAT_AI, SEAT_AI, SEAT_AI),
    ),
    "three_ai": Preset(
        key="three_ai",
        title="三人机",
        description="3 个真人 + 1 个电脑补位（掼蛋常见房型）。",
        seats=(SEAT_HUMAN, SEAT_HUMAN, SEAT_HUMAN, SEAT_AI),
    ),
}

DEFAULT_PRESET = "single"


# ============================================================
# 配置本体
# ============================================================


@dataclass(frozen=True)
class MatchConfig:
    """一场对局的座位配置。

    ``seats`` 逐座标记「真人」或「电脑」；``local_seat`` 是本机玩家操控的座位。
    在只有一个本地玩家的前提下，除 ``local_seat`` 之外的真人座位由本机托管
    （界面会标注「托管」），这样「三人机」的配置语义可以原样留给将来的联机版。
    """

    seats: Tuple[str, ...] = PRESETS[DEFAULT_PRESET].seats
    local_seat: int = 0
    preset: str = DEFAULT_PRESET
    # 联机房间开起来的对局，本机玩家用这个昵称替代「你」（空串=单人模式仍显示「你」）
    local_nick: str = ""

    # ---- 查询 ----

    def seat_kind(self, seat: int) -> str:
        return self.seats[seat]

    def is_human(self, seat: int) -> bool:
        return self.seats[seat] == SEAT_HUMAN

    def is_local(self, seat: int) -> bool:
        """是否由本机玩家亲手操作。"""
        return seat == self.local_seat

    def is_auto(self, seat: int) -> bool:
        """是否由电脑代打（电脑位，或非本机的真人位=托管）。"""
        return not self.is_local(seat)

    def controller(self, seat: int) -> str:
        """界面上的控制器标签。"""
        if self.is_local(seat):
            return self.local_nick or "你"
        return "托管" if self.is_human(seat) else "电脑"

    def human_count(self) -> int:
        return sum(1 for s in self.seats if s == SEAT_HUMAN)

    def team_of(self, seat: int) -> int:
        """0/2 一队返回 0，1/3 一队返回 1。"""
        return 0 if seat % 2 == 0 else 1

    def my_team(self) -> int:
        return self.team_of(self.local_seat)

    def summary(self) -> str:
        parts = [
            f"{SEAT_NAMES[p]}·{self.controller(p)}" for p in range(NUM_SEATS)
        ]
        return "  ".join(parts)

    # ---- 变更 ----

    def with_seat(self, seat: int, kind: str) -> "MatchConfig":
        """把某个座位设为真人/电脑；四个座位不能全是电脑（那就没人玩了）。"""
        if kind not in (SEAT_HUMAN, SEAT_AI):
            raise ValueError(f"未知的座位类型：{kind}")
        new = list(self.seats)
        new[seat] = kind
        if all(k == SEAT_AI for k in new):
            raise ValueError("至少要保留一个真人座位")
        return replace(self, seats=tuple(new), preset="custom")

    def with_local_seat(self, seat: int) -> "MatchConfig":
        if not self.is_human(seat):
            raise ValueError("本机玩家只能坐在真人座位上")
        return replace(self, local_seat=seat)

    @classmethod
    def from_preset(cls, key: str) -> "MatchConfig":
        preset = PRESETS.get(key, PRESETS[DEFAULT_PRESET])
        return cls(seats=preset.seats, local_seat=0, preset=preset.key)

    # ---- 序列化（为将来加载配置文件预留）----

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "preset": self.preset,
            "local_seat": self.local_seat,
            "seats": list(self.seats),
        }

    @classmethod
    def from_dict(cls, raw: Optional[dict]) -> "MatchConfig":
        """容错读取：任何字段缺失/非法都退回默认值，不抛异常。"""
        if not isinstance(raw, dict):
            return cls.from_preset(DEFAULT_PRESET)
        seats = raw.get("seats")
        if not isinstance(seats, list) or len(seats) != NUM_SEATS:
            return cls.from_preset(DEFAULT_PRESET)
        cleaned = tuple(
            s if s in (SEAT_HUMAN, SEAT_AI) else SEAT_AI for s in seats
        )
        if all(s == SEAT_AI for s in cleaned):
            return cls.from_preset(DEFAULT_PRESET)
        local = raw.get("local_seat", 0)
        if not isinstance(local, int) or not 0 <= local < NUM_SEATS:
            local = 0
        if cleaned[local] != SEAT_HUMAN:
            local = cleaned.index(SEAT_HUMAN)
        preset = raw.get("preset")
        if not isinstance(preset, str):
            preset = "custom"
        return cls(seats=cleaned, local_seat=local, preset=preset)


# ============================================================
# 便捷函数
# ============================================================


def default_config() -> MatchConfig:
    """默认配置：单人。"""
    return MatchConfig.from_preset(DEFAULT_PRESET)


def from_preset(key: str) -> MatchConfig:
    """按预设键取配置（未知键回落到默认）。"""
    return MatchConfig.from_preset(key)


def preset_list():
    """按插入顺序返回全部预设，供设置界面渲染。"""
    return list(PRESETS.values())


# ============================================================
# 会话共享：设置页写入，牌桌页读取
# ============================================================

_active: MatchConfig = MatchConfig.from_preset(DEFAULT_PRESET)


def active() -> MatchConfig:
    """当前生效的配置（进程启动时从持久化设置里读）。"""
    return _active


def set_active(cfg: MatchConfig) -> None:
    """设置当前配置，并写入持久化设置（下次启动沿用）。"""
    global _active
    _active = cfg
    _persist(cfg)


# ============================================================
# 房间名（联机版本的房间标识；本版只做持久化，不参与匹配）
# ============================================================

_ROOM_NAME_KEY = "guandan_room_name"
DEFAULT_ROOM_NAME = "掼蛋房间"
_room_name: str = ""


def room_name() -> str:
    """当前房间名。"""
    return _room_name or DEFAULT_ROOM_NAME


def set_room_name(name: str) -> None:
    """保存房间名（下次启动沿用）。"""
    global _room_name
    name = (name or "").strip() or DEFAULT_ROOM_NAME
    _room_name = name
    try:
        from core.settings import Settings

        st = Settings.load()
        st.data[_ROOM_NAME_KEY] = name
        st.save()
    except Exception:
        # 写不进去不影响本次游戏
        pass


def _load_room_name() -> None:
    """启动时把持久化的房间名读进内存。"""
    global _room_name
    try:
        from core.settings import Settings

        raw = Settings.load().data.get(_ROOM_NAME_KEY)
        _room_name = raw.strip() if isinstance(raw, str) and raw.strip() \
            else DEFAULT_ROOM_NAME
    except Exception:
        _room_name = DEFAULT_ROOM_NAME


_load_room_name()


def _persist(cfg: MatchConfig) -> None:
    try:
        from core.settings import Settings

        st = Settings.load()
        st.data[_SETTINGS_KEY] = cfg.to_dict()
        st.save()
    except Exception:
        # 配置文件写不进去不影响本次游戏
        pass


def _load() -> MatchConfig:
    """启动时把持久化的座位配置读进内存。"""
    global _active
    try:
        from core.settings import Settings

        raw = Settings.load().data.get(_SETTINGS_KEY)
        _active = MatchConfig.from_dict(raw)
    except Exception:
        _active = MatchConfig.from_preset(DEFAULT_PRESET)
    return _active


_load()