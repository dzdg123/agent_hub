"""无需可选模型依赖的向量比较函数。"""

from __future__ import annotations

import math


def cosine(a: list[float], b: list[float]) -> float:
    if not a or len(a) != len(b):
        raise ValueError("向量不能为空且维度必须一致")
    if not all(math.isfinite(value) for value in (*a, *b)):
        raise ValueError("向量分量必须是有限数值")
    na, nb = math.hypot(*a), math.hypot(*b)
    if na == 0 or nb == 0:
        raise ValueError("零向量不能计算余弦相似度")
    if not math.isfinite(na) or not math.isfinite(nb):
        raise ValueError("向量范数超出可表示范围")
    # 先归一化再相乘，避免直接计算平方或点积造成中间值溢出。
    return math.fsum((x / na) * (y / nb) for x, y in zip(a, b))
