# ATR Game 代码地图（逐文件作用说明）

> 本文件是 **代码的目录说明**：每个源码文件放在哪一类、负责什么、依赖谁。
> 想改某个功能时，先在这里找到对应的文件，再去看那个文件顶部的 docstring。
>
> 配套阅读：每个 `.py` 文件的开头都有一段中文 docstring，写清「这个文件负责什么」。

---

## 一、整体分层

```
                 app.py / main.py                ← 入口：起窗口、注册路由
                        │
         ┌──────────────┴──────────────┐
         │                             │
    core/（框架层）              games/（游戏层）
    通用能力，不含玩法            具体玩法，插件化接入
```

| 层 | 目录 | 说明 |
| --- | --- | --- |
| 入口层 | `app.py` `main.py` `build_all.py` | 起 Flet 页面、注册路由、构建安装包 |
| 框架层 | `core/` | 路由、主题、界面包、国际化、联机、历史记录……**与具体游戏无关** |
| 游戏层 | `games/` | 每个游戏一个子包，通过 `GamePlugin` 注册菜单与路由 |
| 规则层 | `games/guandan/`（纯逻辑） | 掼蛋的牌、牌型、引擎、进贡、AI —— **不依赖 flet** |

**依赖方向是单向的**：`games/` 可以用 `core/`，反过来不行。
`games/guandan/` 里的纯逻辑模块（`cards` `rules*` `engine` `state` `hand`
`settle` `serialize` `tribute` `ai` `analyzer`）**完全不 import flet**，
所以能被命令行自检直接调用。

---

## 二、文件分类速查

### A. 入口与构建（3 个）

| 文件 | 行数 | 作用 |
| --- | --- | --- |
| `app.py` | 77 | 应用入口：配置 Flet 页面尺寸、注册核心路由（含 0.4.9 新增的「游玩记录」）、启动路由。`import games` 会触发各游戏插件注册。 |
| `main.py` | 26 | `python -m main` 的启动脚本（桌面端）。 |
| `build_all.py` | 86 | 打包脚本：把源码打成 macOS/Windows 可执行程序与安装包。 |

### B. 框架层 · 路由与注册（2 个）

| 文件 | 行数 | 作用 |
| --- | --- | --- |
| `core/registry.py` | 149 | 游戏注册中心：登记「有哪些游戏 / 有哪些菜单项 / 有哪些路由」，并提供 `NavigateFn` 跳转函数类型。 |
| `core/router.py` | 97 | 路由表：把 URL 映射到页面构造函数，并且**带缓存**（同一路由复用同一个控件，所以换页前要 `invalidate`）。 |

### C. 框架层 · 界面与主题（9 个）

| 文件 | 行数 | 作用 |
| --- | --- | --- |
| `core/theme.py` | 207 | 颜色 / 字号 / 间距令牌表（`T`）。明暗两套，写死在这一处。 |
| `core/ui_theme.py` | 220 | 「当前界面包」的调度层：把 `title/panel/button/card/slot/chat_row` 等零件转发给正在用的界面包。 |
| `core/ui_common.py` | 180 | 视图层常用的通用零件（顶栏、页面留白、菜单卡片等）。 |
| `core/ui_packs/base.py` | 216 | 界面包**基类**：定义一个界面包必须实现哪些零件（抽象接口）。 |
| `core/ui_packs/material.py` | 339 | 默认「材料风」界面包：干净、现代，是所有界面的默认皮。 |
| `core/ui_packs/rustic.py` | 407 | 「暗黑2 石砖风」界面包：暗金火把线的复古质感。 |
| `core/ui_packs/registry.py` | 54 | 界面包注册表：登记有哪些可用界面包（社区包往这里加）。 |
| `core/window.py` | 75 | 窗口模式（全屏 / 窗口化 / 记住上次）及相关尺寸计算。 |
| `core/settings.py` | 73 | 设置项的读写：主题、语言、界面包、窗口模式、昵称等的本地持久化。 |

### D. 框架层 · 国际化（3 个）

| 文件 | 行数 | 作用 |
| --- | --- | --- |
| `core/i18n.py` | 228 | 翻译表读取与 `t(key)` 查词；支持回退到中文、按语言刷新界面。 |
| `core/locales/zh_CN.py` | 296 | 简体中文文案。 |
| `core/locales/en_US.py` | 312 | 英文文案。 |

### E. 框架层 · 页面（8 个）

| 文件 | 行数 | 作用 |
| --- | --- | --- |
| `core/views/menu_view.py` | 116 | 主菜单：按已注册的游戏生成大卡片。 |
| `core/views/single_view.py` | 57 | 单人游戏页（框架自带的通用外壳）。 |
| `core/views/multiplayer_view.py` | 493 | 多人联机页：创建房间 / 搜索房间（局域网 UDP 广播发现）。 |
| `core/views/room_view.py` | 400 | 房间大厅骨架：进房、选游戏、开始、离开、事件轮询。 |
| `core/views/room_widgets.py` | 201 | 房间大厅的界面零件：席位区、语音区、聊天区。 |
| `core/views/settings_view.py` | 401 | 设置页：语言 / 界面风格 / 明暗主题 / 快捷键 / 窗口模式 / 数据目录。 |
| `core/views/profile_view.py` | 124 | 个人资料页：昵称与设备号，可改名、可随机生成。 |
| `core/views/ui_rustic.py` | 341 | 早期手写的石砖风控件（**已不再被引用**，保留作历史参考）。 |

### F. 框架层 · 联机（8 个）

| 文件 | 行数 | 作用 |
| --- | --- | --- |
| `core/net/__init__.py` | 26 | 联机协议常量与编解码：包类型、可靠序号、`encode/decode`、房间码哈希。 |
| `core/net/discovery.py` | 290 | 局域网发现：房主广播 beacon、客人扫描房间。 |
| `core/net/session.py` | 400 | 房间会话主体：建房 / 加入 / 关闭、席位、聊天、语音开关、玩法透传，以及全局「当前房间」。 |
| `core/net/member.py` | 45 | 房间里「一个人」的数据结构（昵称、席位、是否房主、是否在说话…）。 |
| `core/net/session_const.py` | 15 | 心跳 / 重传 / 超时的时间参数。 |
| `core/net/session_reliable.py` | 243 | 可靠传输那一半：收发包、ACK、重传、心跳、席位表广播。 |
| `core/net/session_messaging.py` | 226 | 消息处理那一半：收到各类包之后干什么（握手 / 席位表 / 聊天 / 开始 / 玩法）。 |
| `core/net/session_game.py` | 49 | 玩法消息透传：把游戏消息原样转给房间里跑的游戏。 |
| `core/net/voice.py` | 368 | 语音：采集 20ms 音频帧、UDP 单点发送、回放、电平统计。 |
| `core/net/selftest.py` | 181 | 联机层自检：发现与加入、可靠消息、语音链路。 |

### G. 框架层 · 记录与资料（4 个）

| 文件 | 行数 | 作用 |
| --- | --- | --- |
| `core/history.py` | 177 | 对局记录**落盘**：写文件、列文件、读文件；`game_ids()` / `recent_logs_all()` 用来跨游戏汇总（0.4.9 新增）。 |
| `core/history_view.py` | 370 | 历史记录页：左边列表、右边详情；`all_games` 模式列出所有游戏的记录。 |
| `core/profile.py` | 173 | 本地资料：昵称、设备号、房间码记忆、上次房间名。 |
| `core/views/history_view.py` | 82 | 主页「游玩记录」页：汇总所有游戏 + 顶部按游戏筛选（0.4.9 新增）。 |

### H. 掼蛋 · 纯逻辑（不依赖 flet，可命令行直接跑）（15 个）

| 文件 | 行数 | 作用 |
| --- | --- | --- |
| `games/guandan/cards.py` | 279 | 牌与牌堆：108 张牌怎么生成、大小顺序、级牌感知排序、逢人配判定。 |
| `games/guandan/rules_base.py` | 109 | 牌型的「公共零件」：牌型枚举 `ComboType`、牌型数据结构 `Combo`、共用小工具。 |
| `games/guandan/rules_parse.py` | 282 | **牌型识别**：给一组牌判断它是什么牌型（「就高解释」）。 |
| `games/guandan/rules_compare.py` | 38 | **大小比较**：这一手牌能不能压过那一手。 |
| `games/guandan/rules.py` | 331 | **牌型枚举**：从手牌里列出所有能真正打出的牌型（供 AI 用）；同时是上面三个模块的门面。 |
| `games/guandan/state.py` | 113 | 对局的静态状态：常量、`MatchState`、开新场。 |
| `games/guandan/hand.py` | 219 | **一手牌的状态机**：出牌 / 跟牌 / 过牌 / 接风 / 出完判定。 |
| `games/guandan/settle.py` | 80 | 一手结束后的升级结算 + 下一把的进贡安排。 |
| `games/guandan/serialize.py` | 260 | 联机用的 JSON 序列化 / 还原（房主权威的整局快照）。 |
| `games/guandan/engine.py` | 78 | 引擎**门面**：把上面四个模块再导出一遍，老写法 `from .engine import Hand` 不用改。 |
| `games/guandan/tribute.py` | 428 | 进贡 / 还贡 / 抗贡的完整规则（含王对、双下、还贡要最大牌等细节）。 |
| `games/guandan/ai.py` | 43 | AI 选牌：给定手牌与场面，挑一手最合理的牌出来。 |
| `games/guandan/analyzer.py` | 420 | 记牌器：按四家视角推算各家已出的牌、剩余牌与炸弹概率。 |
| `games/guandan/simulator.py` | 109 | 命令行版全模拟：自己跑 N 局 AI 对局做统计。 |
| `games/guandan/config.py` | 282 | 对局配置：座位表（哪个座位是人 / 电脑）、本机座位、牌局设置。 |

### I. 掼蛋 · 界面（17 个）

| 文件 | 行数 | 作用 |
| --- | --- | --- |
| `games/guandan/plugin.py` | 79 | 掼蛋插件声明：向框架登记菜单项与路由。 |
| `games/guandan/assets.py` | 87 | 牌面图片等静态资源的路径与加载。 |
| `games/guandan/views/home_view.py` | 123 | 掼蛋子菜单：开始游戏 / 记牌 / 模拟 / 历史记录 / 牌型速查。 |
| `games/guandan/views/play_view.py` | 363 | **对局牌桌的组装**：状态、界面骨架、生命周期；下面五个 mixin 拼成一个 `_Play`。 |
| `games/guandan/views/play_const.py` | 166 | 牌桌的配色 / 尺寸 / 时间参数 + 纯工具函数。 |
| `games/guandan/views/play_table.py` | 417 | 牌桌「画面」：顶栏 / 席位 / 待压区 / 手牌 / 结算 / 按钮。 |
| `games/guandan/views/play_actions.py` | 357 | 牌桌「真人操作」：选牌 / 出牌 / 过牌 / 进贡面板。 |
| `games/guandan/views/play_ai.py` | 104 | 牌桌「电脑代打」：协程驱动 AI 出牌。 |
| `games/guandan/views/play_net.py` | 327 | 牌桌「联机同步」：房主权威 + 整局快照 + 客人请求转发。 |
| `games/guandan/views/play_flow.py` | 199 | 牌桌「流转」：结算 / 落盘 / 离开确认 / 发下一手。 |
| `games/guandan/views/board_view.py` | 374 | 快速记牌页：选玩家、选级牌、点牌标记「已出」。 |
| `games/guandan/views/board_widgets.py` | 164 | 记牌页的牌面按钮组件（普通牌 / 王）。 |
| `games/guandan/views/simulator_view.py` | 207 | 全模拟观战页入口：顶栏 + 控制条 + 牌桌画面。 |
| `games/guandan/views/sim_session.py` | 349 | 观战会话：本机跑 AI 对局并把每一步渲染成动画。 |
| `games/guandan/views/sim_const.py` | 84 | 观战页的配色 / 尺寸 / 画牌图工具。 |
| `games/guandan/views/types_view.py` | 146 | 牌型速查表。 |
| `games/guandan/views/advisor_view.py` | 67 | AI 建议页（占位，0.5 规划中）。 |
| `games/guandan/views/history_view.py` | 64 | 掼蛋历史记录页入口（复用 `core/history_view.py`）。 |

### J. 国际象棋（9 个）

| 文件 | 行数 | 作用 |
| --- | --- | --- |
| `games/chess/plugin.py` | 52 | 国际象棋插件声明。 |
| `games/chess/engine.py` | 493 | 棋规引擎：走子合法性、将军 / 将死、升变、吃过路兵、易位、王车易位权。 |
| `games/chess/assets.py` | 54 | 棋子图片路径。 |
| `games/chess/views.py` | 243 | 象棋视图组装：子菜单、视图骨架、工具栏、生命周期。 |
| `games/chess/views_board.py` | 233 | 棋盘画面、点格子走子、兵升变。 |
| `games/chess/views_sync.py` | 191 | 联机对弈：算身份（白 / 黑 / 观战）、同步局面、轮询席位。 |
| `games/chess/views_record.py` | 92 | 棋谱记录与落盘（与掼蛋共用 `core/history`）。 |
| `games/chess/history_view.py` | 61 | 象棋历史记录页入口。 |
| `games/chess/selftest.py` | 129 | 棋规自检：开局着法、将死、悔棋、升变、吃过路兵、易位权、将军判定。 |

### K. 掼蛋自检（5 个）

| 文件 | 行数 | 作用 |
| --- | --- | --- |
| `games/guandan/selftest.py` | 63 | 自检入口：汇总所有用例并汇报。跑法 `python -m games.guandan.selftest`。 |
| `games/guandan/selftest_common.py` | 26 | 自检公共小工具：造牌、固定级牌背景。 |
| `games/guandan/selftest_cards.py` | 151 | 用例：牌堆、大小顺序、牌型识别、逢人配。 |
| `games/guandan/selftest_engine.py` | 181 | 用例：动作守卫、级牌归属不变量、自对弈收尾。 |
| `games/guandan/selftest_tribute.py` | 267 | 用例：进贡 / 还贡 / 抗贡 / 双下 / 选贡 / 谁先出。 |

### L. 占位游戏（3 个）

| 文件 | 行数 | 作用 |
| --- | --- | --- |
| `games/placeholder.py` | 64 | 未实现游戏的通用占位页。 |
| `games/splendor/plugin.py` | 43 | Splendor 占位插件（菜单里是灰的）。 |
| `games/chinese_chess/plugin.py` | 43 | 中国象棋占位插件（菜单里是灰的）。 |

### M. 五子棋（6 个，0.4.9 新增）

| 文件 | 行数 | 作用 |
| --- | --- | --- |
| `games/gomoku/plugin.py` | 48 | 五子棋插件声明（players=2，路由 /g/gomoku、/g/gomoku/play、/g/gomoku/history）。 |
| `games/gomoku/engine.py` | 175 | 棋局引擎：15 路棋盘、落子、五连判胜、平局、悔棋、序列化（联机快照）。 |
| `games/gomoku/views.py` | 63 | 子菜单：本地对局 / 历史记录 / 规则说明。 |
| `games/gomoku/views_board.py` | 481 | 棋盘画面（棋子落在**线的交汇点**上）、落子、悔棋、重开、联机同步、落盘；**棋盘尺寸按屏幕宽度缩放**（手机上 448 → 320，整盘留在屏幕里）。 |
| `games/gomoku/history_view.py` | 65 | 五子棋历史记录页入口（复用 `core/history_view.py`）。 |
| `games/gomoku/selftest.py` | 53 | 引擎自检：落子合法性 / 横五连 / 斜五连 / 悔棋 / 序列化往返。 |

### N. 俄罗斯方块（6 个，0.4.9 新增）

| 文件 | 行数 | 作用 |
| --- | --- | --- |
| `games/tetris/plugin.py` | 49 | 俄罗斯方块插件声明（players=1、online=False，不进多人房间列表）。 |
| `games/tetris/engine.py` | 302 | 引擎：七种方块、移动 / 旋转 / 消行 / 计分 / 等级 / Hold / 幽灵块 / 序列化。 |
| `games/tetris/views.py` | 64 | 子菜单：开始游戏 / 历史记录 / 操作说明。 |
| `games/tetris/views_play.py` | 375 | 对局页：棋盘画面、输入统一（键盘 / 触屏 / 滑动走同一个 `_act`）、重力循环、落盘。 |
| `games/tetris/views_pad.py` | 130 | **触屏操作键**：← → 移动、↻ 旋转、↓ 软降、⤓ 硬降、暂存；按住能连发（`on_tap_down`/`on_tap_up`）。 |
| `games/tetris/views_layout.py` | 152 | 页面组装：宽屏「棋盘 + 右侧信息栏」，窄屏「顶部信息条 + 棋盘 + 底部操作键」。 |
| `games/tetris/history_view.py` | 59 | 俄罗斯方块历史记录页入口。 |
| `games/tetris/selftest.py` | 35 | 引擎自检：方块齐全 / 硬降消行 / 同种子确定性 / 序列化往返。 |

### O. 台球（12 个，0.4.9 新增）

| 文件 | 行数 | 作用 |
| --- | --- | --- |
| `games/billiards/plugin.py` | 49 | 台球插件声明（players=2、online=True，路由 /g/billiards、/g/billiards/play、/g/billiards/history）。 |
| `games/billiards/assets.py` | 44 | 贴图资源：球桌 `table.png`（1200×678，绿色台面区 1087×565）、球 `ball_1~16.png`；贴图路径与台面区的几何常量。 |
| `games/billiards/physics.py` | 393 | **物理内核**（不依赖 flet）：球、球桌尺寸与缩放、摆球、库边反弹、等质量弹性碰撞、滚动摩擦、**子步进防穿透**、落袋判定（袋口位置量自贴图）、合法落点查找。 |
| `games/billiards/engine.py` | 397 | **规则引擎**（不依赖 flet）：中式八球简化规则 —— 定花色、犯规判定（空杆 / 白球落袋 / 打进对方球）、换手、自由球、8 号球胜负、整局快照序列化。 |
| `games/billiards/views_table.py` | 207 | 球桌画面：球桌贴图（按台面区对齐物理坐标）+ 绝对定位的球 + 瞄准线；`ft.GestureDetector` 把手势转成物理坐标。 |
| `games/billiards/views_gesture.py` | 122 | 手势 mixin：按住白球往后拉（拉弓）瞄准、犯规后拖动摆白球。 |
| `games/billiards/views_net.py` | 220 | 联机 mixin：算身份（1 号 / 2 号 / 观战）、击球请求、摆球请求、房主广播整局快照。 |
| `games/billiards/views_play.py` | 417 | 对局页：组装球桌与信息栏、60FPS 物理主循环、界面刷新、重开、落盘。 |
| `games/billiards/views.py` | 65 | 子菜单：开始对局 / 历史记录 / 规则说明。 |
| `games/billiards/history_view.py` | 63 | 台球历史记录页入口（复用 `core/history_view.py`）。 |
| `games/billiards/selftest.py` | 322 | 自检：摆球不重叠 / 碰撞交换法向速度 / 摩擦停球 / 撞库不出台 / 进袋 / 高速不穿透 / 犯规换手 / 8 号球胜负 / 快照往返。 |
| `games/billiards/__init__.py` | 3 | 包入口（import 即注册）。 |


---

## 三、命名与放置约定

| 想加的东西 | 放哪 | 例子 |
| --- | --- | --- |
| 一个新游戏 | `games/<名字>/`，含 `plugin.py` + `views/` | `games/chess/` |
| 纯规则 / 算法 | `games/<名字>/` 下的独立模块，**不要 import flet** | `games/guandan/rules.py` |
| 一个新页面 | 对应游戏的 `views/` 下，一个文件一个页面 | `games/guandan/views/home_view.py` |
| 一个通用界面零件 | 加到 `core/ui_packs/base.py` 的抽象接口，再在各界面包里实现 | `core/ui_packs/material.py` |
| 一个新的联机包类型 | `core/net/__init__.py` 加常量，再在 `session_messaging.py` 加处理函数 | |
| 一个新文案 | `core/locales/zh_CN.py` 与 `en_US.py` 同时加键 | |

**文件大小上限：500 行**。超了就按「职责」拆开（本仓库所有文件目前都在 500 行以内）。

---

## 四、本次整理做了什么（0.4.8 整理版）

### 1. 拆分超长文件

原来有 8 个文件超过 500 行，全部按职责拆开：

| 原文件 | 原行数 | 拆成 |
| --- | --- | --- |
| `games/guandan/views/play_view.py` | 1681 | `play_view.py` + `play_const.py` + `play_table.py` + `play_actions.py` + `play_ai.py` + `play_net.py` + `play_flow.py` |
| `core/net/session.py` | 828 | `session.py` + `member.py` + `session_const.py` + `session_reliable.py` + `session_messaging.py` + `session_game.py` |
| `games/chess/views.py` | 663 | `views.py` + `views_board.py` + `views_sync.py` + `views_record.py` |
| `games/guandan/selftest.py` | 616 | `selftest.py` + `selftest_common.py` + `selftest_cards.py` + `selftest_engine.py` + `selftest_tribute.py` |
| `games/guandan/engine.py` | 605 | `engine.py`（门面）+ `state.py` + `hand.py` + `settle.py` + `serialize.py` |
| `games/guandan/rules.py` | 593 | `rules.py` + `rules_base.py` + `rules_parse.py` + `rules_compare.py` |
| `core/views/room_view.py` | 554 | `room_view.py` + `room_widgets.py` |
| `games/guandan/views/simulator_view.py` | 546 | `simulator_view.py` + `sim_session.py` + `sim_const.py` |

另外 `games/guandan/views/board_view.py` 也拆出了 `board_widgets.py`。

### 2. 拆分的原则

* **纯逻辑**按「数据结构 / 规则识别 / 规则比较 / 枚举 / 状态机 / 结算 / 序列化」分；
* **界面**按「常量 / 画面 / 交互 / 后台任务 / 网络 / 流转」分；
* 类太长时用 **mixin** 组合（`class _Play(PlayNetMixin, PlayAiMixin, ...)`），
  方法一行不改地搬过去，行为完全一致；
* 需要「全局唯一指针」的地方（`_ACTIVE` / `_CURRENT_PLAY`）留在**组装模块**里，
  mixin 通过 `_is_current_play()` 之类的方法去问，避免 import 循环。

### 3. 保持兼容

所有对外的导入写法都没变：

```python
from .engine import Hand, new_match, settle          # 引擎门面
from games.guandan.rules import ComboType, beats, parse
from core.net.session import RoomSession, current
from games.guandan.views.play_view import build
```

### 4. 补注释

* 每个文件顶部都有一段中文 module docstring，说明「这个文件负责什么」；
* 每个函数 / 方法都有一句「它负责什么」的 docstring；
* 成块代码前加了 `# ---------- 小节标题 ----------` 分节标题（项目原有风格）；
* 关键决策加了行内注释（尤其是「为什么这么写」）。

### 5. 顺手修的小问题（都不影响原有行为）

* `core/net/session.py` 里 `Member` 与 `RoomSession` 混在一个文件 →
  `Member` 抽到 `core/net/member.py`，消除 import 循环；
* `core/ui_common.py` 里 `menu_card` 有两份定义（后者把前者覆盖了）→
  删掉被覆盖的那份，现行外观保持不变，并留注释说明；
* `games/chess/engine.py`、`games/*/history_view.py` 缺 `Any/Dict/ft` 导入 → 补上；
* `games/guandan/views/play_view.py` 的联机进贡分支少导入了 `card_from_json` → 补上；
* 清掉全项目「导入但没用」的 import。
