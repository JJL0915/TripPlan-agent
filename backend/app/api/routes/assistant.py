"""行程问答助手接口。"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ...agents.travel_assistant_agent import get_travel_assistant_agent
from ...models.schemas import AssistantChatRequest, AssistantChatResponse

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


@router.get("/health", summary="健康检查", description="检查行程问答助手是否正常")
async def health_check():
    """行程问答助手健康检查。"""
    try:
        get_travel_assistant_agent()
        return {"status": "healthy", "service": "travel-assistant"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"服务不可用: {exc}") from exc
