"""旅行规划API路由"""

from fastapi import APIRouter, HTTPException
from ...models.schemas import TripRequest, TripPlanResponse, ErrorResponse
from ...agents.trip_planner_agent import get_trip_planner_agent


router = APIRouter(prefix="/trip", tags=["旅游计划"])


@router.post(
    "/plan",
    response_model=TripPlanResponse,
    summary="生成旅行计划",
    description="根据用户输出的旅游需求，生成详细的旅游嘉华",
)
async def plan_trip(request: TripRequest):
    """
    生成旅行计划

    Args:
        request: 旅行请求参数

    Returns:
        旅行计划响应
    """
    try:
        print(f"\n{'='*60}")
        print(f"📥 收到旅行规划请求:")
        print(f"   城市: {request.city}")
        print(f"   日期: {request.start_date} - {request.end_date}")
        print(f"   天数: {request.travel_days}")
        print(f"{'='*60}\n")
        # 获取Agent实例
        print("🔄 获取多智能体系统实例...")
        agent = get_trip_planner_agent()
        # 生成旅行计划
        print("🚀 开始生成旅行计划...")
        trip_plan = agent.plan_trip(request)
        print(f"✅ 旅行计划生成成功")
        print(f"   trip_plan 类型: {type(trip_plan)}")
        print(f"   trip_plan is None: {trip_plan is None}")
        if trip_plan is not None:
            print(f"   城市: {trip_plan.city}")
            print(f"   天数: {len(trip_plan.days)}")
            print(f"   budget: {trip_plan.budget}")
        print(f"   准备返回响应\n")

        response = TripPlanResponse(
            success=True, message="旅行计划生成成功", data=trip_plan
        )
        print(f"   响应 data 字段: {response.data is not None}")
        return response

    except Exception as e:
        print(f"❌ 生成旅行计划失败: {str(e)}")
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"生成旅行计划失败: {str(e)}")


@router.get("/health", summary="健康检查", description="检查旅行规划服务是否正常")
async def health_check():
    """健康检查"""
    try:
        # 检查Agent是否可用
        agent = get_trip_planner_agent()

        return {
            "status": "healthy",
            "service": "trip-planner",
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"服务不可用: {str(e)}")
