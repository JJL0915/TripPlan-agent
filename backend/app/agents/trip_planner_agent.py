"""旅行计划智能体."""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timedelta
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from ..models.schemas import (
    Attraction,
    DayPlan,
    Location,
    Meal,
    TripPlan,
    TripRequest,
)
from ..services.amap_service import call_amap_tool, get_amap_mcp_tools
from ..services.llm_service import get_llm
from .prompts import (
    ATTRACTION_AGENT_PROMPT,
    HOTEL_AGENT_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    WEATHER_AGENT_PROMPT,
)


class TripPlannerState(TypedDict, total=False):
    request: TripRequest
    attraction_raw: str
    weather_raw: str
    hotel_raw: str
    attraction_summary: str
    weather_summary: str
    hotel_summary: str
    planner_result: str
    trip_plan: TripPlan
    error: str


class MultiAgentTripPlanner:
    """LangGraph multi-agent trip planning system."""

    def __init__(self):
        print("[LangGraph] Initializing multi-agent trip planner...")
        self.llm = get_llm()
        self.graph = None

    async def _ensure_graph(self):
        if self.graph is not None:
            return

        print("  - Loading Amap MCP tools for LangGraph nodes...")
        await get_amap_mcp_tools()

        builder = StateGraph(TripPlannerState)
        builder.add_node("attraction_tool", self._attraction_tool_node)
        builder.add_node("weather_tool", self._weather_tool_node)
        builder.add_node("hotel_tool", self._hotel_tool_node)
        builder.add_node("attraction_agent", self._attraction_agent_node)
        builder.add_node("weather_agent", self._weather_agent_node)
        builder.add_node("hotel_agent", self._hotel_agent_node)
        builder.add_node("planner", self._planner_node)

        builder.add_edge(START, "attraction_tool")
        builder.add_edge(START, "weather_tool")
        builder.add_edge(START, "hotel_tool")
        builder.add_edge("attraction_tool", "attraction_agent")
        builder.add_edge("weather_tool", "weather_agent")
        builder.add_edge("hotel_tool", "hotel_agent")
        builder.add_edge(
            ["attraction_agent", "weather_agent", "hotel_agent"], "planner"
        )
        builder.add_edge("planner", END)

        self.graph = builder.compile()
        print("[LangGraph] Trip planner initialized")

    async def aplan_trip(self, request: TripRequest) -> TripPlan:
        """Generate a trip plan asynchronously."""
        await self._ensure_graph()

        total_start = time.time()
        try:
            result = await self.graph.ainvoke({"request": request})
            trip_plan = result.get("trip_plan")
            if isinstance(trip_plan, TripPlan):
                print(
                    f"[LangGraph] Trip plan generated in {time.time() - total_start:.1f}s"
                )
                return trip_plan

            print("[LangGraph] Graph did not return a TripPlan, using fallback")
            return self._create_fallback_plan(request)

        except Exception as e:
            print(
                f"[LangGraph] Trip planning failed in {time.time() - total_start:.1f}s: {str(e)}"
            )
            import traceback

            traceback.print_exc()
            return self._create_fallback_plan(request)

    def plan_trip(self, request: TripRequest) -> TripPlan:
        """Sync compatibility wrapper for non-async callers."""
        return asyncio.run(self.aplan_trip(request))

    async def _attraction_tool_node(self, state: TripPlannerState) -> dict[str, str]:
        request = state["request"]
        keywords = self._build_attraction_keywords(request)
        start = time.time()
        result = await call_amap_tool(
            "maps_text_search",
            {
                "keywords": keywords,
                "city": request.city,
                "citylimit": "true",
            },
        )
        content = self._stringify_result(result)
        print(f"  [time] attraction tool: {time.time() - start:.1f}s")
        return {"attraction_raw": content}

    async def _weather_tool_node(self, state: TripPlannerState) -> dict[str, str]:
        request = state["request"]
        start = time.time()
        result = await call_amap_tool("maps_weather", {"city": request.city})
        content = self._stringify_result(result)
        print(f"  [time] weather tool: {time.time() - start:.1f}s")
        return {"weather_raw": content}

    async def _hotel_tool_node(self, state: TripPlannerState) -> dict[str, str]:
        request = state["request"]
        start = time.time()
        result = await call_amap_tool(
            "maps_text_search",
            {
                "keywords": f"{request.accommodation} 酒店",
                "city": request.city,
                "citylimit": "true",
            },
        )
        content = self._stringify_result(result)
        print(f"  [time] hotel tool: {time.time() - start:.1f}s")
        return {"hotel_raw": content}

    async def _attraction_agent_node(self, state: TripPlannerState) -> dict[str, str]:
        request = state["request"]
        prompt = self._build_sub_agent_query(request, state.get("attraction_raw", ""))
        start = time.time()
        response = await self.llm.ainvoke(
            [
                SystemMessage(content=ATTRACTION_AGENT_PROMPT),
                HumanMessage(content=prompt),
            ]
        )
        content = getattr(response, "content", str(response))
        print(f"  [time] attraction summary agent: {time.time() - start:.1f}s")
        return {"attraction_summary": content}

    async def _weather_agent_node(self, state: TripPlannerState) -> dict[str, str]:
        request = state["request"]
        prompt = self._build_sub_agent_query(request, state.get("weather_raw", ""))
        start = time.time()
        response = await self.llm.ainvoke(
            [
                SystemMessage(content=WEATHER_AGENT_PROMPT),
                HumanMessage(content=prompt),
            ]
        )
        content = getattr(response, "content", str(response))
        print(f"  [time] weather summary agent: {time.time() - start:.1f}s")
        return {"weather_summary": content}

    async def _hotel_agent_node(self, state: TripPlannerState) -> dict[str, str]:
        request = state["request"]
        prompt = self._build_sub_agent_query(request, state.get("hotel_raw", ""))
        start = time.time()
        response = await self.llm.ainvoke(
            [
                SystemMessage(content=HOTEL_AGENT_PROMPT),
                HumanMessage(content=prompt),
            ]
        )
        content = getattr(response, "content", str(response))
        print(f"  [time] hotel summary agent: {time.time() - start:.1f}s")
        return {"hotel_summary": content}

    async def _planner_node(self, state: TripPlannerState) -> dict[str, Any]:
        request = state["request"]
        query = self._build_planner_query(
            request,
            state.get("attraction_summary", ""),
            state.get("weather_summary", ""),
            state.get("hotel_summary", ""),
        )

        start = time.time()
        response = await self.llm.ainvoke(
            [
                SystemMessage(content=PLANNER_SYSTEM_PROMPT),
                HumanMessage(content=query),
            ]
        )
        content = getattr(response, "content", str(response))
        trip_plan = self._parse_response(content, request)
        print(f"  [time] planner agent: {time.time() - start:.1f}s")
        return {"planner_result": content, "trip_plan": trip_plan}

    def _build_attraction_keywords(self, request: TripRequest) -> str:
        if not request.preferences:
            return "景点"
        if len(request.preferences) > 1:
            return f"{request.preferences[0]} {request.preferences[1]}"
        return request.preferences[0]

    def _build_sub_agent_query(self, request: TripRequest, raw_result: str) -> str:
        return f"""用户旅行需求：
- 城市: {request.city}
- 日期: {request.start_date} 至 {request.end_date}
- 天数: {request.travel_days}
- 交通方式: {request.transportation}
- 住宿偏好: {request.accommodation}
- 偏好: {", ".join(request.preferences) if request.preferences else "无"}
- 额外要求: {request.free_text_input or "无"}

工具返回的真实数据：
{raw_result}
"""

    def _build_planner_query(
        self, request: TripRequest, attractions: str, weather: str, hotels: str = ""
    ) -> str:
        extra = (
            f"\n额外要求: {request.free_text_input}" if request.free_text_input else ""
        )
        return f"""请根据以下信息生成{request.city}的{request.travel_days}天旅行计划。

基本信息:
- 城市: {request.city}
- 日期: {request.start_date} 至 {request.end_date}
- 天数: {request.travel_days}
- 交通方式: {request.transportation}
- 住宿偏好: {request.accommodation}
- 偏好: {", ".join(request.preferences) if request.preferences else "无"}{extra}

景点推荐 Agent 总结:
{attractions}

天气分析 Agent 总结:
{weather}

酒店推荐 Agent 总结:
{hotels}
"""

    def _parse_response(self, response: str, request: TripRequest) -> TripPlan:
        try:
            json_str = self._extract_json(response)
            data = json.loads(json_str)
            data = self._normalize_trip_data(data)
            return TripPlan(**data)
        except Exception as e:
            print(f"[LangGraph] Failed to parse planner response: {str(e)}")
            return self._create_fallback_plan(request)

    @staticmethod
    def _extract_json(text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text)
            for block in reversed(blocks):
                candidate = block.strip()
                if candidate.startswith("{") and candidate.endswith("}"):
                    return candidate

        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return text[start : end + 1]

        raise ValueError("No JSON object found in planner response")

    @staticmethod
    def _stringify_result(result: Any) -> str:
        if isinstance(result, str):
            return result
        try:
            return json.dumps(result, ensure_ascii=False)
        except TypeError:
            return str(result)

    @staticmethod
    def _normalize_trip_data(data: dict[str, Any]) -> dict[str, Any]:
        """Coerce common LLM scalar type drift before Pydantic validation."""
        for day in data.get("days", []) or []:
            hotel = day.get("hotel")
            if isinstance(hotel, dict):
                for key in (
                    "name",
                    "address",
                    "price_range",
                    "rating",
                    "distance",
                    "type",
                ):
                    if hotel.get(key) is not None:
                        hotel[key] = str(hotel[key])

            for attraction in day.get("attractions", []) or []:
                if not isinstance(attraction, dict):
                    continue
                for key in ("name", "address", "description", "category"):
                    if attraction.get(key) is not None:
                        attraction[key] = str(attraction[key])

            for meal in day.get("meals", []) or []:
                if not isinstance(meal, dict):
                    continue
                for key in ("type", "name", "address", "description"):
                    if meal.get(key) is not None:
                        meal[key] = str(meal[key])

        for weather in data.get("weather_info", []) or []:
            if not isinstance(weather, dict):
                continue
            for key in (
                "date",
                "day_weather",
                "night_weather",
                "wind_direction",
                "wind_power",
            ):
                if weather.get(key) is not None:
                    weather[key] = str(weather[key])

        return data

    def _create_fallback_plan(self, request: TripRequest) -> TripPlan:
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")

        days = []
        for i in range(request.travel_days):
            current_date = start_date + timedelta(days=i)
            day_plan = DayPlan(
                date=current_date.strftime("%Y-%m-%d"),
                day_index=i,
                description=f"第{i + 1}天行程",
                transportation=request.transportation,
                accommodation=request.accommodation,
                attractions=[
                    Attraction(
                        name=f"{request.city}景点{j + 1}",
                        address=f"{request.city}市",
                        location=Location(
                            longitude=116.4 + i * 0.01 + j * 0.005,
                            latitude=39.9 + i * 0.01 + j * 0.005,
                        ),
                        visit_duration=120,
                        description=f"这是{request.city}的推荐景点。",
                        category="景点",
                    )
                    for j in range(2)
                ],
                meals=[
                    Meal(
                        type="breakfast",
                        name=f"第{i + 1}天早餐",
                        description="当地特色早餐",
                    ),
                    Meal(type="lunch", name=f"第{i + 1}天午餐", description="午餐推荐"),
                    Meal(
                        type="dinner", name=f"第{i + 1}天晚餐", description="晚餐推荐"
                    ),
                ],
            )
            days.append(day_plan)

        return TripPlan(
            city=request.city,
            start_date=request.start_date,
            end_date=request.end_date,
            days=days,
            weather_info=[],
            overall_suggestions=(
                f"这是为您规划的{request.city}{request.travel_days}日游兜底行程，"
                "建议出发前再次确认景点开放时间、门票和天气。"
            ),
        )


_multi_agent_planner: MultiAgentTripPlanner | None = None


def get_trip_planner_agent() -> MultiAgentTripPlanner:
    """Return shared LangGraph trip planner instance."""
    global _multi_agent_planner

    if _multi_agent_planner is None:
        _multi_agent_planner = MultiAgentTripPlanner()

    return _multi_agent_planner
