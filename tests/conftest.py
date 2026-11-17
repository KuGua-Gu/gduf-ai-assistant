"""pytest 配置：注入 backend 到 sys.path，提供 --mock-llm / --live 开关。"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def pytest_addoption(parser) -> None:
    parser.addoption("--mock-llm", action="store_true", default=False, help="使用离线规则模型（默认行为）")
    parser.addoption("--live", action="store_true", default=False, help="用真实大模型跑 30 条评测集")
