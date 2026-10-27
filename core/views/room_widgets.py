# -*- coding: utf-8 -*-
"""房间大厅的「界面零件」那一半：席位区、语音区、聊天区。

这些方法只负责**把数据画出来 / 把点击翻译成动作**，不碰网络协议，
所以单独拆成一个 mixin（:class:`RoomWidgetsMixin`），
由 :class:`core.views.room_view._Lobby` 继承。
"""

from __future__ import annotations

from typing import List, Optional

import flet as ft

from core import ui_theme as ui
from core.i18n import t
from core.net.session import RoomSession
from core.net.voice import AUDIO_OK
from core.registry import game_players

MAX_CHAT = 200              # 聊天记录最多留多少条

class RoomWidgetsMixin:
    """席位 / 语音 / 聊天三块界面零件。"""

    # ---------- 三块界面零件 ----------
    def _seats_area(self, session: RoomSession) -> ft.Control:

        """席位区：几个位子排成一行，空位点一下就坐过去。"""
        return ui.panel(
            ft.Column(
                [
                    ui.text(t("room.seats"), 13, "gold", ft.FontWeight.BOLD),
                    ft.Container(height=10),
                    self.seat_row,
                    ft.Container(height=8),
                    ui.hint(t("room.seats_hint")),
                ],
                spacing=0,
            )
        )

    def _voice_area(self, session: RoomSession) -> ft.Control:

        """语音区：麦克风开关 + 电平条 + 扬声器开关。"""
        tip_text = t("room.voice_tip") if AUDIO_OK else t("room.voice_unavailable")
        if not AUDIO_OK and session.voice.reason:
            # 把真实原因带上（模块缺失 / PortAudio 加载失败 / 设备打不开）：
            # 0.4.8 实测「分发版没有语音库」就是靠这一行区分出来的 ——
            # 只有笼统文案时，打包漏依赖和本机缺 PortAudio 看起来一模一样。
            tip_text = f"{tip_text}（{session.voice.reason}）"
        self._voice_row = ft.Row(
            [
                ui.button(t("room.mic_on"), "🎤", self._toggle_mic, height=40),
                ft.Container(width=10),
                ui.button(t("room.speaker_off"), "🔊", self._toggle_speaker,
                          height=40),
                ft.Container(width=14),
                ft.Column([ui.text(t("room.level"), 10, "dim"), self.level],
                          spacing=2),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=True,
        )
        return ui.panel(
            ft.Column(
                [
                    ui.text(t("room.voice"), 13, "gold", ft.FontWeight.BOLD),
                    ft.Container(height=10),
                    self._voice_row,
                    ft.Container(height=8),
                    ui.hint(tip_text),
                ],
                spacing=0,
            )
        )

    def _chat_area(self, session: RoomSession) -> ft.Control:

        """聊天区：一个输入框 + 消息列表。"""
        return ui.panel(
            ft.Column(
                [
                    ui.text(t("room.chat"), 13, "gold", ft.FontWeight.BOLD),
                    ft.Container(height=8),
                    ui.scroll_box(self.chat_col, height=180),
                    ft.Container(height=8),
                    # 输入行 + 按钮行分开：wrap 的 Row 里放 expand 输入框
                    # 会被撑成一块灰墙（见 _head 的注释）
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.TextField(
                                    ref=self.input_ref,
                                    hint_text=t("room.chat_placeholder"),
                                    border=ft.InputBorder.OUTLINE, text_size=14,
                                    color=ui.colors().text,
                                    bgcolor=ui.colors().ink,
                                    on_submit=self._send,
                                    hint_style=ft.TextStyle(
                                        color=ui.colors().text_muted,
                                        size=13),
                                ),
                                border=ft.Border.all(1, ui.colors().border),
                                border_radius=8, expand=True,
                                padding=ft.Padding.symmetric(horizontal=8),
                            ),
                            ft.Container(width=8),
                            ui.button(t("room.send"), "✉", self._send,
                                      height=44),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(height=8),
                    ft.Row(
                        [
                            ui.button(t("room.start") if session.is_host
                                      else t("room.wait_start"),
                                      "⚔", self._begin,
                                      primary=session.is_host,
                                      enabled=session.is_host, height=44),
                        ],
                    ),
                ],
                spacing=0,
            )
        )

    # ---------- 重画 ----------
    def _render_seats(self) -> None:

        """重画席位区（有人进出、有人说话时刷新）。"""
        session = self.session
        if session is None:
            return
        members = session.roster()
        by_seat = {m.seat: m for m in members if m.seat >= 0}
        players = game_players(session.info.game_id)
        cells: List[ft.Control] = []
        for i in range(session.info.seats):
            spectator = i >= players          # 超出游戏人数的席位是观战席
            member = by_seat.get(i)
            if member is None:
                label = (t("room.empty_seat", n=i + 1)
                         + (t("room.spectator") if spectator else ""))
                cells.append(ui.slot(label, on_click=self._take_seat(i)))
                continue
            peer = (member.ip, member.voice_port)
            talking = bool(member.voice_port) and session.voice.is_talking(peer)
            suffix = t("room.spectator") if spectator else ""
            cells.append(ui.taken_slot(
                member.nick + suffix, host=member.host, talking=talking,
                muted=not member.mic_on))
        # 还没坐下的人（席位满了 / 刚进来）一律算观战
        for member in members:
            if member.seat >= 0:
                continue
            cells.append(ui.taken_slot(member.nick + t("room.spectator_paren"),
                                       host=member.host, muted=True))
        self.seat_row.controls = cells

    def _render_voice_buttons(self) -> None:
        """把麦克风 / 扬声器按钮换成当前状态对应的文案。"""
        if self.session is None or self._voice_row is None:
            return
        self._voice_row.controls = [
            ui.button(t("room.mic_off") if self.mic_on else t("room.mic_on"),
                      "🎤" if self.mic_on else "🔇",
                      self._toggle_mic, height=40),
            ft.Container(width=10),
            ui.button(t("room.speaker_on") if not self.speaker_on
                      else t("room.speaker_off"),
                      "🔊" if self.speaker_on else "🔈",
                      self._toggle_speaker, height=40),
            ft.Container(width=14),
            ft.Column([ui.text(t("room.level"), 10, "dim"), self.level],
                      spacing=2),
        ]

    # ---------- 往聊天区追加消息 ----------
    def system(self, text: str) -> None:

        """在聊天区插一条系统消息（居中灰色那种）。"""
        self._append(None, text)

    def _append_chat(self, nick: str, text: str, own: bool = False) -> None:

        """在聊天区插一条某人说的消息。"""
        self._append({"nick": nick, "text": text}, None, own)

    def _append(self, item, system_text: Optional[str] = None,
                own: bool = False) -> None:

        """往消息列表里追加一条（带自动滚动）。"""
        if system_text is not None:
            self.chat_lines.append(ui.chat_row("", system_text, system=True))
        elif item is not None:
            self.chat_lines.append(ui.chat_row(item["nick"], item["text"],
                                               own=own))
        if len(self.chat_lines) > MAX_CHAT:
            del self.chat_lines[:len(self.chat_lines) - MAX_CHAT]
        self.chat_col.controls = self.chat_lines
