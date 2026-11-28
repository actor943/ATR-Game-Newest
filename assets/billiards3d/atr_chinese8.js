/* ATR Game 0.5 — 中八（中式八球）规则补丁。
 *
 * 上游 billiards 只有美式八球：提前打进 8 号球时会把 8 号球摆回台面并判犯规。
 * 中式八球的常见规则是：**未清完本组球就打进 8 号球直接判负**。
 *
 * 这里不重编译上游 TS：页面加载完成后拿到暴露的 window.container.rules，
 * 包装它的 update()。只在 URL 带 ?chinese8 时生效，其它模式完全不动。
 *
 * 注意：仍不含「指球定袋」——上游 Outcome 没有记录落袋袋口，完整指袋需要
 * 修改 TS 模型、UI 和网络事件后重新构建 bundle。
 */
(function () {
  'use strict';

  function isChinese8() {
    try {
      return new URLSearchParams(location.search).has('chinese8');
    } catch (e) {
      return false;
    }
  }

  function eightPotted(outcome) {
    if (!Array.isArray(outcome)) return false;
    return outcome.some(function (o) {
      return o && o.type === 'Pot' && o.ballA && o.ballA.label === 8;
    });
  }

  function patch(rules) {
    if (!rules || rules.__atrChinese8) return;
    rules.__atrChinese8 = true;

    var original = rules.update;
    if (typeof original !== 'function') return;

    rules.update = function (outcome) {
      if (isChinese8() && eightPotted(outcome)) {
        var won = false;
        try {
          won = !!rules.isEndOfGame(outcome);
        } catch (e) {}
        if (!won && typeof rules.handleGameEnd === 'function') {
          return rules.handleGameEnd(
            false,
            '8-ball pocketed before clearing group'
          );
        }
      }
      return original.call(rules, outcome);
    };
  }

  function waitForRules(tries) {
    var container = globalThis.container;
    if (container && container.rules) {
      patch(container.rules);
      return;
    }
    if ((tries || 0) < 200) {
      setTimeout(function () { waitForRules((tries || 0) + 1); }, 100);
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    waitForRules(0);
  });
  setTimeout(function () { waitForRules(0); }, 200);
})();
