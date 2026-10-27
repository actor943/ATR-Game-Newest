README

ATR Game V0.4.9
===============

1. 使用方法
	启动后进入主菜单（默认全屏，可在设置里改回最大化 / 窗口）
	掼蛋：子菜单「开始游戏」直接用上次的配置进牌桌（单人 / 三人机）
	国际象棋：子菜单「开始对局」进入棋盘（本地双人轮流 / 联网对弈）；
		子菜单「历史记录」回看以前下过的棋局着法
	五子棋（0.4.9 新增）：子菜单「本地对局」下棋（15 路棋盘，黑先，
		横/竖/斜连五即胜）；「历史记录」回看以前的棋局
	俄罗斯方块（0.4.9 新增）：子菜单「开始游戏」单人消行；「历史记录」
		回看以前的分数 / 等级 / 消行数
	游玩记录（0.4.9 新增）：主页第三扇门「游玩记录」把**所有游戏**玩过的
		记录汇在一张表里，顶部可按游戏筛选
	联机房间：多人游戏 → 创建 / 搜索房间 → 进房间 → 房主「开始」众人进对局
	掼蛋子菜单：快速记牌 / 牌型速查 / 全模拟 / 开始游戏
	AI 建议后续版本上线
	右上角"设置"调整主题、窗口模式与界面偏好
	设置页最上方「语言」可切换界面语言：简体中文 / English，
		选中即整应用换语言（不需要重启）

2. 使用场景
	当你觉得网上掼蛋的记牌器居然需要豆子，太贵了点时候
	国际象棋：本地双人（一手白一手黑）已可玩；房间内也能联网对弈
		（同一 WiFi 下两人各坐一个席位即可实时同步走子）
	五子棋 / 俄罗斯方块：0.4.9 新增，均可本地开局；五子棋还能在房间里
		联机对弈（两人各坐一个席位即分别为黑方 / 白方，其余席位观战）
	已规划：掼蛋 / Splendor / Chinese Chess（后两款仍为占位）

3. 使用限制
	记牌仍需手动点击；自动识别与 AI 对手留到后续版本
	国际象棋联网对弈目前只做「两人对弈 + 观战」的走子同步；AI 对手、残局库、
		棋谱导入导出留到后续版本
	联机房间里 Chess 已带网络代码（走子/悔棋/重开实时同步）；掼蛋的多人同步
		仍待后续版本

4. 使用注意事项
	记录越及时准确，算出的概率越准
	每家剩余张数由该家已出牌数推算（起手 27 张）
	进贡在每局发牌后进行：末游把最大的牌（红桃级牌除外）交给头游，
		头游还一张 10 以下（含 10）的牌；末游有两 chi 大王可抗贡；
		双下时两个输家都进贡，头游拿大的、二游拿小的；
		双下且贡牌点数相等时可选贡（赢家各挑各的，输家也各挑各的还牌）

5. 使用技巧
	最好等更多的时间在网络掼蛋中，因为你要记录

6. 数据位置
	设置：~/Library/Application Support/ATR Game/settings.json（Mac）
		Windows：%APPDATA%\ATR Game；Linux：~/.config/ATR Game
	出牌记录：同上目录下的 logs/guandan/*.txt，整场结束自动保存
	象棋棋谱：同上目录下的 logs/chess/*.txt，将死 / 逼和 / 对手离场判胜后
		自动保存，中途退出也会留一份（标「中途结束」）
	五子棋棋谱：同上目录下的 logs/gomoku/*.txt，分出胜负或中途退出时保存
	俄罗斯方块成绩：同上目录下的 logs/tetris/*.txt，方块堆到顶（游戏结束）
		时保存分数 / 等级 / 消行数
	游玩记录（主页第三扇门）把上述 logs/ 下**所有游戏**的记录汇总显示，
		还能按游戏筛选；各游戏子菜单里的「历史记录」只看自己那一份

7. 分发构建（apk / app / ipa）
	一键脚本：./build_dist.sh apk | app | ipa | all，产物统一放在 dist/
	等价手动命令：
		./.venv/bin/python -c "import sys;sys.argv[0]='flet';from flet.cli import main;main()" \
			build apk --yes
	各平台还差什么（本机 2026-10-17 实测）：
		apk / aab：flet 会自动装 Flutter + JDK17 + AndroidSDK，
			但 GitHub 在国内不通，JDK 要先走镜像放好：
				curl -o /tmp/jdk.tar.gz "https://mirrors.huaweicloud.com/adoptium/17/jdk/aarch64/macOS/OpenJDK17U-jdk_aarch64_mac_hotspot_17.0.13_11.tar.gz"
				mkdir -p ~/java/17.0.13+11 && tar -xzf /tmp/jdk.tar.gz -C ~/java/17.0.13+11 --strip-components=1
				export JAVA_HOME=~/java/17.0.13+11/Contents/Home
			Flutter 也可预先装好（flet 发现 ~/flutter/3.41.7 存在就跳过下载），
				国内用 storage.flutter-io.cn 镜像，比 Google CDK 快二十多倍；
				注意 Flutter arm64 压缩包有 2.15 GB，磁盘要留够
		app：还需要**完整 Xcode**（App Store 安装，约 10GB）；
			本机只有 Command Line Tools，打不出 .app
		ipa：还需要 Xcode + CocoaPods + Apple 开发者账号签名
			（--ios-team-id / --ios-export-method / 证书；没有账号只能出未签名包，
			 未签名 ipa 装不到非越狱设备上）
	资源与图标约定（改代码前先读）：
		牌图在项目根 assets/cards/，代码里用**相对 assets 根**的路径
			（如 "cards/10 of hearts.png"），不要加 assets/ 前缀
		应用图标是 assets/icon.png（1024×1024），flet build 靠它自动生成
			各平台图标；assets/Songs 是个人音乐，已在 pyproject 的 exclude
			里排除，不会进安装包

8. 代码结构
	app.py				应用入口（注册路由、配置 Page）
	（逐文件的详细作用见 CODE_INDEX.md —— 代码地图）
	main.py				兼容壳（让 IDE 直接运行）
	core/				框架层（不依赖具体游戏）
		registry.py		游戏插件注册表
		router.py		路由
		theme.py		配色 / 尺寸
		ui_common.py	通用组件
		settings.py	用户设置持久化（跨平台配置目录）
		window.py		窗口模式（全屏 / 最大化 / 窗口）
		history.py		比赛记录落盘（跨平台数据目录）
		history_view.py	通用历史记录页（掼蛋 / 象棋 共用的界面与交互）
		profile.py		本机档案：昵称（没起过就随机）+ 上次房间码
		net/			局域网联机（0.4.7 新增）
			__init__.py	消息协议 / JSON 编解码 / 房间码加盐校验
			discovery.py	UDP 广播：房主喊人、扫描器收人
			session.py	房间会话主体：建房/加入/席位/聊天/玩法透传
			member.py	房间里「一个人」的数据结构
			session_const.py	心跳/重传/超时的时间参数
			session_reliable.py	可靠传输：收发、ACK、重传、心跳
			session_messaging.py	各类包的处理：握手/席位表/聊天/开始
			session_game.py	玩法消息透传（象棋走子、掼蛋出牌…）
			voice.py		语音：可选依赖（sounddevice），缺失自动降级
			selftest.py	逻辑自检入口：python -m games.guandan.selftest
			selftest_common.py	自检公共小工具
			selftest_cards.py	自检：牌与牌型
			selftest_engine.py	自检：对局引擎
			selftest_tribute.py	自检：进贡 / 还贡
		ui_packs/		界面皮肤包（0.4.7-fix1 新增，可插拔）
			base.py		包契约：颜色令牌 + 零件工厂签名 + 语气翻译
			material.py	默认包（材料风，跟随明暗主题）
			rustic.py		暗黑2 / MC 石砖风（斜面描边、暗金、火把线）
			registry.py	包注册表：内置两套，社区包 register 即出现
		ui_theme.py	界面风格总控：当前包分发、切换、覆写 theme.T 全局换色
		views/			核心视图（主菜单 / 单人 / 多人 / 房间 / 我的 / 设置 / 游玩记录）
			room_view.py	房间大厅骨架（进房/选游戏/开始/离开/轮询）
			room_widgets.py	房间大厅零件（席位 / 语音 / 聊天）
			multiplayer_view.py	多人页：创建房间 / 搜索房间
			history_view.py	游玩记录页（汇总所有游戏 + 按游戏筛选）
	games/				游戏插件
		guandan/		掼蛋
			analyzer.py	记牌算法（与 0.3 等价）
			cards.py	模拟器牌面模型（Card、108张牌堆、级牌感知排序）
			rules.py	牌型枚举（能打出的牌型）+ 门面再导出
			rules_base.py	牌型枚举与数据结构
			rules_parse.py	牌型识别（就高解释）
			rules_compare.py	牌型大小比较
			engine.py	对局引擎门面（再导出下面四个模块）
			state.py	对局常量与数据结构（MatchState 等）
			hand.py	一手牌状态机（出牌/跟牌/过牌/接风）
			settle.py	升级结算 + 进贡安排
			serialize.py	联机用 JSON 序列化 / 还原
			tribute.py	进贡 / 还贡状态机（抗贡、双下、选贡）
			ai.py		贪心 AI（自对弈 + 进贡自动决策）
			simulator.py	headless 自对弈：python -m games.guandan.simulator
			selftest.py	逻辑自检：python -m games.guandan.selftest
			plugin.py	插件声明
			views/		视图（牌桌 / 历史 / 记牌 / AI建议 / 全模拟 / 牌型速查）
				play_view.py	牌桌组装 + play_const/table/actions/ai/net/flow
				board_view.py	快速记牌页（+ board_widgets.py 牌面按钮）
				simulator_view.py	全模拟观战页（+ sim_session.py / sim_const.py）
		splendor/		占位（仅插件框架）
		chess/			国际象棋（0.4.8 落地为可玩游戏）
			engine.py	棋局引擎：走法 / 王车易位 / 吃过路兵 / 升变 /
					将军·将死·逼和 / 悔棋 / serialize·load_state
			assets.py	15 套棋子皮肤 + piece_image_src()
			views.py		棋盘 UI 组装（本地双人 + 房间联网对弈）
			views_board.py	棋盘画面 / 走子 / 升变
			views_sync.py	联机身份与局面同步
			views_record.py	棋谱记录与落盘
			history_view.py	历史记录页（委托 core/history_view）
			plugin.py	插件声明（players=2，路由 /g/chess、/g/chess/play、
					/g/chess/history）
			selftest.py	引擎自检：python -m games.chess.selftest
		chinese_chess/	占位（仅插件框架）
		gomoku/		五子棋（0.4.9 落地为可玩游戏）
			engine.py	棋局引擎：15 路棋盘 / 落子 / 五连判胜 / 悔棋 /
					平局判定 / 序列化（联机快照）
			views.py		子菜单（本地对局 / 历史记录 / 规则说明）
			views_board.py	棋盘画面（棋子落在**线的交汇点**上）/ 落子 /
					悔棋 / 重开 / 联机同步 / 落盘
			history_view.py	历史记录页（委托 core/history_view）
			plugin.py	插件声明（players=2，路由 /g/gomoku、/g/gomoku/play、
					/g/gomoku/history）
			selftest.py	引擎自检：python -m games.gomoku.selftest
		tetris/		俄罗斯方块（0.4.9 落地为可玩游戏）
			engine.py	引擎：七种方块 / 移动 / 旋转 / 消行 / 计分 /
					等级 / Hold / 幽灵块 / 序列化
			views.py		子菜单（开始游戏 / 历史记录 / 操作说明）
			views_play.py	对局画面 + 键盘输入 + 重力循环 + 落盘
			history_view.py	历史记录页（委托 core/history_view）
			plugin.py	插件声明（players=1，online=False 不进多人房间）
			selftest.py	引擎自检：python -m games.tetris.selftest

8. 模拟器进度（0.4.1）
	底层逻辑已完成并实测（多场自对弈全部正常收尾）
	已实现：进贡 / 还贡 / 抗贡 / 双下 / 选贡
	暂未实现：观战 UI 接入进贡

9. 局域网联机（0.4.7，0.4.8 新增 Chess 联网对弈）
	怎么用（两台电脑在同一个 WiFi 下）：
		① 房主：主页 → 多人游戏 → 建立房间（填房间名 / 房间码 / 游戏 / 席位）
		② 伙伴：主页 → 多人游戏 → 搜索房间 → 找到房间 → 输入房间码 → 进入
		③ 房间里：点空位坐下、开麦克风说话、聊天框打字；房主点「开始」
	不用记 IP、不用服务器：房间靠 UDP 广播把自己告诉大家（端口 45663），
		席位/聊天走 UDP 单播，语音点对点直连（不经第三方）
	房间码会存在本地，下次建房间自动带上；只知道房间名也进不来，还得有房间码
	语音是**可选**功能：依赖 sounddevice + numpy；没装的话按钮提示未安装，
		其余功能不受影响（手机端打包用不上，也就不会绑死 PortAudio）
	不偷偷录音：进房间只开端口，点「开麦克风」才拉起采集设备
	联机自检（不用两台电脑）：./venv/bin/python3 -m core.net.selftest
	选「国际象棋」后进对局（0.4.8 新增）：两人各坐一个席位即分别为白方 / 黑方，
		其余席位与未入座的人自动观战；走子 / 悔棋 / 重开实时同步，迟到进来的人
		会自动追平当前局面。中途有人离开：在场的一方直接判胜（显示「对方离开，
		X 方获胜！」），观战方则提示「白方/黑方已离开」
	已知边界：打通的是「发现 + 席位 + 语音 + 聊天 + Chess 走子同步」；把四个人
		塞进同一局掼蛋的多人同步仍留到后续版本

10. 界面风格（0.4.7-fix1）
	两套内置皮：**默认（材料）** 与 **暗黑2 / MC（石砖）**，设置页 →
		「界面风格」里切换，整个应用（含掼蛋牌桌）当场换皮、不用重启
	换皮原理：界面包自带颜色令牌，切换时把令牌覆写到 core/theme.py 的 T 上，
		所有用 T 取色的界面自动跟上；核心视图则直接用包的零件工厂
	深色主题开关只对默认皮有意义（石砖皮本身就是暗色）
	想加第三套皮：在 core/ui_packs/ 里加一个模块，继承 base.BasePack、
	实现同名零件工厂、末尾 register(YourPack())，设置页立刻多一项
	（PackMeta.builtin=False 表示社区包，会排在内置包后面）

11. flet 布局的两个坑（0.4.7-fix1 踩过，改代码前先看）
	① Dropdown 不要放进 expand 的 Column：选项浮层会被拉成一块盖住
		半个屏幕的灰色矩形。要选就用的石砖按钮组（ui.chip）或把 Column
		的 expand 去掉
	② wrap=True 的 Row 里不要放 expand 占位 / expand 输入框：剩余空间会被
		当成独立一行撑成灰墙。左右分开用 MainAxisAlignment.SPACE_BETWEEN，
		输入框和按钮分两行放
	③ 可滚动的 Column 里不要放 expand 占位（会把后面的内容顶出屏幕）；
		输入框自身也别 expand（在 Column 里会被拉高，多出一块空白）
