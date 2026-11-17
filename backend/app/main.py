"""FastAPI 应用入口。"""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent.errors import AgentError, LLMUnavailableError
from app.api.chat import router as chat_router
from app.config import get_settings

logger = logging.getLogger("app.main")


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def create_app() -> FastAPI:
    """创建应用实例，注册路由、CORS 与统一错误格式。"""
    settings = get_settings()
    _configure_logging(settings.log_level)

    app = FastAPI(
        title="个人记账与消费分析 AI 助手",
        description="自然语言/小票记账 + 消费统计 + 预算提醒",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(chat_router)

    @app.get("/api/health", tags=["system"], summary="健康检查")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "llm_configured": settings.llm_configured,
            "llm_model": settings.llm_model,
        }

    @app.exception_handler(AgentError)
    async def agent_error_handler(request: Request, exc: AgentError) -> JSONResponse:
        trace_id = uuid.uuid4().hex[:12]
        status_code = 503 if isinstance(exc, LLMUnavailableError) else 500
        logger.warning("trace=%s path=%s code=%s detail=%s", trace_id, request.url.path, exc.code, exc.detail)
        return JSONResponse(
            status_code=status_code,
            content={"code": exc.code, "message": exc.user_message, "trace_id": trace_id},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        trace_id = uuid.uuid4().hex[:12]
        return JSONResponse(
            status_code=422,
            content={"code": "VALIDATION_ERROR", "message": "请求参数不合法，请检查后重试。", "trace_id": trace_id},
        )

    return app


app = create_app()
