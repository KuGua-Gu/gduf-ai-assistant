"""生成合成小票样例，用于 OCR 离线评测（只需运行一次，产物已提交仓库）。

用法：
    python scripts/make_receipt_samples.py                # 默认生成 10 张到 backend/samples/receipts
    python scripts/make_receipt_samples.py --count 20     # 生成更多
    python scripts/make_receipt_samples.py --font C:/Windows/Fonts/simhei.ttf

依赖 Pillow（仅生成样例时使用，运行服务不需要）：
    pip install pillow
"""

from __future__ import annotations

import argparse
import csv
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = REPO_ROOT / "backend" / "samples" / "receipts"
FONT_CANDIDATES = (
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
)

MERCHANTS = (
    "沙县小吃",
    "瑞幸咖啡",
    "麦当劳",
    "永辉超市",
    "全家便利店",
    "兰州拉面",
    "菜鸟驿站",
    "滴滴出行",
    "美团外卖",
    "中国石化",
)
ITEMS = ("招牌套餐", "拿铁咖啡", "巨无霸套餐", "矿泉水", "关东煮", "牛肉面", "快递费", "打车费", "外卖订单", "92 号汽油")


@dataclass
class Sample:
    image_id: str
    merchant: str
    amount: float
    occurred_at: date


def _load_font(size: int, font_path: str | None) -> ImageFont.FreeTypeFont:
    candidates = (font_path,) if font_path else FONT_CANDIDATES
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    raise SystemExit("找不到中文字体，请用 --font 指定一个 .ttf/.ttc 字体路径")


def _render(sample: Sample, out_path: Path, font: ImageFont.FreeTypeFont, index: int) -> None:
    """绘制一张 480x640 的小票；奇偶交替两种版式，避免样本过于单一。"""
    image = Image.new("RGB", (480, 640), "white")
    draw = ImageDraw.Draw(image)
    small = ImageFont.truetype(font.path, 18)
    big = ImageFont.truetype(font.path, 30)

    if index % 2 == 0:
        draw.text((140, 24), sample.merchant, fill="black", font=big)
        draw.line((20, 70, 460, 70), fill="black", width=2)
        draw.text((20, 90), f"商品：{random.choice(ITEMS)}", fill="black", font=small)
        draw.text((20, 125), f"日期：{sample.occurred_at.isoformat()}", fill="black", font=small)
        draw.text((20, 160), "数量：1", fill="black", font=small)
        draw.line((20, 200, 460, 200), fill="black", width=1)
        draw.text((20, 230), "合计（元）", fill="black", font=big)
        draw.text((330, 225), f"{sample.amount:.2f}", fill="black", font=big)
        draw.text((20, 320), "谢谢惠顾，欢迎再次光临", fill="black", font=small)
    else:
        draw.text((20, 24), "电子发票", fill="black", font=big)
        draw.text((20, 80), f"商户：{sample.merchant}", fill="black", font=small)
        draw.text((20, 115), f"开票日期：{sample.occurred_at.isoformat()}", fill="black", font=small)
        draw.text((20, 150), f"项目：{random.choice(ITEMS)}", fill="black", font=small)
        draw.text((20, 185), "金额：", fill="black", font=small)
        draw.text((100, 178), f"¥{sample.amount:.2f}", fill="black", font=big)
        draw.rectangle((20, 240, 460, 300), outline="black", width=2)
        draw.text((40, 255), f"价税合计：{sample.amount:.2f} 元", fill="black", font=small)

    # 加一点噪声与倾斜，让样本更接近真实拍照
    image = image.rotate(random.uniform(-1.5, 1.5), expand=True, fillcolor="white")
    image.save(out_path, format="PNG")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成合成小票样例与 ground_truth.csv")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--font", default=None, help="中文字体路径（默认自动查找系统中文字体）")
    parser.add_argument("--seed", type=int, default=20261125, help="随机种子，保证可复现")
    args = parser.parse_args()

    random.seed(args.seed)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    font = _load_font(28, args.font)

    samples: list[Sample] = []
    today = date(2026, 11, 25)
    for index in range(1, args.count + 1):
        sample = Sample(
            image_id=f"receipt-{index:02d}",
            merchant=random.choice(MERCHANTS),
            amount=round(random.uniform(8, 320), 2),
            occurred_at=today - timedelta(days=random.randint(0, 20)),
        )
        _render(sample, args.out_dir / f"{sample.image_id}.png", font, index)
        samples.append(sample)

    truth_path = args.out_dir / "ground_truth.csv"
    with truth_path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(["image_id", "merchant", "amount", "occurred_at"])
        for sample in samples:
            writer.writerow([sample.image_id, sample.merchant, f"{sample.amount:.2f}", sample.occurred_at.isoformat()])

    print(f"已生成 {len(samples)} 张样例小票 → {args.out_dir}")
    print(f"标注文件 → {truth_path}")


if __name__ == "__main__":
    main()
