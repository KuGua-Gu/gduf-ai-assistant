"""OCR 离线评测：对比识别结果与 ground_truth.csv，统计三项准确率。

用法：
    python scripts/eval_ocr.py                       # 评测 backend/samples/receipts
    python scripts/eval_ocr.py --limit 5             # 只跑前 5 张
    python scripts/eval_ocr.py --dir path/to/receipts

前置条件：.env 中配置好 VISION_API_KEY / VISION_MODEL（DeepSeek 文本模型不支持图片）。
没有配置时脚本会提示并退出，不会产生任何费用。
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.services.ocr_service import OcrError, ReceiptOcrService  # noqa: E402

DEFAULT_DIR = REPO_ROOT / "backend" / "samples" / "receipts"


@dataclass
class Case:
    image_id: str
    merchant: str
    amount: float
    occurred_at: date


def _load_cases(directory: Path) -> list[Case]:
    truth = directory / "ground_truth.csv"
    if not truth.is_file():
        raise SystemExit(f"找不到标注文件：{truth}（先运行 scripts/make_receipt_samples.py）")

    cases: list[Case] = []
    with truth.open(encoding="utf-8", newline="") as fp:
        for row in csv.DictReader(fp):
            cases.append(
                Case(
                    image_id=row["image_id"],
                    merchant=row["merchant"],
                    amount=float(row["amount"]),
                    occurred_at=date.fromisoformat(row["occurred_at"]),
                )
            )
    return cases


def _amount_ok(predicted: float | None, expected: float, tolerance: float) -> bool:
    return predicted is not None and abs(predicted - expected) <= tolerance


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR 样例评测")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--limit", type=int, default=0, help="只评测前 N 张，0 表示全部")
    parser.add_argument("--tolerance", type=float, default=0.01, help="金额允许误差（元）")
    args = parser.parse_args()

    settings = Settings(ocr_upload_dir=str(args.dir))
    if not settings.vision_configured:
        raise SystemExit(
            "未配置视觉模型：请在 .env 中填写 VISION_API_KEY / VISION_MODEL（例如 glm-4v-flash 或 qwen-vl-plus）。"
        )

    service = ReceiptOcrService(settings)
    cases = _load_cases(args.dir)
    if args.limit:
        cases = cases[: args.limit]

    rows: list[tuple[str, str, str, str, str, str]] = []
    amount_hits = merchant_hits = date_hits = 0

    for case in cases:
        try:
            result = service.recognize(case.image_id)
        except OcrError as exc:
            rows.append((case.image_id, "调用失败", str(exc), "-", "-", "✗"))
            continue

        amount_ok = _amount_ok(result.amount, case.amount, args.tolerance)
        # 商户名允许包含关系（模型多写“沙县小吃(万达店)”也算对）
        merchant_ok = bool(result.merchant) and (
            case.merchant in result.merchant or result.merchant in case.merchant
        )
        date_ok = result.occurred_at == case.occurred_at
        amount_hits += amount_ok
        merchant_hits += merchant_ok
        date_hits += date_ok

        rows.append(
            (
                case.image_id,
                f"{result.amount:.2f}" if result.amount is not None else "—",
                result.merchant or "—",
                str(result.occurred_at) if result.occurred_at else "—",
                f"{result.confidence:.2f}",
                "+" if amount_ok and merchant_ok and date_ok else
                ("金额✓" if amount_ok else "") + ("商户✓" if merchant_ok else "") + ("日期✓" if date_ok else "") or "✗",
            )
        )

    total = max(len(cases), 1)
    print(f"评测样本：{len(cases)} 张（目录：{args.dir}）")
    print(f"{'image_id':<12}{'金额':>10}{'商户':<18}{'日期':<12}{'置信度':>7}  判定")
    for row in rows:
        print(f"{row[0]:<12}{row[1]:>10}{row[2]:<18}{row[3]:<12}{row[4]:>7}  {row[5]}")

    print("\n准确率：")
    print(f"  金额：{amount_hits}/{len(cases)} = {amount_hits / total:.0%}")
    print(f"  商户：{merchant_hits}/{len(cases)} = {merchant_hits / total:.0%}")
    print(f"  日期：{date_hits}/{len(cases)} = {date_hits / total:.0%}")
    exact = sum(1 for row in rows if row[5] == "+")
    print(f"  三项全对：{exact}/{len(cases)} = {exact / total:.0%}")


if __name__ == "__main__":
    main()
