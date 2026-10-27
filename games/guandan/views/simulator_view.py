# -*- coding: utf-8 -*-
"""掼蛋全模拟观战页：在本机跑一整场 AI 对局，把过程实时画出来。

用来欣赏 AI 打法、演示规则 —— 不联网、不需要房间，一个人就能看。

模块划分
--------
* :mod:`games.guandan.views.sim_const`    —— 配色 / 尺寸 / 画牌图工具
* :mod:`games.guandan.views.sim_session`  —— 观战会话（跑牌 + 渲染）
* 本文件                                —— 页面入口（组装控制条与画面）
"""

from __future__ import annotations

from typing import List

import flet as ft

from core.registry import NavigateFn
from core.theme import T
from core.ui_common import app_bar, page_padding
from games.guandan.views.sim_const import (
    EVENTS_HEIGHT,
    HAND_SPACING,
    MUTED,
    SPEEDS,
    SURFACE,
    SURFACE_ALT,
)
from games.guandan.views.sim_session import _Session

def build(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """全模拟视图：状态栏 + 4 家手牌 + 最近出牌 + 近期事件 + 控制。"""
    go_back = lambda _e: navigate("/g/guandan")

    # 四家手牌：header + Row（重叠排列）
    hand_rows: List[ft.Row] = [
        ft.Row(wrap=True, spacing=HAND_SPACING, run_spacing=4) for _ in range(4)
    ]
    hand_headers: List[ft.Text] = [
        ft.Text("", size=13, weight=ft.FontWeight.BOLD) for _ in range(4)
    ]
    player_sections: List[ft.Control] = []
    for p in range(4):
        player_sections.append(
            ft.Container(
                content=ft.Column(
                    [hand_headers[p],
                     ft.Container(height=4),
                     hand_rows[p]],
                    spacing=0,
                ),
                padding=ft.Padding.all(10),
                border=ft.Border.all(1, SURFACE_ALT),
                border_radius=8,
                bgcolor=SURFACE,
            )
        )

    # 最近出牌
    last_play_label = ft.Text("（暂无出牌）", size=14,
                              weight=ft.FontWeight.BOLD)
    last_play_row = ft.Row(wrap=True, spacing=-6, run_spacing=4,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER)
    last_play_section = ft.Container(
        content=ft.Column(
            [ft.Text("── 最近出牌 ──", size=11, color=MUTED),
             ft.Container(height=4),
             last_play_label,
             ft.Container(height=6),
             last_play_row],
            spacing=0,
        ),
        padding=ft.Padding.all(10),
        border=ft.Border.all(1, SURFACE_ALT),
        border_radius=8,
        bgcolor=SURFACE,
    )

    # 近期事件：单ft.Text + spans（继承 0.4.3 终端模式，Mac 可整段复制）
    events_text = ft.Text(
        value="",
        spans=[],
        selectable=True,
        font_family="monospace",
        size=12,
        no_wrap=False,
        opacity=1.0,
        animate_opacity=0,
        animate_size=0,
    )
    # 关键（同 0.4.3 终端）：固定高度窗口 + 内部 Column 负责滚动
    events_inner = ft.Column(
        controls=[events_text],
        scroll=ft.ScrollMode.AUTO,
        auto_scroll=True,                   # 新行自动跟随到底部
        expand=True,
        spacing=0,
        animate_opacity=0,
        animate_size=0,
    )
    events_box = ft.Container(
        content=events_inner,
        height=EVENTS_HEIGHT,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        opacity=1.0,
        animate_opacity=0,
        animate_size=0,
    )
    events_section = ft.Container(
        content=ft.Column(
            [ft.Text("── 近期事件 ──", size=11, color=MUTED),
             ft.Container(height=4),
             events_box],
            spacing=0,
        ),
        padding=ft.Padding.all(10),
        border=ft.Border.all(1, SURFACE_ALT),
        border_radius=8,
        bgcolor=SURFACE,
        opacity=1.0,
        animate_opacity=0,
    )

    # 状态栏 + 控制
    status = ft.Text("未开始", size=13, weight=ft.FontWeight.BOLD,
                     color=T.TEXT_PRIMARY)
    play_btn = ft.Button(content=ft.Text("▶ 播放"), height=38,
                         bgcolor=T.PRIMARY, color=T.TEXT_INVERT)
    speed_btn = ft.Button(
        content=ft.Text(f"速度: {SPEEDS[1][0]}"), height=38,
        bgcolor=T.SURFACE_ALT, color=T.TEXT_PRIMARY)

    session = _Session(page, hand_rows, hand_headers,
                       last_play_label, last_play_row,
                       events_text, status, events_inner,
                       play_btn, speed_btn)

    # ---------- 控制条按钮 ----------
    def on_play(_e):

        """播放 / 暂停。"""
        playing = session.toggle()
        play_btn.content.value = "⏸ 暂停" if playing else "▶ 播放"
        play_btn.bgcolor = T.ACCENT if playing else T.PRIMARY
        page.update()

    def on_step(_e):

        """单步。"""
        play_btn.content.value = "▶ 播放"
        play_btn.bgcolor = T.PRIMARY
        session.single_step()

    def on_new(_e):

        """换一场新的。"""
        play_btn.content.value = "▶ 播放"
        play_btn.bgcolor = T.PRIMARY
        session.new_game()

    def on_speed(_e):

        """切换速度。"""
        session.cycle_speed()
        speed_btn.content.value = f"速度: {SPEEDS[session.speed_idx][0]}"
        page.update()

    play_btn.on_click = on_play
    speed_btn.on_click = on_speed

    buttons = ft.Row(
        [
            play_btn,
            ft.Button(content=ft.Text("单步"), icon=ft.Icons.SKIP_NEXT,
                      on_click=on_step, height=38,
                      bgcolor=T.SURFACE_ALT, color=T.TEXT_PRIMARY),
            ft.Button(content=ft.Text("新一场"), icon=ft.Icons.REFRESH,
                      on_click=on_new, height=38,
                      bgcolor=T.SURFACE_ALT, color=T.TEXT_PRIMARY),
            speed_btn,
        ],
        spacing=10,
        wrap=True,
    )

    body = ft.Column(
        [status,
         ft.Container(height=8),
         *player_sections,
         ft.Container(height=8),
         last_play_section,
         ft.Container(height=8),
         events_section,
         ft.Container(height=8),
         buttons],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    return ft.Column(
        [
            app_bar("全模拟", on_back=go_back),
            page_padding(body),
        ],
        expand=True,
    )
