# -*- coding: utf-8 -*-
"""台球贴图资源。

路径约定和掼蛋、国际象棋一致：**相对于 assets 目录根**，不带 ``assets/``
前缀（``flet build`` 打包后同样按这个规则解析，见 flet 文档 Assets）。

贴图尺寸（量自 PNG 本体）
--------------------------
* ``table.png`` 1200×678 —— 整张球桌（含木质库边）；绿色台面区在
  ``(56, 56) - (1143, 621)``，也就是 1087×565。
* ``ball_1.png`` ~ ``ball_15.png`` —— 1~15 号球，36×36。
* ``ball_16.png`` —— 白球，36×36。
* ``cue.png`` —— 球杆（备用）。

物理坐标与贴图坐标
------------------
物理用的台面坐标（左上角为原点，单位像素）**只覆盖绿色台面区**；
贴图比台面大一圈（木头库边 + 袋口），所以 :mod:`games.billiards.views_table`
会把整张贴图按比例缩放后往左上角挪 ``(56, 56)``，让绿色区和物理坐标
严丝合缝 —— 这样「球进袋」和「球看着掉进袋里」是同一件事。
"""

from __future__ import annotations

BILLIARDS_SUBDIR = "billiards"

TABLE_IMAGE = "billiards/table.png"
BALL_IMAGE = "billiards/ball_{0}.png"
CUE_BALL_IMAGE = "billiards/ball_16.png"
CUE_STICK_IMAGE = "billiards/cue.png"

# 整张球桌贴图的像素尺寸
TABLE_IMAGE_SIZE = (1200.0, 678.0)
# 绿色台面区在贴图里的位置（左上角 x/y + 宽/高）
TABLE_GREEN = (56.0, 56.0, 1087.0, 565.0)
# 球贴图边长（像素）
BALL_IMAGE_SIZE = 36.0


def ball_image_src(number: int) -> str:
    """球号 → 贴图路径（0 号白球用 ``ball_16.png``）。"""
    if number <= 0:
        return CUE_BALL_IMAGE
    return BALL_IMAGE.format(number)
