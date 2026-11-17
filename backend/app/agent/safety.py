"""越界请求识别：命中即拒绝，不进入模型与工具调用。

只覆盖明确高风险/违规的表达，避免误伤「预算不够怎么办」这类正常咨询。
"""

from __future__ import annotations

import re

# (正则, 命中原因)
_VIOLATION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"套现|提现额度|刷出来", "套现"),
    (r"(绕过|规避|突破|躲开).{0,8}(额度|限额|风控|监管|征信)", "规避金融限制"),
    (r"(伪造|虚构|做假|P图|ps).{0,8}(流水|小票|发票|账单|消费记录)", "伪造凭证"),
    (r"(洗钱|跑分|刷单|代开发票|买卖发票)", "违法资金操作"),
    (r"(贷款口子|高利贷|裸贷|帮我借钱|帮我贷款|哪里能借到钱)", "代借贷款"),
)

REFUSAL_REPLY = (
    "这个请求我没法帮忙。套现、伪造流水、规避额度这类操作不合规，我只能帮你记账、"
    "查看消费情况和设置预算。"
)


def detect_violation(text: str) -> str | None:
    """返回命中的违规原因；未命中返回 None。"""
    normalized = text.strip()
    for pattern, reason in _VIOLATION_PATTERNS:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            return reason
    return None


def is_violation(text: str) -> bool:
    return detect_violation(text) is not None
