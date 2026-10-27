# -*- coding: utf-8 -*-
"""简体中文（母本）。

所有键都必须在这里出现一次；其它语言缺键时会自动回退到本表，
所以「翻译一半」是安全的，界面上不会冒出 key。

键名约定：``模块.条目``
    common.*    通用按钮 / 状态
    route.*     核心路由标题
    menu.*      主菜单
    single.*    单人游戏页
    profile.*   我的
    settings.*  设置页
    window.*    窗口模式
    mp.*        多人游戏页（建房间 / 搜索房间）
    room.*      房间大厅
    history.*   历史记录页
    game.<id>.* 游戏插件卡（标题 / 说明）
    其余按游戏分：guandan.* / chess.* / splendor.* / chinese_chess.*
"""

from __future__ import annotations

STRINGS: dict[str, str] = {
    # ---------------- 通用 ----------------
    "common.back": "返回",
    "common.cancel": "取消",
    "common.coming_soon": "敬请期待",
    "common.on": "开",
    "common.off": "关",

    # ---------------- 核心路由 ----------------
    "route.home": "ATR Game",
    "route.single": "单人游戏",
    "route.multiplayer": "多人游戏",
    "route.room": "多人房间",
    "route.profile": "我的",
    "route.settings": "设置",

    # ---------------- 主菜单 ----------------
    "menu.settings": "设置",
    "menu.me": "我的",
    "menu.no_nick": "还没起名",
    "menu.where": "想去哪儿？",
    "menu.single": "单人游戏",
    "menu.single_desc": "自己和 AI 玩，或者用单机小工具",
    "menu.multiplayer": "多人游戏",
    "menu.multiplayer_desc": "同一 WiFi 下开房间一起玩，带语音",
    "menu.footer": "v0.4.8 · 支持局域网联机",

    # ---------------- 单人游戏 ----------------
    "single.title": "单人游戏",
    "single.subtitle": "挑一款，自己和 AI（或本地工具）玩。",
    "single.more": "更多游戏",
    "single.more_desc": "跳刀 / 斗地主 / 跑得快……敬请期待。",

    # ---------------- 我的 ----------------
    "profile.title": "我的",
    "profile.subtitle": "这个名字会显示在多人游戏的房间里。",
    "profile.current_nick": "当前名字",
    "profile.nick_source": "名字来源",
    "profile.nick_self": "自己起的",
    "profile.nick_random": "系统随机（还没改过）",
    "profile.change_nick": "改名字",
    "profile.random": "随机",
    "profile.save": "保存",
    "profile.empty_error": "名字不能是空的",
    "profile.too_long": "名字最多 16 个字",
    "profile.saved": "已保存：{nick}",
    "profile.rolled": "随机一个：{nick}（点保存才生效）",
    "profile.tip": "第一次进房间没起过名的话，系统会临时给你一个随机名字，"
                   "改完之后房间里马上就能看到。",

    # ---------------- 设置 ----------------
    "settings.title": "设置",
    "settings.section_language": "语言",
    "settings.language_note": "切换后整个应用（菜单、房间、游戏子菜单……）"
                              "立刻换语言，不需要重启。",
    "settings.section_pack": "界面风格",
    "settings.pack_note": "切换后整个应用（含掼蛋牌桌）立刻换皮；"
                          "以后接入社区包也会出现在这里。",
    "settings.pack_author": "by {author}",
    "settings.pack_community": " · 社区包",
    # 界面包的名字 / 说明：键是 pack.<包 id>.name|desc，社区包没登记就显示自带的
    "pack.default.name": "默认（材料）",
    "pack.default.desc": "干净的材料风界面，跟随明暗主题；游戏界面也用它。",
    "pack.rustic.name": "暗黑2 / MC（石砖）",
    "pack.rustic.desc": "地下城大厅风：石砖斜面、暗金描边、火把分割线。",
    "settings.section_appearance": "外观",
    "settings.dark_theme": "深色主题",
    "settings.theme_current": "当前：{mode}",
    "settings.theme_light": "浅色",
    "settings.theme_dark": "深色",
    "settings.dark_note": "提示：暗黑2 / MC 石砖风本身就是暗色，"
                          "深浅开关只对默认风格有意义。",
    "settings.section_ui": "界面",
    "settings.shortcut_hint": "显示快捷键提示",
    "settings.window_mode": "窗口模式",
    "settings.data_dir": "用户数据目录：{path}",

    # ---------------- 窗口模式 ----------------
    "window.fullscreen": "全屏（默认）",
    "window.maximized": "最大化",
    "window.windowed": "窗口",

    # ---------------- 多人游戏（建房间 / 搜索房间） ----------------
    "mp.title": "多人游戏",
    "mp.your_nick": "你的名字：{nick}",
    "mp.tab_create": "建立房间",
    "mp.tab_search": "搜索房间",
    "mp.room_name": "房间名",
    "mp.room_name_default": "{nick}的房间",
    "mp.room_code": "房间码",
    "mp.room_code_hint": "4~8 位，同伴进房间要用",
    "mp.random": "随机",
    "mp.game": "游戏",
    "mp.no_games": "（暂无可用游戏）",
    "mp.spectator_note": "人数多于本局所需时，多出来的人自动转为观战。",
    "mp.seats": "席位",
    "mp.seats_n": "{n} 人",
    "mp.your_name": "你的名字",
    "mp.your_name_hint": "房间里别人看到的名字，随时可在「我的」里改",
    "mp.create_btn": "建立房间",
    "mp.create_hint": "房间建好后，同一 WiFi / 局域网里的伙伴在「搜索房间」里"
                      "就能看到；把房间码口头报给他才能进。",
    "mp.enter": "进入",
    "mp.enter_room": "进入房间",
    "mp.unnamed_room": "（无名房间）",
    "mp.room_meta": "{game} · 房主 {host} · {ip}",
    "mp.scanning": "🧭 正在搜索局域网里的房间…",
    "mp.scan_hint": "让开房间的伙伴先建好房间，两边的电脑要在同一个 "
                    "WiFi / 局域网下。",
    "mp.code_dialog_title": "进入 {name}",
    "mp.code_dialog_hint": "房主：{host} · {game}",
    "mp.code_placeholder": "房间码（房主那儿问）",
    "mp.code_too_short": "房间码至少 4 位",
    "mp.name_required": "先给房间起个名字",
    "mp.create_failed": "开房失败：本机 UDP 端口用不了？（网络权限？）",
    "mp.join_failed": "加入失败：本机 UDP 端口用不了？",
    "mp.joining": "正在加入「{name}」…",
    "mp.join_reject": "进不去：{reason}",
    "mp.no_response": "房主没有回应（可能已经关了房间，或不在同一局域网）",
    "mp.scan_busy": "扫描端口被占用了（已经有一个搜索在跑？）",
    "mp.no_room_yet": "还没建房间：先在上面填一下，点「建立房间」。",

    # ---------------- 房间大厅 ----------------
    "room.title": "多人房间",
    "room.empty": "这里现在没有房间。",
    "room.back_mp": "回多人游戏",
    "room.room": "房间",
    "room.code": "房间码 {code}",
    "room.head_info": "房主 {host} · {game} · {addr}",
    "room.head_hint": "同一 WiFi / 局域网里的伙伴在「搜索房间」里能看到这个房间，"
                      "报房间码给他才能进来。",
    "room.seats": "席位",
    "room.seats_hint": "点空位可以坐下 / 换座；🎤 是开着麦的，"
                       "🔇 是关了麦的，♛ 是房主。超出本局人数的位子为观战席。",
    "room.empty_seat": "空位 {n}",
    "room.spectator": " · 观战",
    "room.spectator_paren": "（观战）",
    "room.players_note": "{n} 人上场",
    "room.players_note_extra": "{n} 人上场，多出来的人观战",
    "room.select_game": "选游戏（房主可切换）",
    "room.current_game": "本局游戏",
    "room.game_changed": "房主把游戏换成了 {game}",
    "room.voice": "语音",
    "room.mic_on": "开麦克风",
    "room.mic_off": "关麦克风",
    "room.speaker_on": "开扬声器",
    "room.speaker_off": "关扬声器",
    "room.level": "电平",
    "room.voice_tip": "进房间默认不录音 —— 点「开麦克风」才开始说话，"
                      "对方的语音会自动放出来。",
    "room.voice_unavailable": "这台机器没有语音库，装了 sounddevice + numpy "
                              "后才能说话。",
    "room.chat": "聊天",
    "room.chat_placeholder": "说点什么…",
    "room.send": "发送",
    "room.start": "开始",
    "room.wait_start": "等待开始",
    "room.entered": "进入房间「{name}」· {game}",
    "room.leave": "离开房间",
    "room.mic_enabled": "麦克风已开启",
    "room.mic_disabled": "麦克风已关闭",
    "room.speaker_enabled": "扬声器已开启",
    "room.speaker_muted": "扬声器已静音",
    "room.mic_error": "麦克风没能打开：看看系统有没有给麦克风权限，"
                      "或者设备被别的软件占着？",
    "room.start_broadcast": "房主发起了游戏，出发！",
    "room.kicked": "房主把你移出了房间",
    "room.game_not_ready": "「{game}」还没接好联机房间，先把人凑齐就是了。",
    "room.game_failed": "对局页没能打开（详情见运行日志）。留在房间里稍等或重试一次。",

    # ---------------- 联机（网络层给界面看的话） ----------------
    "net.wrong_code": "房间码不对",
    "net.no_response": "房主没有回应（网络不通？）",
    "net.already_started": "已经开始",
    "net.room_full": "房间满员",
    "net.anon": "无名旅人",
    "net.wrong_code_sys": "有人（{ip}）房间码输错了，已拒绝",
    "net.joined": "{nick} 加入了房间",
    "net.left": "{nick} 离开了房间",
    "net.dropped": "{nick} 掉线了",
    "voice.port_error": "语音端口打不开：{exc}",
    "voice.mic_error": "麦克风打不开：{kind}: {exc}",
    "voice.speaker_error": "扬声器打不开：{kind}: {exc}",

    # ---------------- 历史记录（通用页） ----------------
    "history.refresh": "刷新",
    "history.open_dir": "打开数据目录",
    "history.section": "── 记录全文 ──",
    "history.log_dir": "日志目录：{path}",
    "history.log_dir_na": "日志目录：不可用",
    "history.count": "共 {n} 场记录",
    "history.none": "还没有记录",
    "history.empty_body": "还没有记录。\n\n打完一局后，对局记录会自动保存到这里；"
                          "中途退出也会留一份。",
    "history.empty_item": "（空）",
    "history.empty_file": "（空文件）",
    "history.read_failed": "（读取失败：{exc}）",
    "history.open_failed": "打不开目录，请手动前往：\n{path}\n（{exc}）",
    "history.win_suffix": "{win}获胜",
    "history.hands": "{n} 局",

    # ---------------- 游戏：掼蛋 ----------------
    "game.guandan.title": "掼蛋",
    "game.guandan.desc": "两副牌、四人两两结对、按级升级的经典牌类。",
    "guandan.choose_mode": "选择一个模式",
    "guandan.play": "开始游戏",
    "guandan.play_desc": "用上次的房间与座位配置直接开局：单人 / 三人机。",
    "guandan.board": "快速记牌",
    "guandan.board_desc": "记录出牌，按四家视角计算炸弹概率。",
    "guandan.types": "牌型速查",
    "guandan.types_desc": "常见牌型与大小关系速记。",
    "guandan.simulator": "全模拟",
    "guandan.simulator_desc": "AI 自动互玩整场，图形化观战（真牌图）。",
    "guandan.history": "历史记录",
    "guandan.history_desc": "查看往期出牌记录（每整场结束自动保存）。",
    "guandan.advisor": "AI 建议",
    "guandan.advisor_desc": "输入自己手牌，让算法给出推荐出牌。",
    "guandan.advisor_heading": "AI 建议模式",
    "guandan.advisor_body": "输入自己的手牌，算法会基于已记到的牌和手牌组成，"
                            "给出当前最优的出牌建议。",
    "guandan.advisor_badge": "0.5 上线",
    "guandan.types_intro": "以下为掼蛋中常见牌型。炸弹及天王炸在比较时无视牌型，"
                           "只看张数；同张数时再比点数（2 最小，A 最大）。",
    "guandan.types_note": "提示：本工具目前仅计算 4 张及以上同点数的炸弹"
                          "（含赖子），同花顺与其它牌型留到 0.5 引入。",
    # 牌型速查的每一行：名字 + 说明（example 是牌面，不翻译）
    "types.single": "单张",
    "types.single_desc": "任意一张牌",
    "types.pair": "对子",
    "types.pair_desc": "两张同点数",
    "types.trio": "三张",
    "types.trio_desc": "三张同点数",
    "types.full": "三带二",
    "types.full_desc": "三张同点数 + 一对",
    "types.straight": "顺子",
    "types.straight_desc": "5 张或更多连续点数（2 不参与，级牌可作任意牌）",
    "types.flush": "同花顺",
    "types.flush_desc": "同一花色的顺子（掼蛋中最大的普通牌型）",
    "types.plate": "钢板",
    "types.plate_desc": "两组连续三张",
    "types.bomb4": "炸弹（4 张）",
    "types.bomb4_desc": "4 张同点数 > 上面所有牌型",
    "types.bomb5": "炸弹（5 张）",
    "types.bomb5_desc": "5 张同点数 > 4 张炸弹",
    "types.bomb6": "炸弹（6 张）",
    "types.bomb6_desc": "6 张同点数 > 5 张炸弹",
    "types.bomb7": "炸弹（7+ 张）",
    "types.bomb7_desc": "越多越大",
    "types.jokers": "天王炸",
    "types.jokers_desc": "两副牌里的所有王（4 张），最大牌型",

    # ---------------- 游戏：国际象棋 ----------------
    "game.chess.title": "国际象棋",
    "game.chess.desc": "双人对弈的经典国际象棋，含王车易位、吃过路兵、"
                       "升变等特殊规则。",
    "chess.home.intro": "本地双人（一手白、一手黑）：在同一设备上轮流操作。"
                        "支持王车易位、吃过路兵与兵的升变。",
    "chess.home.play": "开始对局",
    "chess.home.play_desc": "本地双人轮流操作，含悔棋 / 重开 / 换皮肤",
    "chess.home.history": "历史记录",
    "chess.home.history_desc": "回看以前下过的棋局着法",

    # ---------------- 游戏：占位（璀璨宝石 / 中国象棋） ----------------
    "game.splendor.title": "Splendor",
    "game.splendor.desc": "收集宝石、换取发展卡，率先累积 15 点声望取胜的"
                          "轻策略桌游。",
    "splendor.stub": "璀璨宝石正在筹备中：宝石收集、发展卡与声望结算将陆续开放。",
    "game.chinese_chess.title": "Chinese Chess",
    "game.chinese_chess.desc": "楚河汉界、九宫纵横的传统象棋，马走日、"
                               "象飞田各有章法。",
    "chinese_chess.stub": "中国象棋正在筹备中：棋盘、走子规则与 AI 对手"
                          "将陆续开放。",
}
