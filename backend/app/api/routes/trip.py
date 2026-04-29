"""Trip planning API routes."""

from fastapi import APIRouter, HTTPException

from ...agents.trip_planner_agent import get_trip_planner_agent
from ...models.schemas import TripPlanResponse, TripRequest

router = APIRouter(prefix="/trip", tags=["旅行规划"])


@router.post(
    "/plan",
    response_model=TripPlanResponse,
    summary="生成旅行计划",
    description="根据用户输入的旅行需求生成详细旅行计划。",
)
async def plan_trip(request: TripRequest):
    """Generate a trip plan."""
    try:
        print(f"\n{'=' * 60}")
        print("收到旅行规划请求:")
        print(f"   城市: {request.city}")
        print(f"   日期: {request.start_date} - {request.end_date}")
        print(f"   天数: {request.travel_days}")
        print(f"{'=' * 60}\n")

        print("获取多智能体系统实例...")
        agent = get_trip_planner_agent()

        print("开始生成旅行计划...")
        trip_plan = await agent.aplan_trip(request)
        print("旅行计划生成成功")
        print(f"   trip_plan type: {type(trip_plan)}")
        print(f"   city: {trip_plan.city}")
        print(f"   days: {len(trip_plan.days)}")

        return TripPlanResponse(success=True, message="旅行计划生成成功", data=trip_plan)

    except Exception as e:
        print(f"[ERROR] 生成旅行计划失败: {str(e)}")
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"生成旅行计划失败: {str(e)}")


@router.get("/health", summary="健康检查", description="检查旅行规划服务是否正常")
async def health_check():
    """Health check for trip planner."""
    try:
        get_trip_planner_agent()
        return {
            "status": "healthy",
            "service": "trip-planner",
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"服务不可用: {str(e)}")
