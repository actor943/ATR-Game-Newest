# -*- coding: utf-8 -*-
"""掼蛋全模拟观战页的「配色 / 尺寸 / 牌图工具」。

观战页没有「我方」视角，所以逢人配统一用金色框、队色用蓝 / 橙两色。
把这些常量与画牌图的小工具单独放一个文件，改配色时只动这里。
"""

from __future__ import annotations

import flet as ft

from core.theme import T
from games.guandan.assets import card_image_src
from games.guandan.cards import wild_owner

TEAM_COLOR = ("#3B82F6", "#F59E0B")   # 队0 蓝 / 队1 橙
BOMB_COLOR = "#EF4444"
WIN_COLOR = "#10B981"
HEAD_COLOR = "#8B5CF6"
TURN_COLOR = "#FBBF24"
MUTED = "#9CA3AF"
SURFACE = "#1F2937"
SURFACE_ALT = "#374151"
TEXT = "#F9FAFB"

PLAYER_NAMES = ("甲", "乙", "丙", "丁")
OUT_NAMES = ("头游", "二游", "三游", "末游")
SPEEDS = (("慢", 0.9), ("中", 0.45), ("快", 0.15), ("极快", 0.03))

CARD_W, CARD_H = 34, 48               # 手牌牌图尺寸
PLAY_W, PLAY_H = 48, 67               # 最近出牌牌图尺寸（略大）
HAND_SPACING = -10                     # 手牌重叠像素
# 窄屏（手机）适配：27 张 × 净宽 24 ≈ 650dp，手机只有 360dp，原来靠 wrap 硬挤，
# 重叠得太狠认不出牌。现在先加大重叠、再整体缩小牌面，保证一张都不被切掉。
MIN_CARD_STEP = 20                     # 叠放时每张至少露出的像素
MIN_CARD_W = 24                        # 牌面缩到这个宽就不再缩了
SIM_MAX_ROWS = 2                       # 一家手牌最多占几行（观战页地方有限）
# 可用宽度 = 页宽 − 页面内边距 − 区块内边距 − 边框 − 余量
HAND_WIDTH_MARGIN = T.PADDING * 2 + 10 * 2 + 2 + 8
MAX_EVENTS = 40# 近期事件保留条数（超出自动裁剪，滚动查看）
EVENTS_HEIGHT = 112                # 事件窗口固定高度（≈6 行），超出由内部 Column 滚动
EVENT_LINE_H = 18
LEVEL_GOLD = "#FFD54F"                     # 级牌金框（观战无「我方」，统一金色）
WILD_MINE = "#FF4D4F"                     # 甲丙的逢人配
WILD_THEIRS = "#FF8A65"                   # 乙丁的逢人配
WILD_SHARED = "#F06292"                   # 双方共有的逢人配


def wild_border(card, ctx):
    """观战下按归属区分两个逢人配（0=甲丙 1=乙丁 共用=粉）。"""
    teams = wild_owner(card, ctx)
    if not teams:
        return None
    if len(teams) == 2:
        return WILD_SHARED
    return WILD_MINE if teams[0] == 0 else WILD_THEIRS


def card_tile(card, ctx, width: int, height: int) -> ft.Control:
    """一张牌图：逢人配按归属上色、级牌金框，tooltip 说明身份。

    双方级数不同时有两个不同的逢人配，必须按归属区分，否则看不出谁在借谁的牌。
    """
    wcolor = wild_border(card, ctx)
    is_lv = not card.is_joker and ctx.is_level_rank(card.rank)
    tip = str(card)
    if wcolor:
        tip += (f"（逢人配·万能牌·可当任意牌·"
                f"{ctx.level_owner_label(card.rank)}的）")
    elif is_lv:
        tip += f"（级牌·{ctx.level_owner_label(card.rank)}）"
    if not wcolor and not is_lv:
        return ft.Image(src=card_image_src(card), width=width, height=height,
                        fit=ft.BoxFit.CONTAIN, tooltip=tip)
    return ft.Container(
        content=ft.Image(src=card_image_src(card), width=width, height=height,
                         fit=ft.BoxFit.CONTAIN, tooltip=tip),
        border=ft.Border.all(2, wcolor or LEVEL_GOLD),
        border_radius=4,
    )


def _pname(p: int) -> str:
    return PLAYER_NAMES[p]
