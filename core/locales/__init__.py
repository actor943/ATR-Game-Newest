# -*- coding: utf-8 -*-
"""语言包（文案表）。

每个语言一个模块，模块内导出 ``STRINGS: dict[str, str]``（键 → 该语言文案）。
``zh_CN`` 是**母本**：新加的键必须先落在这里，其它语言翻多少算多少
（见 :mod:`core.i18n` 的缺键回退规则）。

新增一门语言的步骤
------------------
1. 复制 ``zh_CN.py`` 成 ``<代号>.py``，把值翻成目标语言（键保持不动）；
2. 在 :mod:`core.i18n` 的 ``_TABLES`` 与 ``_LANGUAGES`` 里登记；
3. 跑 ``./venv/bin/python3 -m core.i18n`` 看缺哪些键。
"""

from . import en_US, zh_CN  # noqa: F401

__all__ = ["zh_CN", "en_US"]
