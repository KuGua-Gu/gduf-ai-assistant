"""演示数据脚本：对本地后端依次记账并确认，生成可复现的答辩数据。

用法（先启动后端）：
    python scripts/demo_seed.py
    python scripts/demo_seed.py --base http://127.0.0.1:8000

注意：只应在空账本上运行一次；重复运行会产生重复账单。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:8000"
SEED_MESSAGES = [
    ("午饭 25", "餐饮 25.00"),
    ("今天打车 32", "交通 32.00"),
    ("今天看电影 45", "娱乐 45.00"),
]


def post(base: str, path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{base}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="生成演示账单")
    parser.add_argument("--base", default=DEFAULT_BASE, help="后端地址")
    args = parser.parse_args()

    try:
        for message, expected in SEED_MESSAGES:
            chat = post(args.base, "/api/chat", {"message": message})
            actions = chat.get("pending_actions") or []
            if not actions:
                print(f"[跳过] {message} -> intent={chat.get('intent')} reply={chat.get('reply')}")
                continue
            result = post(
                args.base,
                "/api/chat/confirm",
                {"session_id": chat["session_id"], "actions": actions},
            )
            print(f"[入账] {message} -> 预期 {expected}，created={result.get('created')} failed={result.get('failed')}")
    except urllib.error.URLError as exc:
        print(f"无法连接后端 {args.base}：{exc}", file=sys.stderr)
        return 1

    print("\n演示数据就绪。建议验证：")
    print("- 「这个月餐饮花了多少」 -> 25.00")
    print("- 「这个月一共花了多少」 -> 102.00")
    print("- 「这个月吃饭预算 1500」后再问剩余 -> 已花 25.00")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
