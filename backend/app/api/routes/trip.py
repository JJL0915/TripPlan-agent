"""旅行规划接口。"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException

from ...agents.trip_planner_agent import get_trip_planner_agent
from ...models.schemas import TripPlanResponse, TripRequest
from ...services.session_store import (
    TripPlanVersionConflict,
    get_assistant_session_store,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trip", tags=["旅行规划"])


@router.post(
    "/plan",
    response_model=TripPlanResponse,
    summary="生成旅行计划",
    description="根据用户输入的旅行需求生成详细旅行计划。",
)
async def plan_trip(request: TripRequest):
    """生成旅行计划。"""
    start = time.perf_counter()
    logger.info(
        "收到旅行规划请求",
        extra={
            "city": request.city,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "travel_days": request.travel_days,
            "transportation": request.transportation,
            "accommodation": request.accommodation,
            "preferences": request.preferences,
        },
    )

    try:
        session_store = get_assistant_session_store()
        session_state = session_store.get_or_create_session(request.session_id)
        agent = get_trip_planner_agent()
        trip_plan = await agent.aplan_trip(request)
        plan_version = session_store.save_trip_plan(
            session_state.session_id,
            trip_plan,
            expected_version=request.base_plan_version,
        )
        session_store.update_draft(
            session_state.session_id,
            {
                "city": request.city,
                "start_date": request.start_date,
                "end_date": request.end_date,
                "travel_days": request.travel_days,
                "transportation": request.transportation,
                "accommodation": request.accommodation,
                "preferences": request.preferences,
                "free_text_input": request.free_text_input or "",
            },
        )

        logger.info(
            "旅行规划请求处理完成",
            extra={
                "city": trip_plan.city,
                "days_count": len(trip_plan.days),
                "session_id": session_state.session_id,
                "plan_version": plan_version,
                "duration_ms": round((time.perf_counter() - start) * 1000, 2),
            },
        )
        return TripPlanResponse(
            success=True,
            message="旅行计划生成成功",
            data=trip_plan,
            session_id=session_state.session_id,
            plan_version=plan_version,
        )

    except TripPlanVersionConflict as exc:
        logger.warning(
            "旅行规划保存版本冲突",
            extra={
                "city": request.city,
                "expected_version": exc.expected_version,
                "current_version": exc.current_version,
            },
        )
        raise HTTPException(
            status_code=409,
            detail={
                "message": "行程版本已更新，请刷新后重新生成",
                "current_version": exc.current_version,
            },
        ) from exc
    except Exception as exc:
        logger.exception(
            "旅行规划请求处理失败",
            extra={
                "city": request.city,
                "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                "error": str(exc),
            },
        )
        raise HTTPException(status_code=500, detail=f"生成旅行计划失败: {exc}") from exc


@router.get("/health", summary="健康检查", description="检查旅行规划服务是否正常")
async def health_check():
    """旅行规划服务健康检查。"""
    try:
        get_trip_planner_agent()
        return {
            "status": "healthy",
            "service": "trip-planner",
        }
    except Exception as exc:
        logger.exception("旅行规划服务健康检查失败", extra={"error": str(exc)})
        raise HTTPException(status_code=503, detail=f"服务不可用: {exc}") from exc
