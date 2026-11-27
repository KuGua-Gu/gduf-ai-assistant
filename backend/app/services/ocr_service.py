"""小票识别服务（成员 4 实现 ``OcrService`` 协议）。

链路：
1. 前端 ``POST /api/ocr/upload`` 拿到 ``image_id``；
2. Full ``/api/chat`` 带 ``image_id``，Orchestrator 调 ``recognize(image_id)``；
3. 本服务把图片交给视觉大模型，要求只输出 JSON，校验后返回 ``OcrResult``。

降级顺序：
- 配置了 ``VISION_API_KEY`` + ``VISION_MODEL`` → 视觉大模型；
- 未配置 → 退回 ``StubOcrService``（固定样例，保证评审无 Key 也能演示）；
- 识别失败 → 抛 ``OcrError``，由 Orchestrator 转成可读提示，不返回 500。
"""

from __future__ import annotations

import base64
import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.agent.schemas import OcrResult
from app.config import Settings, get_settings
from app.services.stubs import StubOcrService

logger = logging.getLogger("app.services.ocr")

# image_id 由上传接口生成（uuid4().hex），这里限制字符集顺带防止目录穿越
_IMAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_UPLOAD_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日")
_CODE_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

_SYSTEM_PROMPT = """你是一个严谨的票据信息抽取器。用户会给你一张小票或支付截图。
只输出一个 JSON 对象，不要输出解释、不要使用 Markdown 代码块，字段固定为：
{{"amount": 数字或null, "merchant": "商户名或空串", "occurred_at": "YYYY-MM-DD 或 null", "confidence": 0到1的小数}}
要求：
1. amount 只保留数字（元），看不清给 null；
2. merchant 取最可能的商户名，没有给空串；
3. occurred_at 取消费日期，无法判断给 null，不要编造；
4. confidence 表示你对整体识别的把握，不确定就低于 0.8；
5. 除以上四个字段外不要输出任何内容。"""

_USER_PROMPT = "识别这张小票，按约定只输出 JSON。"


class OcrError(RuntimeError):
    """识别失败（图片不存在、模型不可用、输出无法解析等）。"""


class ReceiptOcrService:
    """基于视觉大模型的小票识别实现（实现 ``OcrService`` 协议）。"""

    def __init__(self, settings: Settings | None = None, client: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self._fallback = StubOcrService()
        self._client = client

    # ------------------------------------------------------------------ 公开

    def recognize(self, image_id: str) -> OcrResult:
        """识别一张已上传的小票，返回结构化结果。"""
        path = self._resolve(image_id)

        if not self.settings.vision_configured:
            # 未配置视觉模型时退回桩实现，保证评审无需 Key 也能演示完整链路
            logger.warning("视觉模型未配置，image_id=%s 使用桩结果兜底", image_id)
            return self._fallback.recognize(image_id)

        return self._recognize_with_vision(image_id, path)

    # ------------------------------------------------------------------ 内部

    def _resolve(self, image_id: str) -> Path:
        """把 image_id 映射到上传目录中的真实文件。"""
        if not _IMAGE_ID_PATTERN.fullmatch(image_id or ""):
            raise OcrError("图片 ID 不合法")

        upload_dir = self.settings.resolved_upload_dir
        for suffix in _UPLOAD_SUFFIXES:
            candidate = upload_dir / f"{image_id}{suffix}"
            if candidate.is_file():
                return candidate
        raise OcrError("图片不存在或已过期，请重新上传")

    def _get_client(self) -> Any:
        """懒加载 OpenAI 兼容客户端，方便测试注入替身。"""
        if self._client is None:
            self._client = OpenAI(
                api_key=self.settings.vision_api_key,
                base_url=self.settings.vision_base_url,
                timeout=self.settings.llm_timeout_seconds,
                max_retries=0,
            )
        return self._client

    def _recognize_with_vision(self, image_id: str, path: Path) -> OcrResult:
        """调用视觉模型识别小票；空响应与脏输出分别重试，仍失败抛 ``OcrError``。"""
        messages = self._build_messages(path)
        last_error: Exception | None = None
        parse_failures = 0
        empty_retries = 0

        for attempt in (1, 2, 3):
            try:
                response = self._get_client().chat.completions.create(
                    model=self.settings.vision_model,
                    messages=messages,
                    temperature=0,
                    max_tokens=400,
                )
            except Exception as exc:  # noqa: BLE001 - 外部服务异常统一转换
                logger.warning("trace image_id=%s vision call failed (attempt=%d): %s", image_id, attempt, exc)
                raise OcrError("视觉模型暂时不可用，请稍后再试或手动输入") from exc

            content = (response.choices[0].message.content or "").strip()
            if not content:
                # 模型偶发返回空内容（限流/抖动），补一次提示后重试
                last_error = ValueError("空响应")
                logger.warning("image_id=%s ocr empty response (attempt=%d)", image_id, attempt)
                if empty_retries >= 1:
                    break
                empty_retries += 1
                messages = [*messages, {"role": "user", "content": "请直接输出约定的 JSON，不要返回空内容。"}]
                continue

            try:
                payload = self._extract_json(content)
                result = self._to_result(payload)
                logger.info(
                    "image_id=%s ocr ok amount=%s merchant=%s confidence=%.2f",
                    image_id,
                    result.amount,
                    result.merchant,
                    result.confidence,
                )
                return result
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                last_error = exc
                parse_failures += 1
                logger.warning("image_id=%s ocr parse failed (attempt=%d): %s", image_id, attempt, exc)
                if parse_failures >= 2:
                    break
                messages = [
                    *messages,
                    {"role": "assistant", "content": content or "（空响应）"},
                    {"role": "user", "content": "只输出一个 JSON 对象，不要解释，不要代码块。"},
                ]

        raise OcrError("识别结果无法解析，请换一张更清晰的图片") from last_error

    @staticmethod
    def _build_messages(path: Path) -> list[dict[str, Any]]:
        """把图片编码成 data URL，拼成 OpenAI 兼容的多模态消息。"""
        suffix = path.suffix.lower()
        mime = _MIME_BY_SUFFIX.get(suffix, "image/png")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _USER_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                ],
            },
        ]

    @staticmethod
    def _extract_json(content: str) -> dict[str, Any]:
        """从模型输出里提取 JSON，兼容 ```json 代码块与前后解释文字。"""
        if not content:
            raise ValueError("空响应")

        fenced = _CODE_FENCE.search(content)
        candidate = fenced.group(1) if fenced else content
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("响应中没有 JSON 对象")

        payload = json.loads(candidate[start : end + 1])
        if not isinstance(payload, dict):
            raise ValueError("JSON 不是对象")
        return payload

    @classmethod
    def _to_result(cls, payload: dict[str, Any]) -> OcrResult:
        """把模型输出的松散字段规范成 ``OcrResult``。"""
        confidence = cls._parse_confidence(payload.get("confidence"))
        raw = dict(payload)
        if confidence < 0.8:
            # 低置信度标记，便于前端/日志提示用户核对（needs_review 由 Orchestrator 生成）
            raw["low_confidence"] = True
        return OcrResult(
            amount=cls._parse_amount(payload.get("amount")),
            merchant=cls._parse_merchant(payload.get("merchant")),
            occurred_at=cls._parse_date(payload.get("occurred_at")),
            confidence=confidence,
            raw=raw,
        )

    @staticmethod
    def _parse_amount(value: Any) -> float | None:
        """金额：接受 25 / "25.00" / "¥25.5" 等写法，非法值返回 None。"""
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            amount = float(value)
        else:
            match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
            if not match:
                return None
            amount = float(match.group())
        return round(amount, 2) if amount > 0 else None

    @staticmethod
    def _parse_merchant(value: Any) -> str:
        """商户：去空白并截断，避免脏数据撑爆前端卡片。"""
        if value is None:
            return ""
        return str(value).strip()[:60]

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        """日期：支持 2026-11-25 / 2026/11/25 / 2026年11月25日。"""
        if value is None or value == "":
            return None
        text = str(value).strip()
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_confidence(value: Any) -> float:
        """置信度：统一到 0~1；模型返回 92 这类百分数时自动换算。"""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.6
        if number > 1:
            number /= 100
        return round(min(max(number, 0.0), 1.0), 2)
