"""成员 4 的 OCR 识别服务测试（用替身客户端，不联网、不花钱）。"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.services.ocr_service import OcrError, ReceiptOcrService

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64


class _FakeCompletions:
    """模拟 openai 的 chat.completions.create 返回。"""

    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls += 1
        if not self._responses:
            raise AssertionError("替身响应已用完")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=item))])


class _FakeChat:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.completions = completions


class FakeClient:
    """替身客户端：按顺序返回预设的模型输出。"""

    def __init__(self, responses: list[object]) -> None:
        self.completions = _FakeCompletions(responses)
        self.chat = _FakeChat(self.completions)


def _settings(tmp_path: Path, key: str = "test-key", model: str = "glm-4v-flash") -> Settings:
    return Settings(ocr_upload_dir=str(tmp_path / "uploads"), vision_api_key=key, vision_model=model)


def _service(tmp_path: Path, responses: list[object]) -> tuple[ReceiptOcrService, FakeClient]:
    client = FakeClient(responses)
    service = ReceiptOcrService(_settings(tmp_path), client=client)
    upload_dir = service.settings.resolved_upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / "0123456789abcdef0123456789abcdef.png").write_bytes(PNG_BYTES)
    return service, client


IMAGE_ID = "0123456789abcdef0123456789abcdef"


def test_recognize_valid_json(tmp_path: Path) -> None:
    service, client = _service(
        tmp_path,
        ['{"amount": 25.5, "merchant": "沙县小吃", "occurred_at": "2026-11-25", "confidence": 0.92}'],
    )

    result = service.recognize(IMAGE_ID)

    assert result.amount == 25.5
    assert result.merchant == "沙县小吃"
    assert result.occurred_at == date(2026, 11, 25)
    assert result.confidence == 0.92
    assert client.completions.calls == 1


def test_recognize_strips_code_fence(tmp_path: Path) -> None:
    service, _ = _service(
        tmp_path,
        ['```json\n{"amount": 12, "merchant": "地铁", "occurred_at": "2026-11-24", "confidence": 0.8}\n```'],
    )

    result = service.recognize(IMAGE_ID)

    assert result.amount == 12.0
    assert result.merchant == "地铁"


def test_recognize_retries_after_bad_output(tmp_path: Path) -> None:
    service, client = _service(
        tmp_path,
        [
            "这张小票看起来是餐饮消费，金额大概 25 元。",
            '{"amount": 25, "merchant": "沙县小吃", "occurred_at": "2026-11-25", "confidence": 0.9}',
        ],
    )

    result = service.recognize(IMAGE_ID)

    assert result.amount == 25.0
    assert client.completions.calls == 2


def test_recognize_fails_after_two_bad_outputs(tmp_path: Path) -> None:
    service, client = _service(tmp_path, ["无法识别", "还是无法识别"])

    with pytest.raises(OcrError):
        service.recognize(IMAGE_ID)
    assert client.completions.calls == 2


def test_recognize_tolerates_missing_fields(tmp_path: Path) -> None:
    service, _ = _service(tmp_path, ["{}"])

    result = service.recognize(IMAGE_ID)

    assert result.amount is None
    assert result.merchant == ""
    assert result.occurred_at is None
    assert 0.0 <= result.confidence <= 1.0


def test_recognize_normalizes_messy_values(tmp_path: Path) -> None:
    service, _ = _service(
        tmp_path,
        ['{"amount": "¥1,280.50 元", "merchant": "  某超市 ", "occurred_at": "2026年11月23日", "confidence": 92}'],
    )

    result = service.recognize(IMAGE_ID)

    assert result.amount == 1280.5
    assert result.merchant == "某超市"
    assert result.occurred_at == date(2026, 11, 23)
    assert result.confidence == 0.92


def test_recognize_maps_api_error_to_ocr_error(tmp_path: Path) -> None:
    service, client = _service(tmp_path, [RuntimeError("429 rate limit")])

    with pytest.raises(OcrError):
        service.recognize(IMAGE_ID)
    assert client.completions.calls == 1


def test_recognize_rejects_unknown_image(tmp_path: Path) -> None:
    service = ReceiptOcrService(_settings(tmp_path), client=FakeClient([]))

    with pytest.raises(OcrError):
        service.recognize("ffffffffffffffffffffffffffffffff")


def test_recognize_marks_low_confidence(tmp_path: Path) -> None:
    service, _ = _service(
        tmp_path,
        ['{"amount": 25, "merchant": "沙县小吃", "occurred_at": "2026-11-25", "confidence": 0.62}'],
    )

    result = service.recognize(IMAGE_ID)

    assert result.confidence == 0.62
    assert result.raw["low_confidence"] is True


def test_recognize_uses_stub_without_vision_key(tmp_path: Path) -> None:
    service, client = _service(tmp_path, [])
    service.settings.vision_api_key = ""

    result = service.recognize(IMAGE_ID)

    assert result.merchant == "沙县小吃"
    assert client.completions.calls == 0


def test_recognize_builds_real_http_request(tmp_path: Path) -> None:
    """用 MockTransport 验证真实 OpenAI 客户端的请求格式（不联网）。"""
    import json as _json

    import httpx
    from openai import OpenAI

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = _json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": "fake-vl",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": '{"amount": 66.6, "merchant": "测试商户", "occurred_at": "2026-11-26", "confidence": 0.9}',
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            },
        )

    client = OpenAI(
        api_key="test-key",
        base_url="https://vision.example.com/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    service = ReceiptOcrService(_settings(tmp_path), client=client)
    upload_dir = service.settings.resolved_upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / f"{IMAGE_ID}.png").write_bytes(PNG_BYTES)

    result = service.recognize(IMAGE_ID)

    assert result.amount == 66.6
    assert result.merchant == "测试商户"
    body = captured["body"]
    assert body["model"] == "glm-4v-flash"
    assert str(captured["url"]).endswith("/chat/completions")
    user_content = body["messages"][1]["content"]
    assert user_content[1]["type"] == "image_url"
    assert user_content[1]["image_url"]["url"].startswith("data:image/png;base64,")

