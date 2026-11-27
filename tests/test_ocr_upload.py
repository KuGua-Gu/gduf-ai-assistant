"""成员 4 的 OCR 上传接口与服务降级测试。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services.ocr_service import OcrError, ReceiptOcrService

# 一个最小的合法 PNG 文件头 + 填充内容，足够通过文件头校验
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """测试用配置：上传目录指向临时目录，限制 1KB 便于验证超限。"""
    return Settings(ocr_upload_dir=str(tmp_path / "uploads"), ocr_max_bytes=1024)


@pytest.fixture
def client(settings: Settings):
    """覆盖配置依赖的测试客户端。"""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_upload_png_returns_image_id_and_saves_file(client: TestClient, settings: Settings) -> None:
    resp = client.post("/api/ocr/upload", files={"file": ("receipt.png", PNG_BYTES, "image/png")})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["image_id"]) == 32
    assert body["size"] == len(PNG_BYTES)
    saved = settings.resolved_upload_dir / f"{body['image_id']}.png"
    assert saved.is_file()
    assert saved.read_bytes() == PNG_BYTES


def test_upload_rejects_unsupported_extension(client: TestClient) -> None:
    resp = client.post("/api/ocr/upload", files={"file": ("payload.exe", b"MZ", "application/octet-stream")})

    assert resp.status_code == 415
    assert resp.json()["code"] == "INVALID_FILE_TYPE"


def test_upload_rejects_fake_image_content(client: TestClient) -> None:
    resp = client.post("/api/ocr/upload", files={"file": ("fake.png", b"MZ-not-a-png", "image/png")})

    assert resp.status_code == 415
    assert resp.json()["code"] == "INVALID_FILE_TYPE"


def test_upload_rejects_oversized_file(client: TestClient) -> None:
    oversized = PNG_BYTES + b"0" * 2048
    resp = client.post("/api/ocr/upload", files={"file": ("big.png", oversized, "image/png")})

    assert resp.status_code == 413
    assert resp.json()["code"] == "FILE_TOO_LARGE"


def test_ocr_service_rejects_unknown_image(settings: Settings) -> None:
    service = ReceiptOcrService(settings)

    with pytest.raises(OcrError):
        service.recognize("0123456789abcdef0123456789abcdef")


def test_ocr_service_falls_back_to_stub_without_vision_key(tmp_path: Path) -> None:
    """未配置视觉模型时退回桩结果，保证无 Key 也能演示。"""
    settings = Settings(
        ocr_upload_dir=str(tmp_path / "uploads"),
        vision_api_key="",
        vision_model="",
    )
    settings.resolved_upload_dir.mkdir(parents=True, exist_ok=True)
    image_id = "0123456789abcdef0123456789abcdef"
    (settings.resolved_upload_dir / f"{image_id}.png").write_bytes(PNG_BYTES)

    result = ReceiptOcrService(settings).recognize(image_id)

    assert result.merchant == "沙县小吃"
    assert result.amount == 25.0
