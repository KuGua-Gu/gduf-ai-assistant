"""OCR 图片上传接口（成员 4）。

前端先调用 ``POST /api/ocr/upload`` 上传小票，拿到 ``image_id``；
随后把 ``image_id`` 放进 ``POST /api/chat`` 的请求体，由 Orchestrator
调用 ``OcrService.recognize`` 生成待确认草稿。
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.errors import BusinessAPIError
from app.config import Settings, get_settings

logger = logging.getLogger("app.api.ocr")

router = APIRouter(prefix="/api/ocr", tags=["ocr"])

# 允许的扩展名 → 期望的文件头，用于拦截"只改后缀"的非图片文件
_IMAGE_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".webp": (b"RIFF",),
}
_CHUNK_SIZE = 64 * 1024


def _detect_suffix(filename: str) -> str:
    """校验扩展名并返回小写后缀。"""
    suffix = Path(filename or "").suffix.lower()
    if suffix not in _IMAGE_SIGNATURES:
        raise BusinessAPIError(415, "INVALID_FILE_TYPE", "只支持 JPG/PNG/WEBP 格式的小票图片。")
    return suffix


def _looks_like_image(suffix: str, head: bytes) -> bool:
    """用文件头粗校验图片类型，避免伪装成图片的其他文件。"""
    if suffix == ".webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    return any(head.startswith(signature) for signature in _IMAGE_SIGNATURES[suffix])


async def _read_limited(upload: UploadFile, limit: int) -> bytes:
    """分块读取上传内容，超过上限立即中断，避免大文件占满内存。"""
    buffer = bytearray()
    while True:
        chunk = await upload.read(_CHUNK_SIZE)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > limit:
            raise BusinessAPIError(
                413, "FILE_TOO_LARGE", f"图片不能超过 {limit // (1024 * 1024)} MB。"
            )
    return bytes(buffer)


@router.post("/upload", summary="上传小票/截图，返回 image_id")
async def upload_receipt(
    file: UploadFile = File(..., description="小票或支付截图（JPG/PNG/WEBP）"),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """保存图片到本地上传目录并返回后续对话使用的 ``image_id``。"""
    suffix = _detect_suffix(file.filename or "")
    data = await _read_limited(file, settings.ocr_max_bytes)
    if not data:
        raise BusinessAPIError(422, "EMPTY_FILE", "上传的图片是空的，请重新选择。")
    if not _looks_like_image(suffix, data[:16]):
        raise BusinessAPIError(415, "INVALID_FILE_TYPE", "文件内容不是有效的图片。")

    upload_dir = settings.resolved_upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    image_id = uuid.uuid4().hex
    target = upload_dir / f"{image_id}{suffix}"
    target.write_bytes(data)

    logger.info("upload image_id=%s size=%d suffix=%s", image_id, len(data), suffix)
    return {
        "image_id": image_id,
        "filename": target.name,
        "size": len(data),
        "content_type": file.content_type,
    }
