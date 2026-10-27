# -*- coding: utf-8 -*-
"""多人游戏：创建房间 / 搜索房间（局域网 UDP 广播发现）。

房间怎么被别人找到
------------------
创建房间那一刻，本机开始**每隔一秒向整个局域网广播**一句「这里有个房间」：
房间名、玩什么、房主是谁、几个人、以及房间控制端口。同一 WiFi 下的伙伴在
「搜索房间」里会看到它们自动冒出来，不需要任何服务器，也不需要记 IP。

房间码
------
每个房间带一个 6 位房间码（默认随机，也可以自己起）。看到房间只是第一步，
**输对房间码才能进**。上次建房间用的房间码会存在本地，下次再建时自动填上 ——
老朋友下次聚会不用再想新口令，也不用再翻聊天记录。

界面风格
--------
本页所有零件都走 :mod:`core.ui_theme`（默认材料风 / 暗黑2 石砖风 / 社区包），
自己不写死颜色；设置页切换后整页跟着换皮。
"""

from __future__ import annotations

import asyncio
from typing import Dict, List, Optional

import flet as ft

from core import registry
from core import ui_theme as ui
from core.i18n import t
from core.net.discovery import RoomInfo, RoomScanner
from core.net.session import RoomSession, current as session_current, set_current
from core.profile import Profile, normalize_code, random_code
from core.registry import NavigateFn
from core.router import Router

ROUTE = "/multiplayer"
SCAN_POLL = 0.9        # 列表刷新间隔（秒）


def _goto(navigate: NavigateFn, path: str) -> None:
    """跳转前丢掉这条路由的缓存。

    房间页必须每次重建：换一个房间就是另一拨人和另一张席位表，
    拿缓存出来的旧控件会把上一间的痕迹带进来。
    """
    router = Router.current
    if router is not None:
        router.invalidate(path)
    navigate(path)


def build(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """多人联机页：创建房间 / 搜索房间 两个模式。"""
    state: Dict[str, object] = {
        "tab": "create",
        "profile": Profile.load(),
        "scanner": None,
        "rooms": [],
        "busy": False,
    }
    profile: Profile = state["profile"]          # type: ignore[assignment]
    nick = profile.ensure_nick()                 # 没起过名就先随机一个

    # ---------------- 组件 ----------------

    name_ref = ft.Ref[ft.TextField]()
    code_ref = ft.Ref[ft.TextField]()
    nick_ref = ft.Ref[ft.TextField]()
    tip = ui.hint("")
    tab_title = ui.hint(t("mp.tab_create"), "primary")

    # 游戏列表：只列已经能玩的游戏
    games = [it for it in registry.menu_items() if it.available]

    # 表单容器：**不 expand**。放在可滚动的 Column 里还 expand，
    # 它会把剩余高度全吃掉、把下面的按钮顶出屏幕
    # （0.4.7 之前「看不到建立房间按钮」就是这么来的）。
    form_area = ft.Column(spacing=0)

    # ---------- 页面状态 ----------
    def stop_scan() -> None:
        """停止局域网扫描（离开页面时必须调用，否则后台还在扫）。"""
        scanner: Optional[RoomScanner] = state["scanner"]  # type: ignore[assignment]
        if scanner is not None:
            scanner.stop()
            state["scanner"] = None
        state["rooms"] = []

    def render_create(_e=None) -> None:
        """切到「创建房间」界面。"""
        stop_scan()
        state["tab"] = "create"
        tab_title.value = t("mp.tab_create")
        tab_title.color = ui.tone("primary")
        _fill_form_area()

    def render_search(_e=None) -> None:
        """切到「搜索房间」界面。"""
        state["tab"] = "search"
        tab_title.value = t("mp.tab_search")
        tab_title.color = ui.tone("primary")
        _fill_form_area()
        _start_scan()

    # ---------------- 创建房间 ----------------

    # 选游戏 / 选席位用「按钮组」而不是 Dropdown：
    # flet 1.0 的 Dropdown 一旦落在 expand 的 Column 里，选项浮层会被拉成
    # 一块盖住半个屏幕的灰色矩形（用户看到的「没有底的诡异窗口」）。
    game_pick = games[0].id if games else ""

    def _default_seats(gid: str) -> str:
        """按游戏的「上场人数」给一个合理的默认席位（可再加位子扩容观战）。"""
        p = registry.game_players(gid)
        return str(p) if p in (2, 3, 4, 5, 6, 8) else "4"

    seat_pick = _default_seats(game_pick)

    def _set_game(value: str) -> None:
        """选定要玩哪个游戏。"""
        nonlocal game_pick, seat_pick
        game_pick = value
        seat_pick = _default_seats(value)   # 换游戏顺手把席位数调到合适的默认
        _fill_form_area()

    def _set_seats(value: str) -> None:
        """选定房间人数。"""
        nonlocal seat_pick
        seat_pick = value
        _fill_form_area()

    def roll_code(_e=None) -> None:
        """重新生成一个房间码。"""
        if code_ref.current is not None:
            code_ref.current.value = random_code()
            page.update()

    # ---------- 创建房间 ----------
    def do_create(_e=None) -> None:
        """真的建房间：申请端口、登记房间、显示房间码。"""
        if state.get("busy"):
            return                      # 防止网络慢时狂点导致重复开房
        name = (name_ref.current.value if name_ref.current else "").strip()
        code = normalize_code(
            code_ref.current.value if code_ref.current else "")
        if not name:
            tip.value = t("mp.name_required")
            tip.color = ui.tone("danger")
            page.update()
            return
        if len(code) < 4:
            tip.value = t("mp.code_too_short")
            tip.color = ui.tone("danger")
            page.update()
            return
        game_id = game_pick or (games[0].id if games else "")
        game_title = next((g.title for g in games if g.id == game_id),
                          game_id)
        seats = int(seat_pick or 4)

        my_nick = (nick_ref.current.value if nick_ref.current else "").strip() \
            or nick
        if my_nick != nick:
            profile.set_nick(my_nick)

        state["busy"] = True
        session = RoomSession.create(name, game_id, game_title, code,
                                     profile.ensure_nick(), seats=seats)
        state["busy"] = False
        if session is None:
            tip.value = t("mp.create_failed")
            tip.color = ui.tone("danger")
            page.update()
            return
        # 记下这次的名字与房间码，下次自动带上（set_current 会顺手关掉旧房间）
        profile.remember_room(name, code)
        set_current(session)
        state["tab"] = "left"
        stop_scan()
        # 创建成功直接进房间：房间页头部就有房间码/房主/席位，反馈足够，
        # 不必再弹确认框（之前弹框导致点完卡在表单页、狂点才进）。
        _goto(navigate, "/room")

    # ---------------- 搜索房间 ----------------

    # ---------- 搜索与加入 ----------
    def _room_row(info: RoomInfo) -> ft.Control:
        """扫描结果里的一行（房间名 + 码 + 加入按钮）。"""
        full = info.started or info.taken >= info.seats
        return ui.panel(
            ft.Row(
                [
                    ft.Column(
                        [
                            ui.text(info.name or t("mp.unnamed_room"), 14, "",
                                    ft.FontWeight.BOLD),
                            ui.text(t("mp.room_meta", game=info.game_title,
                                      host=info.host, ip=info.ip), 11, "dim"),
                        ],
                        spacing=2, expand=True,
                    ),
                    ui.pill(info.label, tone="danger" if full else "gold"),
                    ft.Container(width=8),
                    ui.button(t("mp.enter"), "🚪",
                              lambda _e, i=info: _ask_code(i),
                              primary=not full, enabled=not full, height=36),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )

    def _ask_code(info: RoomInfo) -> None:
        """弹一个小框要房间码；输对了才发出加入请求。"""
        code_box = ft.TextField(
            value="", hint_text=t("mp.code_placeholder"),
            border=ft.InputBorder.OUTLINE, text_size=14,
            color=ui.colors().text, bgcolor=ui.colors().ink,
            capitalization=ft.TextCapitalization.CHARACTERS,
        )
        err = ui.hint("")

        def confirm(_e=None) -> None:
            """输入的码对不对 → 校验后加入。"""
            code = normalize_code(code_box.value or "")
            if len(code) < 4:
                err.value = t("mp.code_too_short")
                err.color = ui.tone("danger")
                page.update()
                return
            page.pop_dialog()
            _do_join(info, code)

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor=ui.colors().surface,
                title=ui.text(t("mp.code_dialog_title", name=info.name), 15, ""),
                content=ft.Column(
                    [
                        ui.hint(t("mp.code_dialog_hint", host=info.host,
                                  game=info.game_title)),
                        ft.Container(height=8),
                        ft.Container(content=code_box,
                                     border=ft.Border.all(
                                         1, ui.colors().border),
                                     border_radius=8,
                                     padding=ft.Padding.symmetric(
                                         horizontal=8, vertical=2)),
                        err,
                    ],
                    spacing=4, tight=True,
                ),
                actions=[
                    ft.TextButton(content=ui.text(t("common.cancel"), 13,
                                                  "dim"),
                                  on_click=lambda _e: page.pop_dialog()),
                    ft.TextButton(content=ui.text(t("mp.enter"), 13,
                                                  "primary",
                                                  ft.FontWeight.BOLD),
                                  on_click=confirm),
                ],
            )
        )

    def _do_join(info: RoomInfo, code: str) -> None:
        """加入房间：握手、拿席位、进房间页。"""
        tip.value = t("mp.joining", name=info.name)
        tip.color = ui.tone("primary")
        page.update()
        session = RoomSession.join(info, code, profile.ensure_nick())
        if session is None:
            tip.value = t("mp.join_failed")
            tip.color = ui.tone("danger")
            page.update()
            return
        page.run_task(_wait_join, session, info.name)

    async def _wait_join(session: RoomSession, room_name: str) -> None:
        """等房主回话：加入成功才跳进房间页，失败就留在原地提示。"""
        for _ in range(50):                     # 最多等 5 秒
            for kind, payload in session.drain():
                if kind == "joined":
                    state["tab"] = "left"
                    stop_scan()
                    set_current(session)
                    _goto(navigate, "/room")
                    return
                if kind in ("join_failed", "kicked"):
                    session.close()
                    tip.value = t("mp.join_reject", reason=payload)
                    tip.color = ui.tone("danger")
                    page.update()
                    return
            await asyncio.sleep(0.1)
        session.close()
        tip.value = t("mp.no_response")
        tip.color = ui.tone("danger")
        page.update()

    # ---------------- 扫描循环 ----------------

    # ---------- 扫描循环 ----------
    def _start_scan() -> None:
        """开始扫描局域网里的房间。"""
        scanner: Optional[RoomScanner] = state["scanner"]  # type: ignore[assignment]
        if scanner is None:
            scanner = RoomScanner()
            if not scanner.start():
                tip.value = t("mp.scan_busy")
                tip.color = ui.tone("danger")
                page.update()
                return
            state["scanner"] = scanner
        page.run_task(_poll_scan)

    async def _poll_scan() -> None:
        """每 SCAN_POLL 秒把新扫到的房间刷进列表（房间没了也会自动消失）。"""
        scanner: Optional[RoomScanner] = state["scanner"]  # type: ignore[assignment]
        while scanner is not None and state["tab"] == "search":
            rooms = scanner.rooms()
            state["rooms"] = rooms
            _fill_form_area()
            await asyncio.sleep(SCAN_POLL)

    # ---------------- 画面拼装 ----------------

    # ---------- 画面拼装 ----------
    def _create_body() -> List[ft.Control]:
        # 卡名走 .label：游戏插件登记了 title_key 就会跟着语言变
        """创建房间那一半的控件。"""
        game_options = [(g.id, g.label) for g in games] \
            or [("", t("mp.no_games"))]
        return [
            ui.panel(
                ft.Column(
                    [
                        ui.field(t("mp.room_name"), profile.last_room_name
                                 or t("mp.room_name_default", nick=nick),
                                 ref=name_ref),
                        ft.Container(height=12),
                        ft.Row(
                            [
                                ui.field(
                                    t("mp.room_code"),
                                    profile.last_room_code or random_code(),
                                    hint_=t("mp.room_code_hint"),
                                    max_length=8, ref=code_ref),
                                ft.Container(width=10),
                                ft.Container(
                                    content=ui.button(t("mp.random"), None,
                                                      roll_code,
                                                      height=36, width=80),
                                    padding=ft.Padding.only(top=18),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.START,
                        ),
                        ft.Container(height=12),
                        ui.text(t("mp.game"), 11, "dim", spacing=1.0),
                        ft.Container(height=6),
                        ft.Row(
                            [
                                ui.chip(label, active=(value == game_pick),
                                        on_click=(
                                            lambda _e, v=value: _set_game(v)))
                                for value, label in game_options
                            ],
                            spacing=6, wrap=True,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Container(height=6),
                        ui.hint(t("mp.spectator_note")),
                        ft.Container(height=14),
                        ui.text(t("mp.seats"), 11, "dim", spacing=1.0),
                        ft.Container(height=6),
                        ft.Row(
                            [
                                ui.chip(t("mp.seats_n", n=i),
                                        active=(str(i) == seat_pick),
                                        on_click=(
                                            lambda _e, v=str(i): _set_seats(v)))
                                for i in (2, 3, 4, 5, 6, 8)
                            ],
                            spacing=6, wrap=True,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Container(height=12),
                        ui.field(t("mp.your_name"), nick, ref=nick_ref,
                                 hint_=t("mp.your_name_hint")),
                        ft.Container(height=14),
                        ft.Row([ui.button(t("mp.create_btn"), "⚒", do_create,
                                          height=48, width=220)],
                               alignment=ft.MainAxisAlignment.CENTER),
                    ],
                    spacing=0,
                ),
                padding=16,
            ),
            ft.Container(height=12),
            ui.hint(t("mp.create_hint")),
        ]

    def _search_body() -> List[ft.Control]:
        """搜索房间那一半的控件。"""
        rooms: List[RoomInfo] = state["rooms"]       # type: ignore[assignment]
        if not rooms:
            return [
                ui.panel(
                    ft.Column(
                        [
                            ui.text(t("mp.scanning"), 14, ""),
                            ft.Container(height=6),
                            ui.hint(t("mp.scan_hint")),
                        ],
                        spacing=0,
                    ),
                    padding=16,
                )
            ]
        return [_room_row(r) for r in rooms]

    def _fill_form_area() -> None:
        # 只包一层面板：以前 _create_body 自带 panel、这里又包一层，
        # 双层边框 + 外层 expand 把内容顶飞，就是「没有底的诡异窗口」
        """把当前模式的控件填进表单区。"""
        body = _create_body() if state["tab"] == "create" else _search_body()
        form_area.controls = body
        try:
            form_area.update()
        except Exception:                            # noqa: BLE001
            page.update()

    # ---------------- 页面骨架 ----------------

    def on_back(_e=None) -> None:
        """返回主菜单。"""
        state["tab"] = "left"        # 让扫描协程自然收摊，别在后台空转
        stop_scan()
        navigate("/")

    def on_enter_room(_e=None) -> None:
        """已经开过房间的话，从这里直接进。"""
        session = session_current()
        if session is None:
            tip.value = t("mp.no_room_yet")
            tip.color = ui.tone("danger")
            page.update()
            return
        _goto(navigate, "/room")

    tabs = ft.Row(
        [
            ft.Container(content=ui.button(t("mp.tab_create"), "⚒",
                                           render_create, height=40),
                         expand=True),
            ft.Container(width=10),
            ft.Container(content=ui.button(t("mp.tab_search"), "🧭",
                                           render_search, height=40),
                         expand=True),
        ],
    )

    # 竖排放「进入房间」：房间已经开好的话，这一颗随时能进
    enter_row = ft.Container(
        content=ui.button(t("mp.enter_room"), "🚪", on_enter_room, height=44),
        padding=ft.Padding.only(top=6),
    )

    body = ft.Column(
        [
            ui.title(t("mp.title"), 22),
            ft.Container(height=6),
            ui.hint(t("mp.your_nick", nick=nick)),
            ft.Container(height=14),
            tabs,
            ft.Container(height=12),
            tab_title,
            ft.Container(height=8),
            form_area,
            ft.Container(height=12),
            enter_row,
            ft.Container(height=6),
            tip,
        ],
        spacing=0,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    render_create()
    return ui.page(t("mp.title"), body, on_back=on_back)
