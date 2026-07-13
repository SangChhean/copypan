# -*- coding: utf-8 -*-
"""自测：生命读经原文查询。"""
from back_cn.roundtable.life_text_service import get_message, get_messages

# 单篇测试
m = get_message(1, 1)
print(m["book_name"], "|", m["title"], "| 段落数:", len(m["paragraphs"]))
print(m["full_text"][:100])

# 之前确认过的以弗所书第61篇
m2 = get_message(49, 61)
print(m2["book_name"], "|", m2["title"], "| 段落数:", len(m2["paragraphs"]))

# 多篇测试（2篇连续）
ms = get_messages(1, [1, 2])
print("多篇测试，共", len(ms), "篇")

# 异常测试：不存在的卷
try:
    get_message(999, 1)
except FileNotFoundError as e:
    print("预期异常（不存在的卷）:", e)

# 异常测试：不存在的篇号
try:
    get_message(1, 9999)
except ValueError as e:
    print("预期异常（不存在的篇）:", e)
