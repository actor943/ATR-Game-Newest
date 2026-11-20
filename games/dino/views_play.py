# -*- coding: utf-8 -*-
"""对局页：小恐龙跑酷画面 + 键盘/触屏输入 + 主循环（自动加速）。

手机端怎么玩
------------
手机上没有键盘，所以这一页同时提供两套操作，走同一个 ``_act()``：

* **键盘（桌面）**：空格 / ↑ / W 跳跃；↓ / S 下蹲（按住）；P 暂停；R 重开；
* **触屏（手机）**：屏幕点击 / 下方「跳」键起跳；按住「蹲」键下蹲；
  直接在画面上**下滑**也能下蹲。

画面用的是 ``assets/Dino_assets/`` 里 19 张原生 Chrome 恐龙 PNG（见
``games/dino/assets.py``）：恐龙 7 帧、仙人掌 6 种、飞鸟 2 帧，外加云、
地面、GAME OVER 和重置键。全部用 ``ft.Image`` 定位在 Stack 上，坐标由引擎
的世界坐标乘 ``self.scale`` 得到；碰撞框与贴图同宽高，所以「看到的」就是
「撞到的」。白天是原版米白底 + 深灰精灵，跑过里程碑会切换成浅色精灵的夜景
（``color_blend_mode=SRC_IN`` 给贴图换色，不改素材文件）。

``Cloud.png`` / ``Reset.png`` 的 PNG 底部有大块透明留白，直接压进小框会把
图案挤扁，所以这两种要走 ``_clipped_pair()`` 的裁剪容器，只露出顶部内容。

素材万一没打进安装包也不会白屏：每张图都带 ``error_content`` 纯色兜底。

为避免内存泄漏，离开页面时必须 ``_detach()``：取消 asyncio 任务、还原
``page.on_keyboard_event`` 与 ``page.on_resize``、停掉触屏按键的连发任务。
"""

from __future__ import annotations

import asyncio
from typing import Dict, Optional, Tuple

import flet as ft

from core import responsive
from core.i18n import t
from core.registry import NavigateFn
from core.theme import T

from . import assets
from .engine import (
    DINO_DUCK_H, DINO_STAND_H, DINO_W, DINO_X, GROUND_TOP,
    TRACK_H, TRACK_TILE_W, WORLD_H, WORLD_W, Dino,
)
from .views_layout import LayoutMixin
from .views_pad import TouchPad

# Chrome 恐龙原版配色：白天米白底 + #535353 精灵，夜里反过来
DAY_BG = "#f7f7f7"
NIGHT_BG = "#111318"
DAY_OVERLAY = "#f7f7f7"
NIGHT_OVERLAY = "#111318"
CLOUD_NIGHT = "#7f8794"
CLOUD_DAY = "#aeb3ba"   # 原生云是 #dadada，米白底上几乎看不见，白天略压深

# 恐龙贴图宽高比（站立 / 下蹲两套），用来把不同帧摆进同一个视觉框，
# 避免 DinoStart(97×101) 和 DinoRun1(87×94) 切帧时宽度跳一下。
_DINO_RATIO = assets.sprite("dino_run1").w / assets.sprite("dino_run1").h
_DUCK_RATIO = assets.sprite("dino_duck1").w / assets.sprite("dino_duck1").h
# GameOver.png 最右侧 383~385 列有一条 24px 高的杂散竖线（素材自带），
# 裁掉最后 4 列即可，字母 R 在 379 列就结束了。
GAME_OVER_TRIM = 382.0 / 386.0

INTERVAL = 0.03        # 主循环步进间隔（秒），与引擎 TICK_SECONDS 对齐


def _make_image(key: str, w: float, h: float) -> ft.Image:
    """造一张像素画贴图：硬边缩放 + 切帧不闪 + 素材缺失时纯色兜底。"""
    return ft.Image(
        src=assets.src(key), width=w, height=h,
        fit=ft.BoxFit.FILL,
        filter_quality=ft.FilterQuality.NONE,
        gapless_playback=True,
        error_content=ft.Container(bgcolor=assets.INK),
    )


def _make_clipped(key: str) -> Tuple[ft.Stack, ft.Image]:
    """底部有透明留白的贴图（云 / 重置键）：外层 Stack 只裁出顶部内容。

    用 ``ft.Stack`` 而不是 ``ft.Container``：Flutter 的 Container 只有带
    decoration 时才创建 ClipPath，实测 ``clip_behavior`` 在这种纯布局用法下
    不生效；Stack 的 HARD_EDGE 是确定会裁掉子控件溢出部分的。
    """
    inner = _make_image(key, 1.0, 1.0)
    inner.left = 0
    inner.top = 0
    box = ft.Stack(width=1.0, height=1.0,
                   clip_behavior=ft.ClipBehavior.HARD_EDGE,
                   controls=[inner])
    return box, inner


def _size_clipped(pair: Tuple[ft.Control, ft.Image], key: str, w: float) -> None:
    """按宽度重算裁剪容器：外层只露内容，内层保持整张 PNG 的原始比例。"""
    sp = assets.sprite(key)
    box, img = pair
    box.width = w
    box.height = w / sp.ratio
    img.width = w
    img.height = w * sp.h / sp.w


def _tint(img: ft.Image, night: bool, cloud: bool = False) -> None:
    """夜景把深灰精灵换成浅色（SRC_IN 只给非透明像素上色）；白天用原生色。

    云是唯一例外：白天也要压深一点，否则 #dadada 在米白底上几乎看不见。
    """
    if cloud:
        img.color = CLOUD_NIGHT if night else CLOUD_DAY
        img.color_blend_mode = ft.BlendMode.SRC_IN
    else:
        img.color = assets.INK_LIGHT if night else None
        img.color_blend_mode = ft.BlendMode.SRC_IN if night else None


class _PlayPage(LayoutMixin):
    """一页对局：持有引擎、控件、循环任务。"""

    def __init__(self, page: ft.Page, navigate: NavigateFn):
        self.page = page
        self.navigate = navigate
        self._best = 0
        self.engine = Dino()
        self._task: Optional[asyncio.Task] = None
        self._prev_keyboard = None
        self._prev_resize = None
        self._log_saved = False
        self.scale = 6.0
        self._touch = False
        self._obstacle_ctrls: Dict[int, ft.Image] = {}
        self._cloud_ctrls: Dict[int, Tuple[ft.Control, ft.Image]] = {}
        self._night = False
        self._drag_from: Optional[float] = None
        self._tap_handled = False        # 同一次点击 on_tap_up / on_tap 只跳一次

        # —— 舞台（画布）——
        # 两块地面贴图首尾相接，按 track_offset 平移，做出无限滚动的地面。
        self.track_a = _make_image("track", 1.0, 1.0)
        self.track_b = _make_image("track", 1.0, 1.0)
        self.dino_img = _make_image("dino_start", 1.0, 1.0)

        self.overlay_text = ft.Text("", size=18, weight=ft.FontWeight.BOLD,
                                   color=assets.INK,
                                   text_align=ft.TextAlign.CENTER)
        self.game_over_img = _make_image("game_over", 1.0, 1.0)
        self.game_over_img.left = 0
        self.game_over_img.top = 0
        self.game_over_box = ft.Stack(
            width=1.0, height=1.0,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            controls=[self.game_over_img],
        )
        self.over_score = ft.Text("", size=13, color=assets.INK,
                                  text_align=ft.TextAlign.CENTER)
        self.reset_box, self.reset_img = _make_clipped("reset")
        # 重置键素材是「深灰底 + 浅色箭头」。夜里若也用 SRC_IN 上色，
        # 底和箭头会一起变白、箭头消失；所以外套一块浅色底片，贴图保持
        # 原色（深浅对比靠底片提供），昼夜都能看清按钮。
        self.reset_chip = ft.Container(
            bgcolor=assets.INK_LIGHT, border_radius=8,
            padding=ft.Padding.all(4), content=self.reset_box,
        )
        self.game_over_panel = ft.Column(
            [self.game_over_box, ft.Container(height=8),
             self.over_score, ft.Container(height=10), self.reset_chip],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            visible=False,
        )
        self.overlay = ft.Container(
            bgcolor=ft.Colors.with_opacity(0.82, DAY_OVERLAY),
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                [self.overlay_text, self.game_over_panel],
                spacing=0,
                # Column 默认 mainAxisSize.max 会撑满浮层高度，不设 CENTER
                # 的话提示文字 / GAME OVER 会贴在舞台最顶上而不是居中。
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            visible=False,
        )
        self.stack = ft.Stack(
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            controls=[self.track_a, self.track_b, self.dino_img, self.overlay],
        )
        self.stage = ft.Container(
            bgcolor=DAY_BG,
            border=ft.Border.all(2, T.BORDER),
            border_radius=6,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=self.stack,
        )

        # —— 信息文字 ——
        self.score_text = ft.Text("0", size=18, weight=ft.FontWeight.BOLD,
                                 color=T.TEXT_PRIMARY)
        self.best_text = ft.Text("0", size=14, color=T.TEXT_SECONDARY)
        self.speed_text = ft.Text("1.0", size=14, color=T.ACCENT,
                                 weight=ft.FontWeight.BOLD)
        self.status_text = ft.Text("", size=12, color=T.DANGER)
        self.pause_label = ft.Text(t("dino.pause", default="暂停"),
                                  size=13, color=T.TEXT_PRIMARY)
        _pause_box = ft.Container(
            bgcolor=T.SURFACE_ALT, border=ft.Border.all(1, T.BORDER),
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            alignment=ft.Alignment.CENTER,
            content=ft.Row(
                [ft.Icon(ft.Icons.PAUSE, size=16, color=T.TEXT_PRIMARY),
                 self.pause_label],
                spacing=4, tight=True,
            ),
        )
        # 用 GestureDetector 而非 ft.Button：不可获得键盘焦点，方向键不会在
        # 按钮间跳、也不会误触按钮（只保留鼠标 / 触控与键盘 on_keyboard_event）
        self.pause_btn = ft.GestureDetector(
            content=_pause_box, on_tap=lambda _e: self._toggle_pause())
        self.pad = TouchPad(page, self._act)

    # ---------- 布局（在 views_layout 中调用） ----------

    def _apply_stage_size(self) -> None:
        s = self.scale
        sw = WORLD_W * s
        sh = WORLD_H * s
        self.stage.width = sw
        self.stage.height = sh
        self.stack.width = sw
        self.stack.height = sh
        tile_w = TRACK_TILE_W * s
        for tile in (self.track_a, self.track_b):
            tile.width = tile_w
            tile.height = TRACK_H * s
            tile.top = GROUND_TOP * s
        self.overlay.width = sw
        self.overlay.height = sh
        # 结束层按舞台宽度限幅，窄屏也不会顶出边界
        gw = min(38.0 * s, sw * 0.72)
        self.game_over_img.width = gw
        self.game_over_img.height = gw * (40.0 / 386.0)
        self.game_over_box.width = gw * GAME_OVER_TRIM
        self.game_over_box.height = gw * (40.0 / 386.0)
        _size_clipped((self.reset_box, self.reset_img), "reset",
                      min(5.0 * s, sw * 0.12))

    # ---------- 画面 ----------

    def _render(self) -> None:
        s = self.scale
        e = self.engine
        night = bool(e.night)
        ink = assets.INK_LIGHT if night else assets.INK

        # 昼夜：只改舞台底色 / 贴图着色，不动素材文件
        if night != self._night:
            self._night = night
            self.stage.bgcolor = NIGHT_BG if night else DAY_BG
        # 待开始 / 暂停时只薄薄盖一层，别把恐龙和地面全糊掉；
        # GAME OVER 时压深一点让字和重置键看得清。
        over = not e.alive
        self.overlay.bgcolor = ft.Colors.with_opacity(
            0.72 if over else 0.45,
            NIGHT_OVERLAY if night else DAY_OVERLAY)
        for tile in (self.track_a, self.track_b):
            _tint(tile, night)
        _tint(self.game_over_img, night)   # 重置键保持原色，靠浅色底片衬出来

        # 地面：两块贴图首尾相接，取模偏移保证无限无缝滚动
        tile_w = TRACK_TILE_W * s
        off = (e.track_offset * s) % tile_w
        self.track_a.left = -off
        self.track_b.left = tile_w - off

        # 云（按对象 id 复用裁剪容器）
        live_clouds = set()
        children = []
        for c in e.clouds:
            cid = id(c)
            live_clouds.add(cid)
            pair = self._cloud_ctrls.get(cid)
            if pair is None:
                pair = _make_clipped("cloud")
                self._cloud_ctrls[cid] = pair
            box, img = pair
            _size_clipped(pair, "cloud", c.w * s)
            _tint(img, night, cloud=True)
            box.left = c.x * s
            box.top = c.y * s
            children.append(box)
        for cid in list(self._cloud_ctrls):
            if cid not in live_clouds:
                del self._cloud_ctrls[cid]
        children.extend((self.track_a, self.track_b))

        # 障碍：贴图与碰撞框同宽高，variant 决定用哪张仙人掌
        live_ids = set()
        for o in e.obstacles:
            oid = id(o)
            live_ids.add(oid)
            ctrl = self._obstacle_ctrls.get(oid)
            if ctrl is None:
                ctrl = _make_image(o.variant if o.kind == "cactus" else "bird1",
                                   1.0, 1.0)
                self._obstacle_ctrls[oid] = ctrl
            wanted = (assets.cactus_src(o.variant) if o.kind == "cactus"
                      else assets.bird_src((e.tick // 8) % 2))
            if ctrl.src != wanted:
                ctrl.src = wanted
            _tint(ctrl, night)
            ctrl.left = o.x * s
            ctrl.top = o.y * s
            ctrl.width = o.w * s
            ctrl.height = o.h * s
            children.append(ctrl)
        for oid in list(self._obstacle_ctrls):
            if oid not in live_ids:
                del self._obstacle_ctrls[oid]

        # 恐龙：底边对齐碰撞框底边、左右居中；帧由 tick 驱动
        if not e.started:
            state = "start"
        elif not e.alive:
            state = "dead"
        elif not e.on_ground:
            state = "jump"
        elif e.ducking:
            state = "duck"
        else:
            state = "run"
        wanted = assets.dino_src(state, (e.tick // 6) % 2)
        if self.dino_img.src != wanted:
            self.dino_img.src = wanted
        _tint(self.dino_img, night)
        dh = DINO_DUCK_H if e.ducking else DINO_STAND_H
        vh = dh * s
        vw = vh * (_DUCK_RATIO if e.ducking else _DINO_RATIO)
        self.dino_img.width = vw
        self.dino_img.height = vh
        self.dino_img.left = DINO_X * s + (DINO_W * s - vw) / 2
        self.dino_img.top = (e.dino_top + dh) * s - vh
        children.append(self.dino_img)
        children.append(self.overlay)
        self.stack.controls = children

        # 信息（原版是 5 位补零分数）
        self.score_text.value = str(int(e.score)).zfill(5)
        self.best_text.value = str(max(self._best, int(e.score))).zfill(5)
        self.speed_text.value = f"{e.speed:.1f}"
        self.game_over_panel.visible = over
        self.overlay_text.visible = not over
        self.overlay_text.color = ink
        self.over_score.color = ink
        if over:
            self.over_score.value = (
                f"{int(e.score)}  ·  "
                f"{t('dino.restart_hint', default='点击 / R 重开')}")
        if not e.started:
            self.status_text.value = ""
            self.overlay.visible = True
            self.overlay_text.value = t("dino.start_hint",
                                       default="空格 / 点击 开始")
        elif over:
            self.status_text.value = t("dino.over", default="游戏结束")
            self.status_text.color = T.DANGER
            self.overlay.visible = True
        elif e.paused:
            self.status_text.value = t("dino.paused", default="已暂停")
            self.status_text.color = T.WARNING
            self.overlay.visible = True
            self.overlay_text.value = t("dino.paused", default="已暂停")
        else:
            self.status_text.value = ""
            self.overlay.visible = False
        self.pause_label.value = (t("dino.resume", default="继续")
                                  if e.paused else t("dino.pause", default="暂停"))

    def _refresh(self) -> None:
        self._render()
        self.page.update()

    # ---------- 输入 ----------

    _KEY_ALIAS = {
        "space": "jump",
        "arrowup": "jump", "up": "jump", "w": "jump",
        "arrowdown": "duck", "down": "duck", "s": "duck",
        "p": "pause",
        "r": "restart",
    }

    def _act(self, action: str) -> None:
        e = self.engine
        if action == "jump":
            if not e.alive:
                self._restart()
                return
            e.jump()
        elif action == "duck":
            e.request_duck(0.5)
        elif action == "duck_release":
            e.release_duck()
        elif action == "pause":
            e.toggle_pause()
        elif action == "restart":
            self._restart()
            return
        else:
            return
        self._refresh()

    def _on_key(self, e: ft.KeyboardEvent):
        # flet 把空格上报为 " "（单个空格），strip 后会变成空串，这里单独归一
        # 成 "space"，否则按空格根本无法开始游戏（启动提示里写的就是「空格」）。
        raw = (e.key or "").strip().lower()
        if raw == "" or raw == "spacebar":
            raw = "space"
        action = self._KEY_ALIAS.get(raw)
        if action:
            self._act(action)

    # ---------- 画面上手势（手机：下滑下蹲 / 点击跳跃） ----------

    @staticmethod
    def _tap_y(e) -> Optional[float]:
        """取 TapEvent 的局部 y 坐标。

        flet 的 :class:`TapEvent` 只有 ``local_position``（``Offset``，含 x/y），
        **没有** ``local_y`` 字段。早先按 ``local_y`` 读取恒为 None，导致点击
        手势被整段吞掉（空格能玩、鼠标点击没反应）。这里兼容两种写法。
        """
        pos = getattr(e, "local_position", None)
        if pos is not None:
            y = getattr(pos, "y", None)
            if y is not None:
                return float(y)
        y = getattr(e, "local_y", None)
        return float(y) if y is not None else None

    def _swipe_start(self, e):
        self._drag_from = self._tap_y(e)
        self._tap_handled = False

    def _swipe_end(self, e):
        start = self._drag_from
        self._drag_from = None
        y = self._tap_y(e)
        # 坐标拿不到时也不能吞掉点击：直接按「轻点」处理。
        if start is not None and y is not None and y - start > 18:
            self._act("duck")
        else:
            self._act("jump")
        self._tap_handled = True

    def _on_stage_tap(self, e):
        """点击兜底：万一 on_tap_up 因手势竞争没触发，仍要能跳。

        Flutter 的顺序是 tapDown → tapUp → onTap；_tap_handled 保证同一次
        点击只跳一次，同时下滑（tap 被取消）不会被误判成跳跃盖掉下蹲。
        """
        if self._tap_handled:
            self._tap_handled = False
            return
        self._act("jump")

    def _swipe_cancel(self, e):
        # 滑动被识别成拖拽时 tap 会取消：只清状态，不动作（下蹲另有触屏键）。
        self._drag_from = None

    # ---------- 主循环 ----------

    async def _loop(self):
        """每帧都重读 self.engine，所以重开换了新引擎后循环能立刻接着跑。

        关键：死亡时**不能 return**。早先在结束态直接退出任务，重开虽然换了
        新引擎却再也没人调用 step()，画面就一直静止（「重开什么也没发生」）。
        现在结束态只空转等待重开，日志靠 _log_saved 保证只落一次。
        """
        try:
            while True:
                await asyncio.sleep(INTERVAL)
                e = self.engine
                if not e.alive:
                    if not self._log_saved:
                        self._refresh()
                        self._save_match_log()
                    continue
                if not e.started or e.paused:
                    # 待开始 / 暂停：由输入事件的 _refresh 驱动刷新，不空转 update
                    continue
                e.step(1.0)
                self._render()
                if not e.alive:
                    self._refresh()
                    self._save_match_log()
                    continue
                self.page.update()
        except asyncio.CancelledError:
            raise
        except Exception:                   # noqa: BLE001 — 页面没了就收工
            return

    # ---------- 生命周期 ----------

    def _attach(self):
        self._prev_keyboard = self.page.on_keyboard_event
        self.page.on_keyboard_event = self._on_key
        # 走全局 resize 分发器，不覆盖框架 / 其它页面的回调
        responsive.subscribe(self.page, "dino.play", self._on_resize)
        try:
            self._task = self.page.run_task(self._loop)
        except Exception:                   # noqa: BLE001
            self._task = None

    def _on_resize(self, *_args):
        """屏幕尺寸变了：重算舞台尺寸；宽窄模式切换时原地换一套排版。"""
        self._layout()
        self._apply_stage_size()
        self._reflow()
        self._refresh()

    def _detach(self):
        if self._task is not None:
            try:
                self._task.cancel()
            except Exception:               # noqa: BLE001
                pass
            self._task = None
        try:
            self.page.on_keyboard_event = self._prev_keyboard
        except Exception:  # noqa: BLE001
            pass
        responsive.unsubscribe(self.page, "dino.play", self._on_resize)
        self.pad.detach()

    def _restart(self, start: bool = True):
        """重开一局，默认**立即起跑**。

        若停在「待开始」界面，玩家还得再按一次空格，看起来就像重开没反应；
        所以死后按空格 / 点击 / R / 重开按钮，都直接换成一局正在跑的新引擎。
        主循环每帧重读 self.engine，下一帧就会接着 step。
        """
        self._best = max(self._best, int(self.engine.score))
        self.engine = Dino()
        self.engine.best = self._best
        if start:
            self.engine.start()
        self._log_saved = False
        self._obstacle_ctrls.clear()
        self._cloud_ctrls.clear()
        self._refresh()

    def _toggle_pause(self):
        self.engine.toggle_pause()
        self._refresh()

    # ---------- 历史记录 ----------

    def _save_match_log(self) -> None:
        if self._log_saved:
            return
        e = self.engine
        # 先标记再判分数：结束态主循环每帧都会走到这里，0 分不落盘时也要
        # 避免反复重试（重开时 _restart 会把标记重置）。
        self._log_saved = True
        if e.score <= 0:
            return
        self._best = max(self._best, int(e.score))
        meta = {
            "状态": "游戏结束",
            "分数": str(int(e.score)),
            "最高分": str(self._best),
            "速度": f"{e.speed:.2f}",
            "模式": "单人",
        }
        lines = [
            f"分数：{int(e.score)}",
            f"最高分：{self._best}",
            f"最终速度：{e.speed:.2f}",
            "结果：游戏结束",
        ]
        try:
            from core import history
            history.save_match_log("dino", lines, meta)
        except Exception as exc:          # noqa: BLE001
            print(f"[dino] 保存历史记录失败：{exc!r}")


def build(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    return _PlayPage(page, navigate).build()
