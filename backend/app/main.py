"""FastAPI 应用入口。"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.agent.errors import AgentError, LLMUnavailableError
from app.api.budgets import router as budgets_router
from app.api.chat import router as chat_router
from app.api.errors import BusinessAPIError
from app.api.ocr import router as ocr_router
from app.api.stats import router as stats_router
from app.api.transactions import router as transactions_router
from app.config import get_settings

logger = logging.getLogger("app.main")

# 前端构建产物：frontend/dist（`cd frontend && npm run build`）
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


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
    app.include_router(transactions_router)
    app.include_router(stats_router)
    app.include_router(budgets_router)
    app.include_router(ocr_router)

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

    @app.exception_handler(BusinessAPIError)
    async def business_api_error_handler(request: Request, exc: BusinessAPIError) -> JSONResponse:
        trace_id = uuid.uuid4().hex[:12]
        logger.warning(
            "trace=%s path=%s code=%s detail=%s",
            trace_id,
            request.url.path,
            exc.code,
            exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "trace_id": trace_id},
        )

    # 前端产物存在时托管到 /（hash 路由，无需 history fallback）。
    # 注意：必须最后挂载，否则 "/" 会匹配掉之后注册的 /api/* 路由。
    if FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
        logger.info("已挂载前端构建产物：%s", FRONTEND_DIST)

    return app


app = create_app()
