# -*- coding: utf-8 -*-
"""国际化（i18n）：语言登记、切换、取文案。

怎么用
------
视图里不再写死中文：::

    from core.i18n import t
    ui.text(t("menu.single"), 22)

带参数的文案用 ``{name}`` 占位，按关键字填：::

    t("mp.your_nick", nick=nick)

缺键怎么办
----------
查表顺序是「当前语言 → 中文母本 → 调用处给的 default → key 本身」。
所以一门新语言翻一半也没事：没翻到的地方自动说中文，不会满屏 key，
也不会因为某个键漏翻就崩掉界面 —— 增量翻译是安全的。

切换语言后要做什么
------------------
``set_lang()`` 只改当前语言。所有视图都是**按老语言建出来的**，
所以要 :func:`refresh` 一次：清掉全部路由缓存 → 重建当前页。
这件事跟换皮（:func:`core.ui_theme.refresh`）是同一个套路。

自检
----
``./venv/bin/python3 -m core.i18n`` 会跑 :func:`audit`，
报告各语言缺哪些键、哪些占位符对不上。
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from core import settings as settings_mod
from core.locales import en_US, zh_CN

# 母本：任何键都必须存在于此，其它语言以此为准回退。
DEFAULT_LANG = "zh_CN"

# 语言表：代号 → 文案字典。新增语言时在这里登记一份。
_TABLES: Dict[str, Dict[str, str]] = {
    "zh_CN": zh_CN.STRINGS,
    "en_US": en_US.STRINGS,
}

# 语言清单（顺序即设置页里的展示顺序）：
# (代号, 语言自己的名字, 备注) —— 名字用语言自己的写法，不翻译。
_LANGUAGES: List[Tuple[str, str, str]] = [
    ("zh_CN", "简体中文", "默认"),
    ("en_US", "English", ""),
]

_CURRENT: Optional[str] = None


# ------------------------------------------------------------------
# 查询
# ------------------------------------------------------------------

def languages() -> List[Tuple[str, str, str]]:
    """已登记的语言：``[(代号, 名字, 备注), …]``，设置页按这个列出。"""
    return list(_LANGUAGES)


def language_name(code: Optional[str] = None) -> str:
    """语言的显示名（用它自己的写法，如 ``English``）。"""
    code = code or current()
    for cid, name, _note in _LANGUAGES:
        if cid == code:
            return name
    return code or ""


def normalize(code: Optional[str]) -> str:
    """容错：没登记过的语言一律回落到母本。"""
    if code in _TABLES:
        return str(code)
    return DEFAULT_LANG


def current() -> str:
    """当前语言代号（第一次调用时读 settings.json）。"""
    global _CURRENT
    if _CURRENT is None:
        try:
            _CURRENT = normalize(settings_mod.Settings.load().language)
        except Exception:                       # noqa: BLE001 — 设置坏了也要能跑
            _CURRENT = DEFAULT_LANG
    return _CURRENT or DEFAULT_LANG


def ensure_loaded() -> str:
    """启动时调用一次：按设置把语言穿上（app.run 里用）。"""
    return current()


# ------------------------------------------------------------------
# 取文案
# ------------------------------------------------------------------

def t(key: str, *, default: str = "", **kwargs) -> str:
    """取一条文案并填占位符。

    Args:
        key: 文案键，如 ``"menu.single"``。
        default: 表里都没有时的兜底（一般写中文原文，保证界面不空）。
        **kwargs: ``{name}`` 占位符的值。

    Returns:
        当前语言的文案；找不到就依次退回中文母本 / ``default`` / ``key``。
    """
    table = _TABLES.get(current()) or {}
    text = table.get(key)
    if text is None:                            # 没翻 → 说母本的话
        text = _TABLES.get(DEFAULT_LANG, {}).get(key)
    if text is None:
        text = default or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text                         # 占位符对不上就原样出，别崩
    return text


def has(key: str, code: Optional[str] = None) -> bool:
    """该语言里有没有这条键（不含母本回退）。"""
    return key in (_TABLES.get(code or current()) or {})


# ------------------------------------------------------------------
# 切换
# ------------------------------------------------------------------

def set_lang(code: str, *, persist: bool = True) -> bool:
    """切换语言；返回是否是已登记的语言。

    * 同步改 ``current()``（下一次 ``t()`` 立刻说新语言）；
    * 按需写回 settings.json（下次启动还是这门语言）。

    界面上已有的控件不会自己变，切换后请再调一次 :func:`refresh`。
    """
    global _CURRENT
    if code not in _TABLES:
        return False
    _CURRENT = code
    if persist:
        try:
            data = settings_mod.Settings.load()
            data.language = code
            data.save()
        except Exception:                       # noqa: BLE001
            pass
    return True


def refresh(page=None, navigate: Optional[Callable[[str], None]] = None) -> None:
    """让界面立刻换成新语言：丢掉所有路由缓存，重建当前页。

    跟换皮一样，缺了这一步看到的还是按老语言建出来的控件树。
    """
    from core.registry import all_routes
    from core.router import Router

    router = Router.current
    path = router.current_path() if router is not None else "/"
    if router is not None:
        for spec in all_routes():
            router.invalidate(spec.path)
        router.invalidate(None)                 # 兜底：清整个缓存
    if navigate is not None:
        navigate(path or "/")


# ------------------------------------------------------------------
# 自检
# ------------------------------------------------------------------

def audit() -> List[str]:
    """检查语言表；返回问题列表（空列表 = 都好）。

    查三件事：
    1. 各语言有没有**多出来**的键（母本里没有 → 多半是拼错或改名了）；
    2. 各语言**缺**哪些键（缺的会自动说中文，列出来供补翻）；
    3. 占位符 ``{name}`` 跟母本对不对得上。
    """
    import re

    base = _TABLES.get(DEFAULT_LANG) or {}
    issues: List[str] = []
    for code, table in _TABLES.items():
        if code == DEFAULT_LANG:
            continue
        extra = sorted(set(table) - set(base))
        missing = sorted(set(base) - set(table))
        for key in extra:
            issues.append(f"[{code}] 多出来的键（母本没有）：{key}")
        for key in missing:
            issues.append(f"[{code}] 缺键（会退回中文）：{key}")
        for key, text in sorted(table.items()):
            if key not in base:
                continue
            want = set(re.findall(r"\{(\w+)\}", base[key]))
            got = set(re.findall(r"\{(\w+)\}", text))
            if want != got:
                issues.append(
                    f"[{code}] 占位符不一致：{key} 需要 {sorted(want)}，"
                    f"实际 {sorted(got)}")
    return issues


def _main() -> int:
    issues = audit()
    print(f"语言：{len(_TABLES)} 门（当前 {current()}），母本 {DEFAULT_LANG} "
          f"共 {len(_TABLES.get(DEFAULT_LANG, {}))} 条")
    if not issues:
        print("自检通过：没有缺键 / 多余键 / 占位符不一致")
        return 0
    for line in issues:
        print(" - " + line)
    return 1


if __name__ == "__main__":
    raise SystemExit(_main())
