/* ATR Game 0.5 — 中八本地双人 HUD。
 * Chinese8Ball 规则把 1P/2P 球组、当前击球者写到 globalThis.__atrHotseat；
 * 这里只负责显示，不参与任何规则判定。
 */
(function () {
  'use strict';

  function label(group) {
    if (group === 1) return '全色 1-7';
    if (group === 2) return '花色 9-15';
    return '未定组';
  }

  function render() {
    var state = globalThis.__atrHotseat;
    var box = document.getElementById('atrHotseatHud');
    if (!state) {
      if (box) box.style.display = 'none';
      setTimeout(render, 300);
      return;
    }
    if (!box) {
      box = document.createElement('div');
      box.id = 'atrHotseatHud';
      document.body.appendChild(box);
    }
    box.style.display = 'block';
    var g = state.groups || [0, 0];
    var active = state.active || 1;
    var s = state.scores || [0, 0];
    box.textContent =
      '1P ' + label(g[0]) + ' (' + (s[0] || 0) + ')' +
      '   |   2P ' + label(g[1]) + ' (' + (s[1] || 0) + ')' +
      '   |   当前 ' + active + 'P';
    setTimeout(render, 200);
  }

  document.addEventListener('DOMContentLoaded', render);
  setTimeout(render, 200);
})();
