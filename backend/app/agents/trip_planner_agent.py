"""多智能体旅行规划系统"""

import json
from typing import Dict, Any, List
from hello_agents import SimpleAgent
from ..services.amap_service import get_amap_mcp_tool
from ..services.llm_service import get_llm
from ..models.schemas import (
    TripRequest,
    TripPlan,
    DayPlan,
    Attraction,
    Meal,
    WeatherInfo,
    Location,
    Hotel,
)

from .prompts import (
    ATTRACTION_AGENT_PROMPT,
    WEATHER_AGENT_PROMPT,
    HOTEL_AGENT_PROMPT,
    PLANNER_AGENT_PROMPT,
)


class MultiAgentTripPlanner:
    """多智能体旅行规划系统"""

    def __init__(self):
        """初始化多智能体系统"""
        print("🔄 开始初始化多智能体旅行规划系统...")

        try:

            self.llm = get_llm()

            # 创建共享的MCP工具(只创建一次)
            print("  - 创建共享MCP工具...")
            self.amap_tool = get_amap_mcp_tool()
            self.amap_tool.expandable = True

            # 创建景点搜索Agent
            print("  - 创建景点搜索Agent...")
            self.attraction_agent = SimpleAgent(
                name="景点搜索专家", llm=self.llm, system_prompt=ATTRACTION_AGENT_PROMPT
            )
            self.attraction_agent.add_tool(self.amap_tool)

            # 创建天气查询Agent
            print("  - 创建天气查询Agent...")
            self.weather_agent = SimpleAgent(
                name="天气查询专家", llm=self.llm, system_prompt=WEATHER_AGENT_PROMPT
            )
            self.weather_agent.add_tool(self.amap_tool)

            # 创建酒店推荐Agent
            print("  - 创建酒店推荐Agent...")
            self.hotel_agent = SimpleAgent(
                name="酒店推荐专家", llm=self.llm, system_prompt=HOTEL_AGENT_PROMPT
            )
            self.hotel_agent.add_tool(self.amap_tool)

            # 创建行程规划Agent(不需要工具)
            print("  - 创建行程规划Agent...")
            self.planner_agent = SimpleAgent(
                name="行程规划专家", llm=self.llm, system_prompt=PLANNER_AGENT_PROMPT
            )

            print(f"✅ 多智能体系统初始化成功")
            print(f"   景点搜索Agent: {len(self.attraction_agent.list_tools())} 个工具")
            print(f"   天气查询Agent: {len(self.weather_agent.list_tools())} 个工具")
            print(f"   酒店推荐Agent: {len(self.hotel_agent.list_tools())} 个工具")

        except Exception as e:
            print(f"❌ 多智能体系统初始化失败: {str(e)}")
            import traceback

            traceback.print_exc()
            raise

    def plan_trip(self, request: TripRequest) -> TripPlan:
        """
        使用多智能体协作生成旅行计划

        Args:
            request: 旅行请求

        Returns:
            旅行计划
        """
        import time

        total_start = time.time()

        try:
            # step1:景点搜索agent
            t0 = time.time()
            attraction_query = self._build_attraction_query(request)
            attraction_response = self.attraction_agent.run(attraction_query)
            print(f"  ⏱ 景点搜索耗时: {time.time() - t0:.1f}s")

            # step2:天气查询agent
            t0 = time.time()
            weather_query = f"请查询{request.city}的天气信息"
            weather_response = self.weather_agent.run(weather_query)
            print(f"  ⏱ 天气查询耗时: {time.time() - t0:.1f}s")

            # step3：酒店查询Agent
            t0 = time.time()
            hotel_query = f"请搜索{request.city}的{request.accommodation}酒店"
            hotel_response = self.hotel_agent.run(hotel_query)
            print(f"  ⏱ 酒店推荐耗时: {time.time() - t0:.1f}s")

            # step4: 行程规划Agent整合信息生成计划
            t0 = time.time()
            planner_query = self._build_planner_query(
                request, attraction_response, weather_response, hotel_response
            )
            planner_response = self.planner_agent.run(planner_query)
            print(f"  ⏱ 行程规划耗时: {time.time() - t0:.1f}s")

            # step5:解析最终计划
            t0 = time.time()
            trip_plan = self._parse_response(planner_response, request)
            print(f"  ⏱ 响应解析耗时: {time.time() - t0:.1f}s")

            total_elapsed = time.time() - total_start
            print(f"{'='*60}")
            print(f"✅ 旅行计划生成完成! 总耗时: {total_elapsed:.1f}s")
            print(f"{'='*60}\n")

            return trip_plan

        except Exception as e:
            total_elapsed = time.time() - total_start
            print(f"❌ 生成旅行计划失败 (耗时: {total_elapsed:.1f}s): {str(e)}")
            import traceback

            traceback.print_exc()
            return self._create_fallback_plan(request)

    def _build_attraction_query(self, request: TripRequest) -> str:
        """构建景点搜索查询 - 直接包含工具调用"""
        keywords = ""
        if not request.preferences:
            keywords = "景点"
        elif len(request.preferences) > 1:
            keywords = request.preferences[0] + "和" + request.preferences[1]
        else:
            keywords = request.preferences[0]

        query = f"请使用amap_maps_text_search工具搜索{request.city}的{keywords}相关景点。\n[TOOL_CALL:amap_maps_text_search:keywords={keywords},city={request.city}]"
        return query

    def _build_planner_query(
        self, request: TripRequest, attractions: str, weather: str, hotels: str = ""
    ) -> str:
        """构建行程规划查询"""
        query = f"""请根据以下信息生成{request.city}的{request.travel_days}天旅行计划:

**基本信息:**
- 城市: {request.city}
- 日期: {request.start_date} 至 {request.end_date}
- 天数: {request.travel_days}天
- 交通方式: {request.transportation}
- 住宿: {request.accommodation}
- 偏好: {', '.join(request.preferences) if request.preferences else '无'}

**景点信息:**
{attractions}

**天气信息:**
{weather}

**酒店信息:**
{hotels}

**要求:**
1. 每天安排2-3个景点
2. 每天必须包含早中晚三餐
3. 每天推荐一个具体的酒店(从酒店信息中选择)
3. 考虑景点之间的距离和交通方式
4. 返回完整的JSON格式数据
5. 景点的经纬度坐标要真实准确
"""
        if request.free_text_input:
            query += f"\n**额外要求:** {request.free_text_input}"

        return query

    def _parse_response(self, response: str, request: TripRequest) -> TripPlan:
        """
        解析Agent响应 (提取最后一个JSON代码块，避免被前序Agent输出干扰)

        Args:
            response: Agent响应文本
            request: 原始请求

        Returns:
            旅行计划
        """
        try:
            import re

            # 优先匹配 ```json ... ``` 代码块，取最后一个（规划Agent的输出）
            json_blocks = re.findall(r"```(?:json)?\s*\n?([\s\S]*?)```", response)
            if json_blocks:
                # 取最后一个JSON代码块（排除前序Agent的输出）
                for candidate in reversed(json_blocks):
                    candidate = candidate.strip()
                    if candidate.startswith("{") and candidate.endswith("}"):
                        json_str = candidate
                        break
                else:
                    json_str = json_blocks[-1].strip()
            elif "{" in response and "}" in response:
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                json_str = response[json_start:json_end]
            else:
                raise ValueError("响应中未找到JSON数据")

            data = json.loads(json_str)
            trip_plan = TripPlan(**data)
            return trip_plan
        except Exception as e:
            print(f"⚠️  解析响应失败: {str(e)}")
            print(f"   将使用备用方案生成计划")
            return self._create_fallback_plan(request)

    def _create_fallback_plan(self, request: TripRequest) -> TripPlan:
        """创建备用计划(当Agent失败时)"""
        from datetime import datetime, timedelta

        # 解析日期
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")

        # 创建每日行程
        days = []
        for i in range(request.travel_days):
            current_date = start_date + timedelta(days=i)

            day_plan = DayPlan(
                date=current_date.strftime("%Y-%m-%d"),
                day_index=i,
                description=f"第{i+1}天行程",
                transportation=request.transportation,
                accommodation=request.accommodation,
                attractions=[
                    Attraction(
                        name=f"{request.city}景点{j+1}",
                        address=f"{request.city}市",
                        location=Location(
                            longitude=116.4 + i * 0.01 + j * 0.005,
                            latitude=39.9 + i * 0.01 + j * 0.005,
                        ),
                        visit_duration=120,
                        description=f"这是{request.city}的著名景点",
                        category="景点",
                    )
                    for j in range(2)
                ],
                meals=[
                    Meal(
                        type="breakfast",
                        name=f"第{i+1}天早餐",
                        description="当地特色早餐",
                    ),
                    Meal(type="lunch", name=f"第{i+1}天午餐", description="午餐推荐"),
                    Meal(type="dinner", name=f"第{i+1}天晚餐", description="晚餐推荐"),
                ],
            )
            days.append(day_plan)

        return TripPlan(
            city=request.city,
            start_date=request.start_date,
            end_date=request.end_date,
            days=days,
            weather_info=[],
            overall_suggestions=f"这是为您规划的{request.city}{request.travel_days}日游行程,建议提前查看各景点的开放时间。",
        )


# 全局多智能体系统示例
_multi_agent_planner = None


def get_trip_planner_agent() -> MultiAgentTripPlanner:
    """获取多智能体旅行规划系统实例"""
    global _multi_agent_planner

    if _multi_agent_planner is None:
        _multi_agent_planner = MultiAgentTripPlanner()

    return _multi_agent_planner
