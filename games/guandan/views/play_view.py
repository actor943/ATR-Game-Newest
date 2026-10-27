# -*- coding: utf-8 -*-
"""掼蛋对局牌桌：真人 + 电脑混战（0.4.5）。

进入路径：掼蛋子菜单 -> 开始游戏 -> 选好配置 -> 进入本页。

设计要点
--------
* **没有出牌倒计时**。轮到你时手牌区可点牌，点「出牌」/「过牌」；
  不点就一直等着，不催你。电脑位由 :mod:`asyncio` 协程自动出牌，
  ``AI_DELAY`` 只是为了让牌面看得清，不是倒计时。
* 座位配置来自 :class:`games.guandan.config.MatchConfig`（单人 / 三人机 /
  自定义），决定哪个座位由你亲手操作。
* 本机只有一个玩家：非本机的真人位按「托管」处理，由电脑代打。
* 近期事件沿用全模拟的终端写法（单个 ``ft.Text`` + spans，固定高度可滚动），
  Mac 上可整段复制。

联机对局（0.4.8-fix：开始游戏后所有人必须是**同一副牌**）
--------------------------------------------------------
从房间「开始」进来的对局，**房主是唯一权威**：只有房主洗牌发牌，之后每有一个
动作（出牌 / 过牌 / 进贡 / 发下一手）房主就把整场局面连同新的事件日志重推一次
快照；所有人按 ``seq`` 只采用更新的快照，乱序 / 重传的旧包直接丢弃。客人不本地
洗牌、不本地跑 AI、不本地写日志 —— 全部等房主快照，从根上杜绝「各玩各的」。
房间 0~3 号座对应牌桌甲~丁，空位由电脑补；4 号位起的人只围观（看不到任何手牌）。

模块划分
--------
原文件 1680 多行，现在按职责拆开（``_Play`` 用 mixin 组合起来）：

============================== ========================================== ==========
模块                         负责什么                                  行数量级
============================== ========================================== ==========
``play_const.py``            配色 / 尺寸 / 时间参数 / 纯工具函数      约 170
``play_table.py``            画面：顶栏 / 席位 / 待压 / 手牌 / 结算   约 250
``play_actions.py``          真人操作：选牌 / 出牌 / 过牌 / 进贡      约 300
``play_ai.py``               电脑代打的协程驱动                       约 90
``play_net.py``              联机同步：房主权威 + 整局快照            约 320
``play_flow.py``             流转：结算 / 落盘 / 离开确认            约 180
``play_view.py``（本文件）    组装：状态、界面骨架、生命周期          约 250
============================== ========================================== ==========

暂未实现：炸弹特效、悔牌。
"""

from __future__ import annotations

from collections import deque
from dataclasses import replace
from typing import Deque, Dict, List, Optional, Set, Tuple

import flet as ft

from core.registry import NavigateFn
from core.theme import T
from core.ui_common import app_bar
from core.profile import ensure_nick
from core.net import session as _sess
from games.guandan import config as cfgmod
from games.guandan.cards import Card
from games.guandan.engine import Hand, MatchState, new_match
from games.guandan.views.play_actions import PlayActionsMixin
from games.guandan.views.play_ai import PlayAiMixin
from games.guandan.views.play_const import (
    EVENTS_HEIGHT,
    HAND_BOX_HEIGHT,
    HAND_ROW_GAP,
    HEAD_COLOR,
    MAX_EVENTS,
    MUTED,
)
from games.guandan.views.play_flow import PlayFlowMixin
from games.guandan.views.play_net import PlayNetMixin
from games.guandan.views.play_table import PlayTableMixin

class _Play(PlayNetMixin, PlayAiMixin, PlayActionsMixin,
            PlayTableMixin, PlayFlowMixin):
    """一局牌桌的全部状态与界面引用。"""

    def __init__(self, page: ft.Page, navigate: NavigateFn):
        self.page = page
        self.navigate = navigate
        self.cfg: cfgmod.MatchConfig = cfgmod.active()

        # ---- 联机房间开起来的对局 ----
        # 权威在房主：只有房主洗牌发牌，之后每有个动作房主重推一次整局快照，
        # 所有人按 seq 采用最新快照 —— 开始游戏后大家必然是**同一副牌**
        # （0.4.8-fix：此前各客户端各自 new_match() 随机发牌，各玩各的）。
        self.net = _sess.current()
        self.is_host = bool(self.net and self.net.is_host)
        self.my_seat = 0                   # 本机玩家坐在哪（甲=0 … 丁=3）
        self.spectator = False             # 房间 4 号位起 / 没入座 = 旁观
        self.remote_nicks: Dict[int, str] = {}   # 牌桌座位 -> 远端真人昵称
        self._seq = 0                      # 房主：已推快照的序号
        self._last_seq = -1                # 已应用的最新快照序号（防乱序 / 重传）
        self._synced = self.net is None or self.is_host
        self._result_hand_no = -1          # 结算面板对应的是第几手
        if self.net is not None:
            self._setup_net_seats()
        # 联机房间开起来的对局：本机玩家用昵称，而不是「你」
        if self.net is not None:
            self.cfg = replace(self.cfg, local_nick=ensure_nick())

        self.match: MatchState = new_match()
        self.hand: Hand = Hand(self.match)
        self.selected: Set[Card] = set()
        self.tribute_sel: Set[Card] = set()      # 进贡阶段选中的牌
        self.gift_marks: Set[Card] = set()       # 本轮进贡**得来**的牌（手牌里标出来）
        self.result = None                  # 上一手结算结果
        self.alive = True

        self._events: Deque[ft.TextSpan] = deque(maxlen=MAX_EVENTS)
        self._log_lines: Deque[str] = deque(maxlen=MAX_EVENTS)  # 纯文本，供落盘
        # 每条日志的 (颜色, 加粗) —— 联机快照要把着色一起广播，客人才不会
        # 看到一串白字（0.4.8-fix：事件记录也是「要同步的内容」）
        self._log_meta: Deque[Tuple[str, bool]] = deque(maxlen=MAX_EVENTS)
        self._log_sent = 0                  # 房主：已随快照发出去的日志条数
        self._log_have = 0                  # 客人：已收到的日志条数（对齐用）
        self._log_saved = False        # 这一场是否已经落盘（防止重复写文件）
        self._ai_task = None

        # ---- 界面引用 ----
        self.score_text = ft.Text("", size=13, weight=ft.FontWeight.BOLD,
                                  color=T.TEXT_PRIMARY)
        self.level_note = ft.Text("", size=11, color=MUTED)
        self.net_text = ft.Text("", size=11, color=MUTED)
        self.turn_text = ft.Text("", size=12)
        self.seat_row = ft.Row(spacing=8, wrap=True)
        self.target_box = ft.Container()
        self.hand_box: Optional[ft.Container] = None   # 手牌盒：高度随行数变化
        self.my_hand_col = ft.Column(
            spacing=HAND_ROW_GAP, scroll=ft.ScrollMode.AUTO,
            auto_scroll=False, expand=True)
        self.play_btn: ft.Button = ft.Button(
            content=ft.Text("出牌"), height=40, width=110,
            bgcolor=T.PRIMARY, color=T.TEXT_INVERT, on_click=self._on_play)
        self.pass_btn: ft.Button = ft.Button(
            content=ft.Text("过牌"), height=40, width=110,
            bgcolor=T.SURFACE_ALT, color=T.TEXT_PRIMARY,
            on_click=self._on_pass)
        self.clear_btn: ft.Button = ft.Button(
            content=ft.Text("清空选择"), height=40,
            bgcolor=T.SURFACE_ALT, color=T.TEXT_SECONDARY,
            on_click=self._on_clear)
        self.hint_text = ft.Text("", size=12, color=T.TEXT_MUTED)
        self.result_box = ft.Container()
        self.events_text = ft.Text(
            value="", spans=[], selectable=True, font_family="monospace",
            size=12, no_wrap=False, opacity=1.0,
            animate_opacity=0, animate_size=0,
        )
        self.events_inner = ft.Column(
            controls=[self.events_text], scroll=ft.ScrollMode.AUTO,
            auto_scroll=True, expand=True, spacing=0,
            animate_opacity=0, animate_size=0,
        )

    # ============================================================
    # 界面组装
    # ============================================================

    def build(self) -> ft.Control:
        events_box = ft.Container(
            content=self.events_inner,
            height=EVENTS_HEIGHT,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            opacity=1.0, animate_opacity=0, animate_size=0,
        )
        events_section = ft.Container(
            bgcolor=T.SURFACE,
            border=ft.Border.all(1, T.BORDER),
            border_radius=8,
            padding=ft.Padding.all(10),
            content=ft.Column(
                [ft.Text("── 近期事件 ──", size=11, color=MUTED),
                 ft.Container(height=4),
                 events_box],
                spacing=0,
            ),
        )

        top_bar = ft.Container(
            bgcolor=T.SURFACE,
            border=ft.Border.all(1, T.BORDER),
            border_radius=8,
            padding=ft.Padding.all(12),
            content=ft.Row(
                [
                    ft.Column(
                        [self.score_text, self.level_note, self.net_text],
                        spacing=2, expand=True,
                    ),
                    self.turn_text,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        table_box = ft.Container(
            bgcolor=T.SURFACE,
            border=ft.Border.all(1, T.BORDER),
            border_radius=8,
            padding=ft.Padding.all(10),
            content=ft.Column(
                [self.seat_row, ft.Container(height=8), self.target_box],
                spacing=0,
            ),
        )

        self.hand_box = ft.Container(
            bgcolor=T.SURFACE,
            border=ft.Border.all(1, T.BORDER),
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            height=HAND_BOX_HEIGHT,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=self.my_hand_col,
        )

        actions = ft.Row(
            [self.play_btn, self.pass_btn, self.clear_btn,
             ft.Container(expand=True), self.hint_text],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        body = ft.Column(
            [
                top_bar,
                ft.Container(height=8),
                table_box,
                ft.Container(height=8),
                self.result_box,
                self.hand_box,
                ft.Container(height=8),
                actions,
                ft.Container(height=8),
                events_section,
            ],
            spacing=0,
            # 手机上竖直空间不够（手牌可能换成多行），整页可滚，保证都能看到
            scroll=ft.ScrollMode.AUTO,
        )

        view = ft.Column(
            [
                app_bar(
                    "对局",
                    on_back=self._on_back,
                    actions=[
                        ft.TextButton(
                            content=ft.Row(
                                [
                                    ft.Icon(ft.Icons.HISTORY, size=16,
                                            color=T.TEXT_PRIMARY),
                                    ft.Text("历史记录", size=12,
                                            color=T.TEXT_PRIMARY),
                                ],
                                spacing=4, tight=True,
                            ),
                            on_click=self._on_history,
                            tooltip="查看往期出牌记录",
                        ),
                    ],
                ),
                ft.Container(
                    padding=ft.Padding.all(12),
                    content=body,
                    expand=True,
                ),
            ],
            expand=True,
        )
        self._log(f"对局开始：{self._seat_summary()}", HEAD_COLOR, bold=True)
        if self.net is not None:
            # 联机：接管会话的玩法消息；房主当即推牌，客人向房主要牌。
            # 整段兜底：网络/序列化任何一环出错都只影响联机，不能把牌桌页
            # 带崩（手机上未捕获异常 = "Error running app" 红屏）。
            global _CURRENT_PLAY
            _CURRENT_PLAY = self
            try:
                self.net.set_game_handler(self._on_net)
                if self.is_host:
                    self._push_state()
                    self._start_ai()
                else:
                    self.net.send_game_to_host({"k": "req_state"})
                    self.page.run_task(self._sync_wait)  # 传方法，别带括号！
                self.page.run_task(self._net_poll)
            except Exception as exc:
                print(f"[guandan] 联机初始化失败，按等待状态继续：{exc!r}")
                self._synced = False
        self._refresh()
        if self.net is None:
            self._start_ai()
        return view

    # ============================================================
    # 刷新
    # ============================================================

    def _refresh(self):
        if not self._synced:
            self._render_waiting()
            return
        self._render_top()
        self._render_seats()
        self._render_target()
        self._render_my_hand()
        self._render_result()
        self._render_buttons()
        self.page.update()

    def _render_waiting(self):
        """客人还没拿到房主的快照：只显示「等待发牌」，不渲染本地那副随机牌。"""
        self.turn_text.value = "等待房主发牌…"
        self.turn_text.color = MUTED
        self.net_text.value = "正在与房主同步局面…"
        self.net_text.color = MUTED
        self.seat_row.controls = [
            ft.Text("等待房主发牌…", size=12, color=MUTED)]
        self.target_box.content = ft.Container()
        self.my_hand_col.controls = [
            ft.Text("正在与房主同步局面…", size=13, color=MUTED)]
        if self.hand_box is not None:
            self.hand_box.height = HAND_BOX_HEIGHT
        self.result_box.visible = False
        self.play_btn.disabled = True
        self.pass_btn.disabled = True
        self.clear_btn.disabled = True
        self.page.update()


    # ============================================================
    # 生命周期辅助
    # ============================================================

    def _is_current_play(self) -> bool:
        """我是不是「当前正在显示」的那一张牌桌。

        路由器会缓存视图，旧实例可能还活着；只有当前显示的那一张才应该
        响应网络消息，否则两张牌桌会同时动。
        """
        return self is _CURRENT_PLAY

    def _clear_current_play(self) -> None:
        """离开牌桌时把「当前牌桌」指针清掉（旧实例别再收玩法消息）。"""
        global _CURRENT_PLAY
        if _CURRENT_PLAY is self:
            _CURRENT_PLAY = None

# 保留最近几张牌桌（换场时用来收尾：停协程、存记录）
_ACTIVE: List[_Play] = []
# 同一时刻只有「当前正在显示」的牌桌响应网络消息（防路由器缓存里的旧实例）
_CURRENT_PLAY: "Optional[_Play]" = None


def build(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """建一张新牌桌；上一场还没收尾就先存盘并停掉它的协程。"""
    for old in _ACTIVE:
        old.dispose()
    _ACTIVE.clear()
    view = _Play(page, navigate)
    _ACTIVE.append(view)
    return view.build()
