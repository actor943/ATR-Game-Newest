# -*- coding: utf-8 -*-
"""本机档案：昵称 + 上次用过的房间码（跨次启动持久化）。

为什么单独一个文件
-------------------
``core/settings.py`` 管的是**应用设置**（主题 / 窗口模式），而昵称与房间码
属于**使用者本人的档案**，两件事生命周期不同（卸载重装、换设备都不该共用），
所以单独落在同目录的 ``profile.json`` 里。

两件事
------
1. **昵称**：第一次进房间时如果用户没起过名，就随机分配一个（中世纪/RPG 味，
   配合「暗黑2 + MC」的房间界面），并立刻写回本地；之后一律用这个名字。
2. **房间码**：建立房间时用的房间码会被记住，下次再建房间自动填上，
   不用每次想新口令（用户明确要求的「本地保存、下次复用」）。
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from .settings import _config_dir

PROFILE_FILE = "profile.json"

# 随机起名池：形容词 + 名号，凑出「沉默的拾荒者」这类 Rougelike 味的名字。
# 不用生僻字，方便房间里的同伴念出来（语音聊天要用）。
_TITLES = (
    "沉默的", "流浪的", "孤高的", "拾荒的", "守夜的", "锈剑的", "燃灰的",
    "破晓的", "霜语的", "暗巷的", "赤瞳的", "旧王的", "荒野的", "锻铁的",
    "苦行的", "游荡的", "挑灯的", "断刃的",
)
_NAMES = (
    "拾荒者", "守塔人", "旅法师", "铁匠", "猎人", "盗火者", "行脚商",
    "雇佣兵", "看门人", "掘墓人", "制图师", "驯兽师", "吟游诗人", "苦修士",
    "海盗", "骑士", "炼金术士", "哨兵", "流浪汉", "幸存者",
)

# 英文池：切到 English 时随机名也跟着换一套（不然房间里念不出中文名）
_TITLES_EN = (
    "Silent", "Wandering", "Lonely", "Rusty", "Ashen", "Grim", "Hollow",
    "Iron", "Frost", "Ember", "Dusty", "Broken", "Quiet", "Wild",
    "Bitter", "Restless", "Pale", "Old",
)
_NAMES_EN = (
    "Scavenger", "Watchman", "Wanderer", "Blacksmith", "Hunter",
    "Firethief", "Peddler", "Mercenary", "Gatekeeper", "Gravedigger",
    "Cartographer", "Beastmaster", "Bard", "Hermit", "Pirate", "Knight",
    "Alchemist", "Sentry", "Vagabond", "Survivor",
)

# 房间码用字：去掉 0/O/1/I 等容易念错也容易看错的字符，
# 房间码是要**口头报给同局域网同伴**的（语音/口头），必须好念。
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LEN = 6


def random_nick() -> str:
    """随机生成一个昵称，例如「沉默的拾荒者」/ "Silent Scavenger"。

    按当前界面语言挑词库：中文库配石砖风的房间，英文库配英文界面 ——
    房间里要靠嘴念名字，念不出来的名字没有意义。
    """
    from .i18n import current as current_lang

    if current_lang().startswith("en"):
        return f"{random.choice(_TITLES_EN)} {random.choice(_NAMES_EN)}"
    return f"{random.choice(_TITLES)}{random.choice(_NAMES)}"


def random_code(length: int = CODE_LEN) -> str:
    """随机生成一个房间码（默认 6 位，去歧义字符）。"""
    return "".join(random.choice(CODE_ALPHABET) for _ in range(length))


def normalize_code(code: str) -> str:
    """规范化输入的房间码：去空白、转大写。

    房间码不区分大小写 —— 同伴口头报过来时很难确认大小写。
    """
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


@dataclass
class Profile:
    """本机使用者档案。"""

    nick: str = ""              # 空串表示「还没起过名」
    last_room_code: str = ""    # 上次建房间用的房间码
    last_room_name: str = ""    # 上次建房间用的房间名（顺带记住，方便复用）
    data: dict = field(default_factory=dict)

    # ---------------- 读写 ----------------

    @classmethod
    def path(cls, path: Optional[Path] = None) -> Path:
        return path or (_config_dir() / PROFILE_FILE)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Profile":
        p = cls.path(path)
        if not p.exists():
            return cls()
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        if not isinstance(raw, dict):
            return cls()
        data = raw.get("data") or {}
        return cls(
            nick=str(raw.get("nick", "") or ""),
            last_room_code=str(raw.get("last_room_code", "") or ""),
            last_room_name=str(raw.get("last_room_name", "") or ""),
            data=data if isinstance(data, dict) else {},
        )

    def save(self, path: Optional[Path] = None) -> Optional[Path]:
        """写回本地；失败返回 None（不影响主流程）。"""
        p = self.path(path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(
                json.dumps(asdict(self), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            return None
        return p

    # ---------------- 昵称 ----------------

    @property
    def named(self) -> bool:
        """用户是否起过名（自己起的，不是随机的）。"""
        return bool(self.nick)

    def ensure_nick(self, path: Optional[Path] = None) -> str:
        """保证有一个能用的昵称：没起过就随机分配并写回本地。

        房间里加入的新人如果没有名字，就调用这里 —— 这就是用户说的
        「加进来的没有起过名的人将随机起名」。
        """
        if not self.nick:
            self.nick = random_nick()
            self.save(path)
        return self.nick

    def set_nick(self, nick: str, path: Optional[Path] = None) -> str:
        """改昵称（Profile 页 / 主页右下角「我的」用）。"""
        nick = (nick or "").strip()
        if nick:
            self.nick = nick[:16]
            self.save(path)
        return self.nick

    # ---------------- 房间码 ----------------

    def remember_room(self, name: str, code: str,
                      path: Optional[Path] = None) -> None:
        """记住这次建房间用的名字与房间码，下次自动填上。"""
        self.last_room_name = (name or "").strip()[:24]
        self.last_room_code = normalize_code(code)
        self.save(path)


def ensure_nick() -> str:
    """快捷方式：加载档案并保证有昵称。"""
    return Profile.load().ensure_nick()
