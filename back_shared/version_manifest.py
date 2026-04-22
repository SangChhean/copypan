# -*- coding: utf-8 -*-
"""
版本常量集中管理。
所有影响缓存 key 与行为的版本字段统一在此维护。
任何变更只改这一个文件，旧缓存自动失效。
"""

PROMPT_VERSION = "v1.0"
# Prompt 有实质改动时手动递增

FIREWALL_RULES_VERSION = "v1.0"
# firewall_rules.json 更新时递增

MODEL_PROFILE = "sonnet-4-6"
# Step 4 生成模型标识，模型切换时更新
