# -*- coding: utf-8 -*-
"""掼蛋底层逻辑自检：规则单元用例 + 自对弈不变量。

用法::

    ./venv/bin/python3 -m games.guandan.selftest

全部用例按主题拆到几个文件里了，本文件只负责**汇总与汇报**：

* games.guandan.selftest_common  —— 公共小工具（造牌、固定级牌背景）
* games.guandan.selftest_cards   —— 牌堆 / 大小顺序 / 牌型识别 / 逢人配
* games.guandan.selftest_engine  —— 动作守卫 / 级牌归属 / 自对弈不变量
* games.guandan.selftest_tribute —— 进贡 / 还贡 / 抗贡 / 双下 / 选贡

任何一个用例失败都会直接抛出 AssertionError（退出码非 0）。
"""

from __future__ import annotations

from .selftest_cards import (
    test_cards,
    test_parse_basic,
    test_parse_bombs_and_runs,
)
from .selftest_engine import (
    test_engine_guards,
    test_level_ownership,
    test_level_rank_follows_winner,
    test_simulation,
)
from .selftest_tribute import (
    test_tribute_auto_and_engine_hook,
    test_tribute_choose_gift,
    test_tribute_double_down,
    test_tribute_first_leader,
    test_tribute_normal,
    test_tribute_refuse,
    test_tribute_refuse_shared_jokers,
)



def main():
    """依次跑完全部用例；任何一条失败都会抛 AssertionError 中断。"""
    for test in (test_cards, test_parse_basic, test_parse_bombs_and_runs,
                 test_engine_guards, test_level_ownership,
                 test_level_rank_follows_winner,
                 test_tribute_normal, test_tribute_refuse,
                 test_tribute_refuse_shared_jokers, test_tribute_first_leader,
                 test_tribute_double_down, test_tribute_choose_gift,
                 test_tribute_auto_and_engine_hook, test_simulation):
        name = test.__name__
        try:
            test()
            print(f"PASS {name}")
        except AssertionError as exc:
            print(f"FAIL {name}: {exc}")
            raise
    print("ALL OK")


if __name__ == "__main__":
    main()
