"""对话接口：与前端（成员 3）约定的唯一入口。"""

from __future__ import annotations

from fastapi import APIRouter

from app.agent.schemas import ChatRequest, ChatResponse, ConfirmRequest, ConfirmResponse
from app.api.deps import get_orchestrator

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse, summary="发送一条对话消息")
def chat(payload: ChatRequest) -> ChatResponse:
    """文本/图片记账、查账、预算查询的统一入口。"""
    return get_orchestrator().chat(payload.session_id, payload.message, payload.image_id)


@router.post("/confirm", response_model=ConfirmResponse, summary="确认入账")
def confirm(payload: ConfirmRequest) -> ConfirmResponse:
    """用户在前端确认卡片上点击确认后调用，真正写入数据库。"""
    created, failed, reply, trace_id = get_orchestrator().confirm(payload.session_id, payload.actions)
    return ConfirmResponse(
        session_id=payload.session_id,
        created=created,
        failed=failed,
        reply=reply,
        trace_id=trace_id,
    )


@router.delete("/session/{session_id}", summary="清空会话")
def clear_session(session_id: str) -> dict[str, bool]:
    """前端「新会话」按钮调用。"""
    get_orchestrator().memory.clear(session_id)
    return {"cleared": True}
