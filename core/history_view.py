# -*- coding: utf-8 -*-
"""通用「历史记录」查看页（掼蛋 / 象棋 等共用）。

底层落盘逻辑统一在 :mod:`core.history`（写入 ``logs/<game_id>/`` 文本文件）。
本模块只负责把那些文件按时间倒序列出来、点开看全文。各游戏通过参数定制：
``game_id`` / 标题 / 返回路由 / 列表摘要函数，因此不同游戏的历史页共享同一套
界面与交互逻辑。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import flet as ft

from core import history
from core.i18n import t
from core.registry import NavigateFn
from core.theme import T
from core.ui_common import app_bar

LIST_HEIGHT = 230          # 记录列表高度；内部可滚动
MAX_FILES = 200            # 最多列多少条

# 落盘文件头部的键是中文（历史文件已经写成那样了，不跟着语言变）
META_TIME = "生成时间"
META_STATE = "状态"
META_WIN = "胜方"
META_MODE = "模式"
META_SCORE = "分数"
# 「和棋 / 未分胜负」这类结果后面不能再跟「获胜」
META_NO_WIN = ("和棋", "未分胜负")


def _read_file(path: Path) -> List[str]:
    """读日志文件；读不出来就返回一行错误说明（不要让整页崩掉）。"""
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [t("history.read_failed", exc=exc)]


def generic_summary(path: Path, meta: Dict[str, str]) -> str:
    """**通用**摘要：时间 + 状态 + 结果 + 模式 + 分数。

    主菜单的「全部游玩记录」页要把各游戏的记录混在一张表里显示，
    各游戏的落盘头部字段并不完全一样，所以这里只挑几个通用字段
    （状态 / 胜方 / 模式 / 分数）拼一行。
    """
    when = meta.get(META_TIME) or _stamp_from_name(path)
    parts = [when]
    for key in (META_STATE, META_WIN, META_MODE):
        value = meta.get(key, "")
        if value:
            parts.append(value)
    score = meta.get(META_SCORE, "")
    if score:
        parts.append(t("history.score_suffix", score=score))
    return " · ".join(parts)


def _split_meta(lines: List[str]) -> tuple[Dict[str, str], List[str]]:
    """把文件拆成「头部元信息」和「正文」两部分。

    落盘格式是头部若干 ``key: value``，然后一个空行，接着记录正文。
    """
    meta: Dict[str, str] = {}
    body: List[str] = []
    in_body = False
    for line in lines:
        if in_body:
            body.append(line)
            continue
        if not line.strip():
            in_body = True
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
        else:
            body.append(line)          # 老格式：没有头部，整段都当正文
            in_body = True
    return meta, body


def _stamp_from_name(path: Path) -> str:
    """文件名形如 ``<game>-20261018-120000-ab12cd.txt``，取日期时间兜底。"""
    stem = path.stem
    try:
        date, clock = stem.split("-")[1:3]      # 20261018 / 120000
        return (f"{date[:4]}-{date[4:6]}-{date[6:]} "
                f"{clock[:2]}:{clock[2:4]}:{clock[4:]}")
    except (ValueError, IndexError):
        return stem


class HistoryPage:
    """历史记录页（有选中状态，所以用类而不是纯函数）。"""

    def __init__(self, page: ft.Page, navigate: NavigateFn, *,
                 game_id: str, title: str, back_route: str,
                 summary_fn: Callable[[Path, Dict[str, str]], str],
                 list_height: int = LIST_HEIGHT,
                 max_files: int = MAX_FILES,
                 all_games: bool = False,
                 game_label_fn: Optional[Callable[[str], str]] = None,
                 filter_game: str = ""):

        """准备页面状态（记录列表、当前选中项）。"""
        self.page = page
        self.navigate = navigate
        self.game_id = game_id
        self.title = title
        self.back_route = back_route
        self.summary_fn = summary_fn
        self.list_height = list_height
        self.max_files = max_files
        # all_games=True：把**所有游戏**的记录汇到一张表里（主菜单用）
        self.all_games = all_games
        self.game_label_fn = game_label_fn
        self.filter_game = filter_game
        # 列表上方的自定义控件（主菜单页塞「按游戏筛选」的按钮条）
        self.header_controls: List[ft.Control] = []

        # 记录列表：[(game_id, 文件路径)]
        self.records: List[Tuple[str, Path]] = []
        self.index = -1                       # 当前选中的记录

        self.count_text = ft.Text(
            "", size=13, weight=ft.FontWeight.BOLD, color=T.TEXT_PRIMARY)
        self.path_text = ft.Text(
            "", size=10, color=T.TEXT_MUTED, selectable=True)
        self.list_col = ft.Column(
            spacing=6, scroll=ft.ScrollMode.AUTO, height=self.list_height)
        self.detail_text = ft.Text(
            "", size=12, selectable=True, font_family="monospace",
            color=T.TEXT_PRIMARY)

    # ---------------- 界面 ----------------

    def build(self) -> ft.Control:

        """拼出整个历史记录页。"""
        self._reload()

        detail_box = ft.Container(
            bgcolor=T.SURFACE,
            border=ft.Border.all(1, T.BORDER),
            border_radius=8,
            padding=ft.Padding.all(10),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            expand=True,
            content=ft.Column(
                [self.detail_text], spacing=0, expand=True,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

        footer = ft.Row(
            [
                ft.Button(
                    content=ft.Text(t("history.refresh"), size=12),
                    on_click=lambda _e: self._reload(),
                ),
                ft.Button(
                    content=ft.Text(t("history.open_dir"), size=12),
                    on_click=self._on_open_dir,
                ),
            ],
            spacing=10,
            wrap=True,
        )

        body = ft.Column(
            [
                *self.header_controls,
                self.count_text,
                ft.Container(height=2),
                self.path_text,
                ft.Container(height=8),
                ft.Container(
                    bgcolor=T.SURFACE,
                    border=ft.Border.all(1, T.BORDER),
                    border_radius=8,
                    padding=ft.Padding.all(8),
                    content=self.list_col,
                ),
                ft.Container(height=8),
                ft.Text(t("history.section"), size=11, color=T.TEXT_MUTED),
                ft.Container(height=4),
                detail_box,
                ft.Container(height=8),
                footer,
            ],
            spacing=0,
            expand=True,
        )

        return ft.Column(
            [
                app_bar(
                    self.title,
                    on_back=lambda _e: self.navigate(self.back_route),
                    actions=[
                        ft.TextButton(
                            content=ft.Row(
                                [
                                    ft.Icon(ft.Icons.REFRESH, size=16,
                                            color=T.TEXT_PRIMARY),
                                    ft.Text(t("history.refresh"), size=12,
                                            color=T.TEXT_PRIMARY),
                                ],
                                spacing=4, tight=True,
                            ),
                            on_click=lambda _e: self._reload(),
                        ),
                    ],
                ),
                ft.Container(
                    padding=ft.Padding.all(T.PADDING),
                    content=body,
                    expand=True,
                ),
            ],
            expand=True,
        )

    # ---------------- 数据 ----------------

    def _reload(self):
        """重新扫描日志目录并重建列表（不清空已选中的正文）。"""
        self.records = self._collect()
        try:
            self.path_text.value = t("history.log_dir",
                                     path=history.logs_dir(self.game_id))
        except OSError:
            self.path_text.value = t("history.log_dir_na")
        self.count_text.value = (
            t("history.count", n=len(self.records))
            if self.records else t("history.none")
        )
        self._rebuild_list()
        if self.records and self.index < 0:
            self._select(0)                  # 默认展开最近一场
        elif not self.records:
            self.detail_text.value = t("history.empty_body")
        self._update()

    def _collect(self) -> List[Tuple[str, Path]]:
        """收集要显示的记录：``[(game_id, 路径)]``。

        * 单个游戏：只取该游戏目录下的记录；
        * 全部游戏：把所有游戏目录的记录混在一起，并按当前筛选过滤。
        """
        if not self.all_games:
            return [(self.game_id, p)
                    for p in history.recent_logs(self.game_id,
                                                 limit=self.max_files)]
        items = history.recent_logs_all(limit=self.max_files)
        if self.filter_game:
            items = [it for it in items if it[0] == self.filter_game]
        return items

    def set_filter(self, game_id: str) -> None:
        """切换筛选（全部游戏模式下用）：``""`` 表示不筛。"""
        self.filter_game = game_id
        self.index = -1
        self._reload()

    def _rebuild_list(self):

        """重画左边的列表。"""
        self.list_col.controls = [
            self._list_item(i, gid, p)
            for i, (gid, p) in enumerate(self.records)
        ] or [
            ft.Text(t("history.empty_item"), size=12, color=T.TEXT_MUTED)
        ]

    def _list_item(self, i: int, game_id: str, path: Path) -> ft.Control:

        """列表里的一项（文件名 + 时间）。"""
        meta, _body = _split_meta(_read_file(path))
        selected = (i == self.index)
        label = self.summary_fn(path, meta)
        if self.all_games and self.game_label_fn is not None:
            # 全部游戏模式：前面加上游戏名，免得看不出是哪一局
            label = f"[{self.game_label_fn(game_id)}] {label}"
        return ft.Container(
            bgcolor=T.SURFACE_ALT if selected else T.SURFACE,
            border=ft.Border.all(2 if selected else 1,
                                 T.PRIMARY if selected else T.BORDER),
            border_radius=6,
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            ink=True,
            on_click=lambda _e: self._select(i),
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.HISTORY, size=14,
                            color=T.PRIMARY if selected else T.TEXT_MUTED),
                    ft.Container(width=6),
                    ft.Text(label, size=12,
                            color=T.TEXT_PRIMARY, expand=True),
                    ft.Text(path.name, size=9, color=T.TEXT_MUTED),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            ),
        )

    def _select(self, i: int):

        """选中某一条记录并显示详情。"""
        if not (0 <= i < len(self.records)):
            return
        self.index = i
        lines = _read_file(self.records[i][1])
        self.detail_text.value = ("\n".join(lines) if lines
                                  else t("history.empty_file"))
        self._rebuild_list()                 # 刷新选中高亮
        self._update()

    def _on_open_dir(self, _e):
        """尝试用系统文件管理器打开日志目录（失败就只在界面上提示）。"""
        try:
            self.page.launch_url(history.open_data_dir().as_uri())
        except Exception as exc:                  # noqa: BLE001
            self.detail_text.value = t("history.open_failed",
                                       path=history.data_dir(), exc=exc)
            self._update()

    def _update(self):

        """把当前状态刷到界面上。"""
        self.page.update()


def build_history(page: ft.Page, navigate: NavigateFn, *,
                  game_id: str, title: str, back_route: str,
                  summary_fn: Callable[[Path, Dict[str, str]], str],
                  list_height: int = LIST_HEIGHT,
                  max_files: int = MAX_FILES,
                  all_games: bool = False,
                  game_label_fn: Optional[Callable[[str], str]] = None,
                  filter_game: str = "") -> ft.Control:
    """构造一个历史记录页（各游戏传入自己的 game_id / 摘要函数即可）。

    ``all_games=True`` 时列出**所有游戏**的记录（主菜单的「游玩记录」用）。
    """
    return HistoryPage(
        page, navigate, game_id=game_id, title=title,
        back_route=back_route, summary_fn=summary_fn,
        list_height=list_height, max_files=max_files,
        all_games=all_games, game_label_fn=game_label_fn,
        filter_game=filter_game,
    ).build()


def open_history(navigate: NavigateFn, *, history_path: str) -> None:
    """跳到历史记录页。

    路由层会缓存视图，直接 ``navigate`` 会看到上一次的旧列表；这里先
    ``invalidate`` 掉缓存再跳，保证每次进来都是最新的落盘记录。
    """
    from core.router import Router

    if Router.current is not None:
        Router.current.invalidate(history_path)
    navigate(history_path)
