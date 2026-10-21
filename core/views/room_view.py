# -*- coding: utf-8 -*-
"""房间大厅：席位、语音、聊天都在这一屏（联机的大厅）。

一屏三件事
----------
1. **席位**：房间里几个位子一目了然。空位点一下就坐过去（换座同理）；
   有人说话时他的头像边框会亮起来 —— 这是语音的即时反馈。
2. **语音**：麦克风 / 扬声器开关 + 麦克风电平条。采集到的每一帧 20ms 音频
   直接 UDP 单点发给房间里其他人，没有服务器中转（见 ``core/net/voice.py``）。
3. **聊天**：打字也行 —— 房主负责把消息转发给所有人，保证大家看到的顺序一致。

房主点「开始」会广播一声开始，然后所有人一起进到具体游戏的房间里。

刷新机制
--------
网络线程只往队列里丢事件，这里用一个 asyncio 循环每 0.25 秒抽一次队列、
顺手刷新席位与电平条 —— **不在网络线程里碰任何控件**，避免多线程把界面搞崩。

界面风格
--------
所有零件走 :mod:`core.ui_theme`：默认材料风 / 暗黑2 石砖风 / 以后的社区包，
设置页切换后这一屏跟着换皮。
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

import flet as ft

from core import ui_theme as ui
from core.net import session as _sess
from core.net.session import RoomSession
from core.net.voice import AUDIO_OK
from core import registry
from core.registry import NavigateFn, game_players
from core.router import Router

POLL = 0.25                 # 界面刷新间隔（电平条需要一点点流畅度）
MAX_CHAT = 200              # 聊天记录最多留多少条

# 房间里「开始」把大家送去哪儿：每个已接好的游戏在这里登记它的对局路由。
# 0.4.7-fix2：直接进牌桌，不再走中间的「房间设置」页（那页已取消）。
GAME_ROOM_ROUTE = {
    "guandan": "/g/guandan/play",
    "chess": "/g/chess/play",
}


class _Lobby:
    def __init__(self, page: ft.Page, navigate: NavigateFn):
        self.page = page
        self.navigate = navigate
        self.session: Optional[RoomSession] = _sess.current()
        self.chat_lines: List[ft.Control] = []
        self.mic_on = False
        self.speaker_on = True
        self._polling = False
        self._voice_row: Optional[ft.Row] = None

        self.seat_row = ft.Row(wrap=True, spacing=10, run_spacing=10)
        self.chat_col = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO,
                                  auto_scroll=True, expand=True)
        self.input_ref = ft.Ref[ft.TextField]()
        self.tip = ui.hint("")
        self.head_info = ui.hint("")
        self.level = ft.Container(content=ui.level_bar(0.0))
        self.game_panel = ui.panel(ft.Column([ui.hint("")], spacing=0))

    # ================================================================
    # 构建
    # ================================================================

    def build(self) -> ft.Control:
        session = self.session
        if session is None:                     # 兜底：没房间就别硬待在这儿
            return ui.page(
                "多人房间",
                ui.panel(ft.Column([
                    ui.text("这里现在没有房间。", 14, ""),
                    ft.Container(height=10),
                    ui.button("回多人游戏", "🧭",
                              lambda _e: self.navigate("/multiplayer")),
                ], spacing=0)),
                on_back=lambda _e: self.navigate("/multiplayer"),
            )

        if not self._polling:
            self._polling = True
            self.page.run_task(self._poll)

        body = ft.Column(
            [
                self._head(session),
                ft.Container(height=12),
                self._game_selector_area(session),
                ft.Container(height=12),
                self._seats_area(session),
                ft.Container(height=12),
                self._voice_area(session),
                ft.Container(height=12),
                self._chat_area(session),
                ft.Container(height=10),
                self.tip,
            ],
            spacing=0, scroll=ft.ScrollMode.AUTO, expand=True,
        )
        self.system(f"进入房间「{session.info.name}」· "
                    f"{session.info.game_title}")
        self._render_seats()
        return ui.page("多人房间", body, on_back=self._on_leave)

    # ---------------- 各区块 ----------------

    def _head(self, session: RoomSession) -> ft.Control:
        self.head_info.value = (f"房主 {session.info.host} · "
                                f"{session.info.game_title} · "
                                f"{session.info.ip}:{session.info.port}")
        return ui.panel(
            ft.Column(
                [
                    # 注意：wrap=True 的 Row 里**不能**放 expand 占位 ——
                    # flet 会把剩余空间当成独立一行撑成一块灰色巨墙
                    # （0.4.7「没有底的诡异窗口」的另一半原因）。
                    # 想左右分开就用 SPACE_BETWEEN。
                    ft.Row(
                        [
                            ui.text(session.info.name or "房间", 17, "gold",
                                    ft.FontWeight.BOLD),
                            ui.pill(f"房间码 {session.code or '——'}"),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        wrap=True,
                    ),
                    ft.Container(height=6),
                    self.head_info,
                    ft.Container(height=4),
                    ui.hint("同一 WiFi / 局域网里的伙伴在「搜索房间」里"
                            "能看到这个房间，报房间码给他才能进来。"),
                ],
                spacing=0,
            )
        )

    def _seats_area(self, session: RoomSession) -> ft.Control:
        return ui.panel(
            ft.Column(
                [
                    ui.text("席位", 13, "gold", ft.FontWeight.BOLD),
                    ft.Container(height=10),
                    self.seat_row,
                    ft.Container(height=8),
                    ui.hint("点空位可以坐下 / 换座；🎤 是开着麦的，"
                            "🔇 是关了麦的，♛ 是房主。"
                            "超出本局人数的位子为观战席。"),
                ],
                spacing=0,
            )
        )

    # ---------------- 选游戏（房主可在房间内切换） ----------------

    def _game_selector_area(self, session: RoomSession) -> ft.Control:
        players = game_players(session.info.game_id)
        note = (f"{players} 人上场，多出来的人观战"
                if session.info.seats > players
                else f"{players} 人上场")
        if session.is_host:
            chips = [
                ui.chip(it.title, active=(it.id == session.info.game_id),
                        on_click=(lambda _e, gid=it.id,
                                  gt=it.title: self._set_room_game(gid, gt)))
                for it in registry.menu_items() if it.available
            ]
            inner = ft.Column(
                [
                    ui.text("选游戏（房主可切换）", 13, "gold", ft.FontWeight.BOLD),
                    ft.Container(height=6),
                    ft.Row(chips, wrap=True, spacing=6,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Container(height=6),
                    ui.hint(note),
                ],
                spacing=0,
            )
        else:
            inner = ft.Column(
                [
                    ui.text("本局游戏", 13, "gold", ft.FontWeight.BOLD),
                    ft.Container(height=6),
                    ui.text(session.info.game_title, 15, "", ft.FontWeight.BOLD),
                    ft.Container(height=6),
                    ui.hint(note),
                ],
                spacing=0,
            )
        self.game_panel.content = inner
        return self.game_panel

    def _set_room_game(self, game_id: str, game_title: str) -> None:
        if self.session is None or not self.session.is_host:
            return
        self.session.set_game(game_id, game_title)
        self.system(f"房主把游戏换成了 {game_title}")
        # 重画选游戏区（让 chip 高亮跟上）与席位区（观战席数量变了）
        self._game_selector_area(self.session)
        self._render_seats()
        self.head_info.value = (f"房主 {self.session.info.host} · "
                                f"{self.session.info.game_title} · "
                                f"{self.session.info.ip}:"
                                f"{self.session.info.port}")
        self.page.update()

    def _voice_area(self, session: RoomSession) -> ft.Control:
        tip_text = ("进房间默认不录音 —— 点「开麦克风」才开始说话，对方的语音会"
                    "自动放出来。" if AUDIO_OK
                    else "这台机器没有语音库，装了 sounddevice + numpy 后才能说话。")
        self._voice_row = ft.Row(
            [
                ui.button("开麦克风", "🎤", self._toggle_mic, height=40),
                ft.Container(width=10),
                ui.button("关扬声器", "🔊", self._toggle_speaker, height=40),
                ft.Container(width=14),
                ft.Column([ui.text("电平", 10, "dim"), self.level], spacing=2),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=True,
        )
        return ui.panel(
            ft.Column(
                [
                    ui.text("语音", 13, "gold", ft.FontWeight.BOLD),
                    ft.Container(height=10),
                    self._voice_row,
                    ft.Container(height=8),
                    ui.hint(tip_text),
                ],
                spacing=0,
            )
        )

    def _chat_area(self, session: RoomSession) -> ft.Control:
        return ui.panel(
            ft.Column(
                [
                    ui.text("聊天", 13, "gold", ft.FontWeight.BOLD),
                    ft.Container(height=8),
                    ui.scroll_box(self.chat_col, height=180),
                    ft.Container(height=8),
                    # 输入行 + 按钮行分开：wrap 的 Row 里放 expand 输入框
                    # 会被撑成一块灰墙（见 _head 的注释）
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.TextField(
                                    ref=self.input_ref, hint_text="说点什么…",
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
                            ui.button("发送", "✉", self._send, height=44),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(height=8),
                    ft.Row(
                        [
                            ui.button("开始" if session.is_host else "等待开始",
                                      "⚔", self._begin,
                                      primary=session.is_host,
                                      enabled=session.is_host, height=44),
                        ],
                    ),
                ],
                spacing=0,
            )
        )

    # ================================================================
    # 动作
    # ================================================================

    def _toggle_mic(self, _e=None) -> None:
        if self.session is None:
            return
        self.mic_on = not self.mic_on
        ok = self.session.set_mic(self.mic_on)
        self.tip.value = ("" if ok
                          else "麦克风没能打开：看看系统有没有给麦克风权限，"
                               "或者设备被别的软件占着？")
        self.tip.color = ui.tone("danger")
        self.system("麦克风已开启" if self.mic_on else "麦克风已关闭")
        self._render_voice_buttons()
        self.page.update()

    def _toggle_speaker(self, _e=None) -> None:
        if self.session is None:
            return
        self.speaker_on = not self.speaker_on
        self.session.set_speaker(self.speaker_on)
        self.system("扬声器已开启" if self.speaker_on else "扬声器已静音")
        self._render_voice_buttons()
        self.page.update()

    def _send(self, _e=None) -> None:
        if self.session is None or self.input_ref.current is None:
            return
        text = (self.input_ref.current.value or "").strip()
        if not text:
            return
        self.input_ref.current.value = ""
        self.session.send_chat(text)
        self._append_chat(self.session.me.nick, text, own=True)
        self.page.update()

    def _begin(self, _e=None) -> None:
        session = self.session
        if session is None or not session.is_host:
            return
        session.begin_game()
        route = GAME_ROOM_ROUTE.get(session.info.game_id)
        if route:
            # 象棋需要每次进对局都重建视图（重新判断本地 / 联网并接管网络回调）
            if route == "/g/chess/play" and Router.current is not None:
                Router.current.invalidate(route)
            self.navigate(route)
        else:
            self.tip.value = f"「{session.info.game_title}」还没接好联机房间，" \
                             f"先把人凑齐就是了。"
            self.tip.color = ui.tone("danger")
            self.page.update()

    def _take_seat(self, seat: int):
        def _handler(_e=None):
            if self.session is not None:
                self.session.take_seat(seat)
        return _handler

    def _on_leave(self, _e=None) -> None:
        """离开房间：广播一声 bye，停掉语音与所有线程。"""
        self.system("离开房间")
        _sess.leave_current()
        self.session = None
        self._polling = False
        self.navigate("/multiplayer")

    # ================================================================
    # 渲染
    # ================================================================

    def _render_seats(self) -> None:
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
                label = f"空位 {i + 1}" + (" · 观战" if spectator else "")
                cells.append(ui.slot(label, on_click=self._take_seat(i)))
                continue
            peer = (member.ip, member.voice_port)
            talking = bool(member.voice_port) and session.voice.is_talking(peer)
            suffix = " · 观战" if spectator else ""
            cells.append(ui.taken_slot(
                member.nick + suffix, host=member.host, talking=talking,
                muted=not member.mic_on))
        # 还没坐下的人（席位满了 / 刚进来）一律算观战
        for member in members:
            if member.seat >= 0:
                continue
            cells.append(ui.taken_slot(member.nick + "（观战）",
                                       host=member.host, muted=True))
        self.seat_row.controls = cells

    def _render_voice_buttons(self) -> None:
        """把麦克风 / 扬声器按钮换成当前状态对应的文案。"""
        if self.session is None or self._voice_row is None:
            return
        self._voice_row.controls = [
            ui.button("关麦克风" if self.mic_on else "开麦克风",
                      "🎤" if self.mic_on else "🔇",
                      self._toggle_mic, height=40),
            ft.Container(width=10),
            ui.button("开扬声器" if not self.speaker_on else "关扬声器",
                      "🔊" if self.speaker_on else "🔈",
                      self._toggle_speaker, height=40),
            ft.Container(width=14),
            ft.Column([ui.text("电平", 10, "dim"), self.level], spacing=2),
        ]

    def system(self, text: str) -> None:
        self._append(None, text)

    def _append_chat(self, nick: str, text: str, own: bool = False) -> None:
        self._append({"nick": nick, "text": text}, None, own)

    def _append(self, item, system_text: Optional[str] = None,
                own: bool = False) -> None:
        if system_text is not None:
            self.chat_lines.append(ui.chat_row("", system_text, system=True))
        elif item is not None:
            self.chat_lines.append(ui.chat_row(item["nick"], item["text"],
                                               own=own))
        if len(self.chat_lines) > MAX_CHAT:
            del self.chat_lines[:len(self.chat_lines) - MAX_CHAT]
        self.chat_col.controls = self.chat_lines

    # ================================================================
    # 轮询：把网络事件搬到界面上
    # ================================================================

    async def _poll(self) -> None:
        while True:
            session = self.session
            # 房间被换掉 / 已经离开，旧协程自动收摊（别拽着上一个房间不放）
            if (session is None or not self._polling
                    or session is not _sess.current()):
                return
            for kind, payload in session.drain():
                if kind == "chat":
                    if not payload.get("own"):   # 自己发的已经本地加过了
                        self._append_chat(payload.get("nick", "?"),
                                          payload.get("text", ""))
                elif kind == "system":
                    self.system(str(payload))
                elif kind == "start":
                    self.system("房主发起了游戏，出发！")
                    route = GAME_ROOM_ROUTE.get(str(payload.get("game", "")))
                    if route and not session.is_host:
                        # 同上：象棋每次重建视图以接管网络回调
                        if route == "/g/chess/play" and Router.current is not None:
                            Router.current.invalidate(route)
                        self.navigate(route)
                        return
                elif kind == "kicked":
                    self.system("房主把你移出了房间")
                    self._polling = False
                    _sess.leave_current()
                    self.navigate("/multiplayer")
                    return
                elif kind == "voice_error":
                    self.tip.value = str(payload)
                    self.tip.color = ui.tone("danger")
            self._render_seats()
            if self.level.content is not None and session.voice.running:
                self.level.content = ui.level_bar(session.voice.level)
            try:
                self.page.update()
            except Exception:                     # noqa: BLE001
                return
            await asyncio.sleep(POLL)


def build(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """路由入口：一间房间一屏，进来时从全局会话里取当前房间。"""
    # 回到房间时，摘掉任何残留的玩法网络回调（避免旧的对局实例继续收消息）
    s = _sess.current()
    if s is not None:
        s.set_game_handler(None)
    return _Lobby(page, navigate).build()
