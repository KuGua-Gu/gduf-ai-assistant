"""视觉模型连通性自检：一条命令确认 Key 可用、并识别一张样例小票。

用法：
    python scripts/check_vision.py
    python scripts/check_vision.py --image receipt-03

成功输出示例：
    [ok] glm-4v-flash 识别成功（1.8s）
         amount=106.30  merchant=沙县小吃  occurred_at=2026-11-08  confidence=0.92
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.services.ocr_service import OcrError, ReceiptOcrService  # noqa: E402

SAMPLES_DIR = REPO_ROOT / "backend" / "samples" / "receipts"


def main() -> None:
    parser = argparse.ArgumentParser(description="检查视觉模型 Key 是否可用")
    parser.add_argument("--image", default="receipt-01", help="样例小票的 image_id（文件名去掉后缀）")
    args = parser.parse_args()

    settings = Settings(ocr_upload_dir=str(SAMPLES_DIR))
    if not settings.vision_configured:
        raise SystemExit(
            "未配置视觉模型：请在 .env 填写 VISION_API_KEY / VISION_MODEL，"
            "例如 glm-4v-flash（智谱）或 qwen-vl-plus（通义）。"
        )

    image_path = SAMPLES_DIR / f"{args.image}.png"
    if not image_path.is_file():
        raise SystemExit(f"找不到样例图片：{image_path}")

    started = time.perf_counter()
    try:
        result = ReceiptOcrService(settings).recognize(args.image)
    except OcrError as exc:
        raise SystemExit(f"[fail] {exc}") from exc
    elapsed = time.perf_counter() - started

    print(f"[ok] {settings.vision_model} 识别成功（{elapsed:.1f}s）")
    print(
        f"     amount={result.amount}  merchant={result.merchant}  "
        f"occurred_at={result.occurred_at}  confidence={result.confidence}"
    )


if __name__ == "__main__":
    main()
