"""初始化并幂等导入示例账单数据。

默认从 ``backend/samples/demo_transactions.csv`` 读取数据。每行使用稳定的
``seed_key`` 映射到 ``demo-seed:<seed_key>`` 会话标识，重复执行时已导入的行
会被跳过。
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.agent.categories import normalize_category, today_in
from app.agent.schemas import TransactionDraft, TransactionSource
from app.config import get_settings
from app.services.transaction_service import SqliteTransactionService

DEFAULT_CSV_PATH = Path(__file__).resolve().parents[2] / "samples" / "demo_transactions.csv"
REQUIRED_COLUMNS = {
    "seed_key",
    "category",
    "amount",
    "merchant",
    "date_offset_days",
    "note",
    "source",
}
SEED_SESSION_PREFIX = "demo-seed:"
_SEED_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True)
class SeedRow:
    """一行经过校验的示例账单。"""

    seed_key: str
    draft: TransactionDraft


@dataclass(frozen=True)
class ImportResult:
    """导入统计。"""

    inserted: int
    skipped: int
    total: int


def _parse_anchor_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("anchor-date 必须为 YYYY-MM-DD") from exc


def _parse_seed_rows(csv_path: Path, anchor_date: date) -> list[SeedRow]:
    """读取并校验 CSV，保证 seed_key 唯一。"""
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - fieldnames
        if missing:
            raise ValueError(f"CSV 缺少字段：{', '.join(sorted(missing))}")

        rows: list[SeedRow] = []
        seen_keys: set[str] = set()
        for line_number, raw in enumerate(reader, start=2):
            seed_key = (raw.get("seed_key") or "").strip()
            if not seed_key or not _SEED_KEY_PATTERN.fullmatch(seed_key):
                raise ValueError(f"第 {line_number} 行 seed_key 不合法")
            if seed_key in seen_keys:
                raise ValueError(f"第 {line_number} 行 seed_key 重复：{seed_key}")
            if len(SEED_SESSION_PREFIX + seed_key) > 64:
                raise ValueError(f"第 {line_number} 行 seed_key 过长")
            seen_keys.add(seed_key)

            category = normalize_category(raw.get("category"))
            if not category:
                raise ValueError(f"第 {line_number} 行 category 不能为空")
            try:
                amount = Decimal((raw.get("amount") or "").strip())
            except InvalidOperation as exc:
                raise ValueError(f"第 {line_number} 行 amount 不是有效数字") from exc
            if not amount.is_finite() or amount <= 0:
                raise ValueError(f"第 {line_number} 行 amount 必须大于 0")
            try:
                offset_days = int((raw.get("date_offset_days") or "").strip())
            except ValueError as exc:
                raise ValueError(f"第 {line_number} 行 date_offset_days 必须为整数") from exc
            try:
                source = TransactionSource((raw.get("source") or "").strip())
            except ValueError as exc:
                raise ValueError(f"第 {line_number} 行 source 不合法") from exc

            rows.append(
                SeedRow(
                    seed_key=seed_key,
                    draft=TransactionDraft(
                        amount=float(amount),
                        category=category,
                        merchant=(raw.get("merchant") or "").strip(),
                        occurred_at=anchor_date + timedelta(days=offset_days),
                        note=(raw.get("note") or "").strip(),
                        source=source,
                    ),
                )
            )
    if not rows:
        raise ValueError("CSV 中没有可导入的账单")
    return rows


def import_seed_rows(
    service: SqliteTransactionService,
    rows: list[SeedRow],
) -> ImportResult:
    """幂等写入示例账单，已有 seed_key 的行直接跳过。"""
    inserted = 0
    skipped = 0
    for row in rows:
        session_id = SEED_SESSION_PREFIX + row.seed_key
        if service.find_by_session_id(session_id) is not None:
            skipped += 1
            continue
        service.create_transactions([row.draft], session_id=session_id)
        inserted += 1
    return ImportResult(inserted=inserted, skipped=skipped, total=len(rows))


def import_seed_data(
    db_path: str | Path,
    csv_path: str | Path = DEFAULT_CSV_PATH,
    anchor_date: date | None = None,
) -> ImportResult:
    """创建数据库并导入示例数据。"""
    settings = get_settings()
    resolved_anchor = anchor_date or today_in(settings.timezone)
    rows = _parse_seed_rows(Path(csv_path).expanduser().resolve(), resolved_anchor)
    service = SqliteTransactionService(db_path)
    try:
        return import_seed_rows(service, rows)
    finally:
        service._engine.dispose()


def main() -> int:
    """命令行入口。"""
    settings = get_settings()
    parser = argparse.ArgumentParser(description="初始化并导入示例账单")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV_PATH, help="示例账单 CSV 路径")
    parser.add_argument("--db-path", type=Path, default=None, help="SQLite 路径，缺省使用 DB_PATH")
    parser.add_argument(
        "--anchor-date",
        type=_parse_anchor_date,
        default=None,
        help="相对日期的基准日，缺省为今天（Asia/Shanghai）",
    )
    args = parser.parse_args()

    db_path = args.db_path or settings.resolved_db_path
    try:
        result = import_seed_data(db_path, args.csv, args.anchor_date)
    except (OSError, ValueError) as exc:
        print(f"导入失败：{exc}", file=sys.stderr)
        return 2

    print(
        f"示例数据导入完成：新增 {result.inserted} 条，"
        f"跳过 {result.skipped} 条，共 {result.total} 条。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
