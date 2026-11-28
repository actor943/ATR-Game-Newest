/* ATR Game 0.5 — 3D 台球界面中文层。
 *
 * 上游 billiards 网页的静态文案是英文，运行时 i18n 只带繁体中文而且没有
 * 可见切换入口。本文件不改上游构建产物，只在本地页面加载后：
 *   1. 默认把可见文案（含 title / aria-label 提示）换成简体中文；
 *   2. 在右上角放一个「中 / EN」按钮，游戏内点一下即可切换；
 *   3. 用 MutationObserver 跟进 JS 动态生成的提示（YOU WON / FOUL 等）。
 *
 * 语言选择存 localStorage，默认 zh；URL 上的 ?lang= 优先，方便外部指定。
 */
(function () {
  'use strict';

  var DICT = {
    // 静态页面 / 帮助面板
    'Play': '开始游戏',
    '8-ball': '八球',
    '9-ball': '九球',
    '3-cushion': '三颗星',
    'Snooker': '斯诺克',
    'Sagu': '萨古',
    'Libre': '自由球',
    'Eat': '挑战',
    'Map': '地图',
    'Reveal': '揭晓',
    'Lobby': '大厅',
    'Controls': '操作说明',
    'Fine Aim': '精细瞄准',
    'Fine aim': '精细瞄准',
    'near top = precise adjustment': '靠近顶部＝精细微调',
    'ZOOM': '缩放',
    'Coarse Aim': '粗略瞄准',
    'near bottom = faster turning': '靠近底部＝快速转动',
    'Shot power': '击球力度',
    'Hit': '击球',
    'Draw lines': '绘制辅助线',
    'Topspin & backspin': '高杆与低杆',
    'Side spin': '左右塞',
    'Hit, hold for power': '击球，长按蓄力',
    'Masse angle': '扎杆角度',
    'Camera view': '切换视角',
    'Full screen': '全屏',
    'Chat': '聊天',
    'Help': '帮助',
    'Chromeless, drag cue': '无边框模式，拖动球杆',
    'About': '关于',
    'Free Online Pool, Snooker & Billiards Game': '免费在线台球、斯诺克与撞球游戏',
    'Multiplayer Lobby': '多人游戏大厅',
    'Accept challenge': '接受挑战',
    'Decline challenge': '拒绝挑战',
    'Table minimap': '球桌小地图',
    // 按钮 title / aria-label
    'concede': '认输',
    'Concede': '认输',
    'shot analysis': '击球分析',
    'chromeless (L)': '无边框（L）',
    'view': '视角',
    'Toggle camera view': '切换视角',
    'Toggle chromeless mode': '切换无边框模式',
    // 网页运行时 i18n 的简体对应（上游只带繁体）
    'Place\nBall': '放置母球',
    'Place Ball': '放置母球',
    'Back to Lobby': '返回大厅',
    'Back to Arena': '返回赛场',
    'Uploading result…': '正在上传结果…',
    'New Game': '新对局',
    'Replay': '回放',
    'Rematch': '再战',
    'Ball in hand': '自由球',
    'You first': '你先手',
    'FOUL': '犯规',
    '8-ball pocketed before clearing group': '未清台先打进 8 号球，判负',
    'YOU WON': '你赢了',
    'YOU LOST': '你输了',
    'GAME OVER': '比赛结束',
    'Concede Game': '认输',
    'Replay Complete': '回放结束',
    'Waiting for opponent to join': '等待对手加入',
    'Play on': '继续比赛',
    'Declare win': '宣告胜利',
    'Continue break': '继续进攻',
    'Update Deck': '更换牌组',
    'Share replay link': '分享回放链接',
    'share': '分享',
    'upload': '上传',
    'left english': '左塞',
    'right english': '右塞',
    'follow': '跟杆',
    'draw': '缩杆',
    'Online:': '在线：'
  };

  // 带数字 / 人名的动态提示不能用精确 key，走正则替换。
  var PATTERNS = [
    [/^Race to:\s*(\d+)$/i, function (m) { return '抢 ' + m[1] + ' 分'; }],
    [/^Break\s*:\s*(\d+)$/i, function (m) { return '单杆：' + m[1]; }],
    [/^Open high break\s+(\d+)$/i, function (m) { return '查看最高单杆 ' + m[1]; }],
    [/^CHALLENGE FROM\s+(.+)$/i, function (m) { return '来自 ' + m[1] + ' 的挑战'; }],
    [/^Online:\s*([\s\S]+)$/i, function (m) { return '在线：' + m[1]; }],
    // 上游 help 按钮的 title 是三国语换行串，整体归并为「帮助」
    [/^help[\s\S]*$/i, function () { return '帮助'; }]
  ];

  var ATTRS = ['title', 'aria-label', 'placeholder', 'alt'];
  var SKIP_TAGS = { SCRIPT: 1, STYLE: 1, NOSCRIPT: 1, TEXTAREA: 1 };
  var STORAGE_KEY = 'atr_billiards3d_lang';

  var originalText = new Map();
  var appliedText = new Map();
  var originalAttr = new Map();
  var appliedAttr = new Map();
  var lang = 'zh';
  var busy = false;
  var pending = false;

  function readLang() {
    var fromUrl = null;
    try {
      fromUrl = new URLSearchParams(location.search).get('lang');
    } catch (e) {}
    if (fromUrl === 'zh' || fromUrl === 'en') return fromUrl;
    var saved = null;
    try {
      saved = localStorage.getItem(STORAGE_KEY);
    } catch (e) {}
    return saved === 'en' ? 'en' : 'zh';   // 默认中文
  }

  function lookup(raw) {
    if (!raw) return null;
    var key = raw.trim();
    if (!key) return null;
    if (DICT[key]) return DICT[key];
    for (var i = 0; i < PATTERNS.length; i++) {
      var m = key.match(PATTERNS[i][0]);
      if (m) return PATTERNS[i][1](m);
    }
    return null;
  }

  function translateText(node) {
    if (node.nodeType !== 3) return;
    var parent = node.parentElement;
    if (!parent || SKIP_TAGS[parent.tagName] || parent.id === 'atrLangToggle') return;
    var cur = node.nodeValue;
    if (!cur || !cur.trim()) return;

    if (lang === 'en') {
      var orig = originalText.get(node);
      if (orig !== undefined && appliedText.get(node) === cur) {
        node.nodeValue = orig;
        appliedText.delete(node);
        originalText.delete(node);
      }
      return;
    }
    if (appliedText.get(node) === cur) return;    // 已经翻过，别被自己触发的 observer 再翻
    var translated = lookup(cur);
    if (!translated) return;
    var lead = (cur.match(/^\s*/) || [''])[0];
    var tail = (cur.match(/\s*$/) || [''])[0];
    var next = lead + translated + tail;
    if (next === cur) return;
    originalText.set(node, cur);
    node.nodeValue = next;
    appliedText.set(node, next);
  }

  function translateAttrs(el) {
    if (!el || !el.getAttribute || el.id === 'atrLangToggle') return;
    for (var i = 0; i < ATTRS.length; i++) {
      var attr = ATTRS[i];
      var cur = el.getAttribute(attr);
      if (!cur) continue;
      var origMap = originalAttr.get(el);
      var appMap = appliedAttr.get(el);

      if (lang === 'en') {
        if (origMap && appMap && appMap.get(attr) === cur) {
          el.setAttribute(attr, origMap.get(attr));
          appMap.delete(attr);
        }
        continue;
      }
      if (appMap && appMap.get(attr) === cur) continue;
      var translated = lookup(cur);
      if (!translated || translated === cur) continue;
      if (!origMap) {
        origMap = new Map();
        originalAttr.set(el, origMap);
      }
      if (!appMap) {
        appMap = new Map();
        appliedAttr.set(el, appMap);
      }
      if (!origMap.has(attr)) origMap.set(attr, cur);
      el.setAttribute(attr, translated);
      appMap.set(attr, translated);
    }
  }

  function apply(root) {
    var scope = root || document.body;
    if (!scope) return;
    busy = true;
    try {
      var walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT, null, false);
      var node;
      while ((node = walker.nextNode())) {
        translateText(node);
      }
      var elements = scope.querySelectorAll('*');
      for (var i = 0; i < elements.length; i++) {
        translateAttrs(elements[i]);
      }
      document.documentElement.lang = lang === 'zh' ? 'zh-Hans' : 'en';
      updateButton();
    } finally {
      busy = false;
    }
  }

  function updateButton() {
    var btn = document.getElementById('atrLangToggle');
    if (!btn) return;
    var label = lang === 'zh' ? 'EN' : '中文';
    if (btn.textContent !== label) btn.textContent = label;
    var tip = lang === 'zh' ? 'Switch to English' : '切换到中文';
    if (btn.getAttribute('title') !== tip) btn.setAttribute('title', tip);
  }

  function setLang(next) {
    lang = next === 'en' ? 'en' : 'zh';
    try {
      localStorage.setItem(STORAGE_KEY, lang);
    } catch (e) {}
    try {
      var url = new URL(location.href);
      url.searchParams.set('lang', lang);
      history.replaceState(null, '', url.toString());
    } catch (e) {}
    apply(document.body);
  }

  function addButton() {
    if (document.getElementById('atrLangToggle')) return;
    var btn = document.createElement('button');
    btn.id = 'atrLangToggle';
    btn.type = 'button';
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      setLang(lang === 'zh' ? 'en' : 'zh');
    });
    (document.body || document.documentElement).appendChild(btn);
  }

  function start() {
    lang = readLang();
    addButton();
    apply(document.body);
    var observer = new MutationObserver(function () {
      if (busy || pending) return;
      pending = true;
      setTimeout(function () {
        pending = false;
        apply(document.body);
      }, 60);
    });
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ATTRS
    });
  }

  window.ATR3D = {
    setLang: setLang,
    currentLang: function () { return lang; }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
