"""行程问答助手接口。"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ...agents.travel_assistant_agent import get_travel_assistant_agent
from ...models.schemas import (
    AssistantChatRequest,
    AssistantChatResponse,
    AssistantSessionResponse,
    TripPlanResponse,
    TripPlanUpdateRequest,
)
from ...services.session_store import (
    TripPlanVersionConflict,
    get_assistant_session_store,
)

router = APIRouter(prefix="/assistant", tags=["行程问答助手"])


def encode_stream_event(event: str, data: dict) -> str:
    """将流式事件编码为 NDJSON 单行。"""
    return json.dumps({"event": event, **data}, ensure_ascii=False) + "\n"


@router.post(
    "/chat",
    response_model=AssistantChatResponse,
    summary="行程问答与行程操作",
    description="在规划页收集需求并生成计划，在结果页回答问题或修改当前计划。",
)
async def chat(request: AssistantChatRequest):
    """非流式行程问答。"""
    try:
        return await get_travel_assistant_agent().achat(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"助手处理失败: {exc}") from exc


@router.post(
    "/chat/stream",
    summary="流式行程问答与行程操作",
    description="以 NDJSON 流式返回助手状态、回答片段和最终结构化结果。",
)
async def chat_stream(request: AssistantChatRequest):
    """流式行程问答。"""

    async def event_stream():
        agent = get_travel_assistant_agent()

        try:
            parsed = None
            visible_reply = ""

            async for event in agent.stream_analysis(request):
                if event["event"] == "delta":
                    yield encode_stream_event("delta", {"text": event["text"]})
                    continue

                if event["event"] == "analysis_complete":
                    parsed = event["parsed"]
                    visible_reply = event["visible_reply"]

            status_message = agent.get_action_status(request, parsed or {})
            if status_message:
                yield encode_stream_event("status", {"message": status_message})

            response = await agent.complete_response(
                request,
                parsed or {},
                reply_override=visible_reply,
            )

            yield encode_stream_event("final", {"data": response.model_dump(mode="json")})

        except Exception as exc:
            yield encode_stream_event("error", {"message": f"助手处理失败: {exc}"})

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache"},
    )


@router.get(
    "/session/{session_id}",
    response_model=AssistantSessionResponse,
    summary="获取问答助手会话",
    description="根据 session_id 获取后端维护的对话历史、行程草稿和当前行程。",
)
async def get_session(session_id: str):
    """获取后端会话快照。"""
    session = get_assistant_session_store().snapshot(session_id)
    return AssistantSessionResponse(
        success=True,
        message="获取会话成功",
        session_id=session.session_id,
        history=session.history,
        draft_trip_request=session.draft_trip_request,
        trip_plan=session.current_trip_plan,
        plan_version=session.plan_version,
    )


@router.get(
    "/session/{session_id}/trip-plan",
    response_model=TripPlanResponse,
    summary="获取当前会话行程",
    description="根据 session_id 获取当前会话保存的最新 TripPlan。",
)
async def get_session_trip_plan(session_id: str):
    """获取当前会话的最新行程计划。"""
    trip_plan, plan_version = get_assistant_session_store().get_trip_plan(session_id)
    return TripPlanResponse(
        success=trip_plan is not None,
        message="获取行程成功" if trip_plan else "当前会话暂无行程",
        data=trip_plan,
        session_id=session_id,
        plan_version=plan_version,
    )


@router.put(
    "/session/{session_id}/trip-plan",
    response_model=TripPlanResponse,
    summary="保存当前会话行程",
    description="使用 plan_version 乐观锁保存用户手动编辑后的 TripPlan。",
)
async def save_session_trip_plan(session_id: str, request: TripPlanUpdateRequest):
    """保存用户手动编辑后的行程计划。"""
    try:
        plan_version = get_assistant_session_store().save_trip_plan(
            session_id,
            request.trip_plan,
            expected_version=request.base_plan_version,
        )
        return TripPlanResponse(
            success=True,
            message="行程已保存",
            data=request.trip_plan,
            session_id=session_id,
            plan_version=plan_version,
        )
    except TripPlanVersionConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "行程版本已更新，请刷新后再保存",
                "current_version": exc.current_version,
            },
        ) from exc


@router.get("/health", summary="健康检查", description="检查行程问答助手是否正常")
async def health_check():
    """行程问答助手健康检查。"""
    try:
        get_travel_assistant_agent()
        return {"status": "healthy", "service": "travel-assistant"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"服务不可用: {exc}") from exc
