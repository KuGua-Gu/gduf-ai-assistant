"""业务层内存实现：用于 Agent 离线测试与成员 2 完成前的联调兜底。

注意：这里只是桩实现，真实落库由成员 2 的 SQLite 实现替换，Agent 代码无需改动。
"""

from __future__ import annotations

from datetime import date
from typing import Any, Sequence

from app.agent.schemas import OcrResult, TransactionDraft, TransactionFilter


class InMemoryTransactionService:
    """满足 TransactionService 协议的内存版实现。"""

    def __init__(self) -> None:
        self._rows: list[dict[str, Any]] = []
        self._next_id = 1
        self._budgets: dict[tuple[str, str], float] = {}

    def create_transactions(
        self, drafts: Sequence[TransactionDraft], session_id: str | None = None
    ) -> list[dict[str, Any]]:
        created: list[dict[str, Any]] = []
        for draft in drafts:
            row = {
                "id": self._next_id,
                "amount": float(draft.amount or 0),
                "category": draft.category or "其他",
                "merchant": draft.merchant,
                "occurred_at": draft.occurred_at,
                "note": draft.note,
                "source": draft.source.value,
            }
            self._rows.append(row)
            created.append(dict(row))
            self._next_id += 1
        return created

    def update_transaction(self, transaction_id: int, patch: dict[str, Any]) -> dict[str, Any] | None:
        for row in self._rows:
            if row["id"] == transaction_id:
                allowed = {"amount", "category", "merchant", "occurred_at", "note"}
                row.update({k: v for k, v in patch.items() if k in allowed})
                return dict(row)
        return None

    def delete_transaction(self, transaction_id: int) -> bool:
        for index, row in enumerate(self._rows):
            if row["id"] == transaction_id:
                self._rows.pop(index)
                return True
        return False

    def query_transactions(self, filters: TransactionFilter) -> list[dict[str, Any]]:
        result = []
        for row in self._rows:
            if filters.start_date and row["occurred_at"] and row["occurred_at"] < filters.start_date:
                continue
            if filters.end_date and row["occurred_at"] and row["occurred_at"] > filters.end_date:
                continue
            if filters.category and row["category"] != filters.category:
                continue
            if filters.keyword and filters.keyword not in f"{row['merchant']}{row['note']}":
                continue
            result.append(dict(row))
        result.sort(key=lambda item: item["occurred_at"] or date.min, reverse=True)
        return result[: filters.limit]

    def get_stats(
        self,
        start: date,
        end: date,
        group_by: str = "category",
        category: str | None = None,
    ) -> dict[str, Any]:
        buckets: dict[str, dict[str, float]] = {}
        total = 0.0
        for row in self._rows:
            occurred = row["occurred_at"]
            if not occurred or occurred < start or occurred > end:
                continue
            if category and row["category"] != category:
                continue
            if group_by == "day":
                key = occurred.isoformat()
            elif group_by == "month":
                key = occurred.strftime("%Y-%m")
            else:
                key = row["category"]
            bucket = buckets.setdefault(key, {"amount": 0.0, "count": 0})
            bucket["amount"] += row["amount"]
            bucket["count"] += 1
            total += row["amount"]
        items = [
            {"key": key, "amount": round(value["amount"], 2), "count": int(value["count"])}
            for key, value in sorted(buckets.items(), key=lambda kv: kv[1]["amount"], reverse=True)
        ]
        return {"start": start.isoformat(), "end": end.isoformat(), "group_by": group_by, "total": round(total, 2), "items": items}

    def set_budget(self, scope: str, amount: float, month: str) -> dict[str, Any]:
        self._budgets[(month, scope)] = float(amount)
        return {"month": month, "scope": scope, "amount": float(amount)}

    def get_budget_status(self, month: str) -> dict[str, Any]:
        start = date.fromisoformat(f"{month}-01")
        end = date(start.year + (1 if start.month == 12 else 0), 1 if start.month == 12 else start.month + 1, 1)
        spent_by_category: dict[str, float] = {}
        total_spent = 0.0
        for row in self._rows:
            occurred = row["occurred_at"]
            if not occurred or not (start <= occurred < end):
                continue
            spent_by_category[row["category"]] = spent_by_category.get(row["category"], 0.0) + row["amount"]
            total_spent += row["amount"]

        items = []
        for (budget_month, scope), amount in self._budgets.items():
            if budget_month != month:
                continue
            spent = total_spent if scope == "total" else spent_by_category.get(scope, 0.0)
            usage = spent / amount if amount else 0.0
            status = "exceeded" if usage > 1 else ("warning" if usage >= 0.8 else "normal")
            items.append({"scope": scope, "budget": amount, "spent": round(spent, 2), "usage": round(usage, 3), "status": status})
        return {
            "month": month,
            "total_budget": self._budgets.get((month, "total")),
            "total_spent": round(total_spent, 2),
            "items": items,
        }


class StubOcrService:
    """OCR 桩实现：固定返回一张样例小票，供未接入成员 4 服务时联调。"""

    def recognize(self, image_id: str) -> OcrResult:
        return OcrResult(
            amount=25.0,
            merchant="沙县小吃",
            occurred_at=date.today(),
            confidence=0.72,
            raw={"image_id": image_id, "stub": True},
        )
