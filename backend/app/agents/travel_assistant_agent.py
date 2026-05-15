"""基于 LangChain 的行程问答与行程操作 Agent。"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import date, datetime
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from ..models.schemas import (
    AssistantChatRequest,
    AssistantChatResponse,
    TripPlan,
    TripRequest,
)
from ..services.llm_service import get_llm
from ..services.session_store import (
    AssistantSessionState,
    TripPlanVersionConflict,
    get_assistant_session_store,
)
from .prompts import ASSISTANT_SYSTEM_PROMPT, MODIFY_TRIP_PLAN_PROMPT
from .trip_planner_agent import get_trip_planner_agent

STREAMING_ASSISTANT_PROMPT = """你是智能旅行问答与行程操作助手。请用中文自然回答用户，并且必须遵守下面的输出协议：
1. 先直接输出给用户看的自然语言回复，这部分会被实时展示给用户。
2. 回复结束后，另起一行输出隐藏元数据，格式必须是：
<assistant_metadata>{"intent":"chat","draft_trip_request":{},"missing_fields":[],"should_generate_plan":false,"should_modify_plan":false,"modification_request":""}</assistant_metadata>
3. hidden metadata 必须是合法 JSON，不要使用 markdown 代码块。

你需要根据用户消息、历史对话、草稿需求和当前页面判断：
- 普通问答：intent=chat
- 收集旅行需求：intent=collect_requirements
- 用户要求生成计划且 city/start_date/end_date 完整：intent=generate_plan, should_generate_plan=true
- 结果页用户要求改行程：intent=modify_plan, should_modify_plan=true

draft_trip_request 结构：
{
  "city": "城市或空字符串",
  "start_date": "YYYY-MM-DD 或空字符串",
  "end_date": "YYYY-MM-DD 或空字符串",
  "travel_days": 1,
  "transportation": "公共交通 | 自驾 | 步行 | 混合",
  "accommodation": "经济型酒店 | 舒适型酒店 | 豪华酒店 | 民宿",
  "preferences": ["历史文化", "自然风光", "美食", "购物", "艺术", "休闲"],
  "free_text_input": "额外要求"
}

规则：
1. 如果信息不足，不要生成计划，missing_fields 写缺少字段，并在可见回复里追问。
2. 如果用户只是咨询，直接回答，不要生成或修改。
3. 日期必须尽量转成 YYYY-MM-DD。无法确定年份时结合当前日期推断未来日期。
4. 如果用户在结果页说替换、调整、减少预算、放慢节奏、不想要某景点等，识别为修改计划。
"""


BeforeActionCallback = Callable[[str], Awaitable[None]]


class TravelAssistantAgent:
    """处理问答、需求收集、行程生成和行程修改。"""

    async def achat(self, request: AssistantChatRequest) -> AssistantChatResponse:
        """非流式处理入口。"""
        parsed = await self.analyze_message(request)
        return await self.complete_response(request, parsed)

    async def analyze_message(self, request: AssistantChatRequest) -> Dict[str, Any]:
        """使用非流式 LLM 调用分析用户消息。"""
        response = await get_llm().ainvoke(
            [
                SystemMessage(content=ASSISTANT_SYSTEM_PROMPT),
                HumanMessage(
                    content=json.dumps(self._build_payload(request), ensure_ascii=False)
                ),
            ]
        )
        return self._extract_json(response.content)

    async def stream_analysis(
        self, request: AssistantChatRequest
    ) -> AsyncIterator[dict[str, Any]]:
        """流式输出可见回复，并在最后返回解析出的控制元数据。"""
        marker_start = "<assistant_metadata>"
        marker_end = "</assistant_metadata>"
        marker_tail = len(marker_start) - 1
        pending_text = ""
        metadata_text = ""
        metadata_started = False
        visible_reply = ""

        async for chunk in get_llm().astream(
            [
                SystemMessage(content=STREAMING_ASSISTANT_PROMPT),
                HumanMessage(
                    content=json.dumps(self._build_payload(request), ensure_ascii=False)
                ),
            ]
        ):
            text = chunk.content or ""
            if not text:
                continue

            if metadata_started:
                metadata_text += text
                continue

            combined = pending_text + text
            marker_index = combined.find(marker_start)
            if marker_index >= 0:
                visible_part = combined[:marker_index]
                if visible_part:
                    visible_reply += visible_part
                    yield {"event": "delta", "text": visible_part}
                metadata_started = True
                metadata_text += combined[marker_index + len(marker_start) :]
                pending_text = ""
                continue

            emit_length = max(len(combined) - marker_tail, 0)
            if emit_length:
                visible_part = combined[:emit_length]
                pending_text = combined[emit_length:]
                visible_reply += visible_part
                yield {"event": "delta", "text": visible_part}
            else:
                pending_text = combined

            await asyncio.sleep(0)

        if not metadata_started and pending_text:
            visible_reply += pending_text
            yield {"event": "delta", "text": pending_text}

        metadata_raw = metadata_text.split(marker_end, 1)[0].strip()
        parsed = (
            self._extract_json(metadata_raw)
            if metadata_raw
            else self._default_parsed(request)
        )
        yield {
            "event": "analysis_complete",
            "parsed": parsed,
            "visible_reply": visible_reply.strip(),
        }

    async def complete_response(
        self,
        request: AssistantChatRequest,
        parsed: Dict[str, Any],
        reply_override: Optional[str] = None,
        before_action: Optional[BeforeActionCallback] = None,
    ) -> AssistantChatResponse:
        """根据解析结果统一完成生成计划、修改计划或普通问答。"""
        store = get_assistant_session_store()
        state = self._get_session(request)
        decision = self._build_decision(request, parsed, state)
        reply = reply_override or parsed.get("reply") or "我已经收到你的需求。"

        response = self._build_response(state, decision, reply)
        store.update_draft(state.session_id, decision["draft"])

        action = ""
        try:
            if decision["should_modify"]:
                action = "modify"
                if before_action:
                    await before_action("我开始修改当前行程，完成后会刷新页面。")
                modified_plan = await self.modify_plan(
                    decision["current_trip_plan"],
                    parsed.get("modification_request") or request.message,
                )
                response.plan_version = store.save_trip_plan(
                    state.session_id,
                    modified_plan,
                    expected_version=decision["plan_version"],
                )
                response.should_modify_plan = True
                response.trip_plan = modified_plan
                response.message = "行程已修改"

            elif decision["should_generate"] and not decision["missing_fields"]:
                action = "generate"
                if before_action:
                    await before_action(
                        "我开始生成旅行计划，这一步需要查询景点、天气和酒店数据。"
                    )
                trip_request = self.build_trip_request(decision["draft"])
                trip_plan = await get_trip_planner_agent().aplan_trip(trip_request)
                response.plan_version = store.save_trip_plan(
                    state.session_id,
                    trip_plan,
                    expected_version=decision["plan_version"],
                )
                response.should_generate_plan = True
                response.trip_plan = trip_plan
                response.message = "旅行计划生成成功"

            elif decision["should_generate"] and decision["missing_fields"]:
                response.reply = reply_override or self.build_missing_reply(
                    decision["missing_fields"]
                )

        except TripPlanVersionConflict as exc:
            self._apply_version_conflict(response, exc, action)
        except Exception as exc:
            self._apply_action_error(response, exc, action)

        store.append_turn(state.session_id, request.message, response.reply)
        return response

    def get_action_status(
        self, request: AssistantChatRequest, parsed: Dict[str, Any]
    ) -> Optional[str]:
        """返回即将执行的耗时动作提示，用于流式接口提前告知用户。"""
        decision = self._build_decision(request, parsed)
        if decision["should_modify"]:
            return "我开始修改当前行程，完成后会刷新页面。"
        if decision["should_generate"] and not decision["missing_fields"]:
            return "我开始生成旅行计划，这一步需要查询景点、天气和酒店数据。"
        return None

    async def modify_plan(
        self, current_plan: Optional[TripPlan], modification_request: str
    ) -> TripPlan:
        """按用户要求修改当前行程。"""
        if current_plan is None:
            raise ValueError("当前没有可修改的旅行计划")

        response = await get_llm().ainvoke(
            [
                SystemMessage(content=MODIFY_TRIP_PLAN_PROMPT),
                HumanMessage(
                    content=json.dumps(
                        {
                            "modification_request": modification_request,
                            "current_trip_plan": current_plan.model_dump(),
                        },
                        ensure_ascii=False,
                    )
                ),
            ]
        )
        data = self._extract_json(response.content)
        return TripPlan(**data)

    def build_trip_request(self, draft: Dict[str, Any]) -> TripRequest:
        """根据草稿构造 TripRequest。"""
        return TripRequest(**self.normalize_draft(draft))

    def build_missing_reply(self, missing_fields: List[str]) -> str:
        """构造缺失字段追问。"""
        labels = {
            "city": "目的地城市",
            "start_date": "开始日期",
            "end_date": "结束日期",
        }
        missing = "、".join(labels.get(field, field) for field in missing_fields)
        return f"我还需要确认{missing}，确认后就可以直接帮你生成旅行计划。"

    def normalize_draft(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        """归一化行程草稿字段。"""
        normalized = {
            "city": str(draft.get("city") or "").strip(),
            "start_date": str(draft.get("start_date") or "").strip(),
            "end_date": str(draft.get("end_date") or "").strip(),
            "travel_days": draft.get("travel_days") or 1,
            "transportation": str(draft.get("transportation") or "公共交通").strip(),
            "accommodation": str(draft.get("accommodation") or "经济型酒店").strip(),
            "preferences": draft.get("preferences") or [],
            "free_text_input": str(draft.get("free_text_input") or "").strip(),
        }
        try:
            normalized["travel_days"] = int(normalized["travel_days"])
        except (TypeError, ValueError):
            normalized["travel_days"] = 1

        if normalized["start_date"] and normalized["end_date"]:
            try:
                start = datetime.strptime(normalized["start_date"], "%Y-%m-%d").date()
                end = datetime.strptime(normalized["end_date"], "%Y-%m-%d").date()
                normalized["travel_days"] = max((end - start).days + 1, 1)
            except ValueError:
                pass

        if not isinstance(normalized["preferences"], list):
            normalized["preferences"] = [str(normalized["preferences"])]

        return normalized

    def missing_required_fields(self, draft: Dict[str, Any]) -> List[str]:
        """返回生成计划所需但仍缺失的字段。"""
        required = ["city", "start_date", "end_date"]
        return [field for field in required if not draft.get(field)]

    def summarize_plan(self, plan: Optional[TripPlan]) -> Optional[Dict[str, Any]]:
        """将 TripPlan 压缩为适合问答上下文使用的摘要。"""
        if not plan:
            return None

        return {
            "city": plan.city,
            "start_date": plan.start_date,
            "end_date": plan.end_date,
            "overall_suggestions": plan.overall_suggestions,
            "days": [
                {
                    "date": day.date,
                    "day_index": day.day_index,
                    "description": day.description,
                    "attractions": [item.name for item in day.attractions],
                    "meals": [meal.name for meal in day.meals],
                    "hotel": day.hotel.name if day.hotel else None,
                }
                for day in plan.days
            ],
            "budget": plan.budget.model_dump() if plan.budget else None,
        }

    def _build_payload(self, request: AssistantChatRequest) -> Dict[str, Any]:
        state = self._get_session(request)
        history = state.history[-8:] or request.history[-8:]
        draft = state.draft_trip_request or request.draft_trip_request or {}
        current_trip_plan = state.current_trip_plan or request.current_trip_plan

        return {
            "page": request.page,
            "today": date.today().isoformat(),
            "message": request.message,
            "history": [m.model_dump() for m in history],
            "draft_trip_request": draft,
            "current_trip_plan_summary": self.summarize_plan(current_trip_plan),
        }

    def _build_decision(
        self,
        request: AssistantChatRequest,
        parsed: Dict[str, Any],
        state: Optional[AssistantSessionState] = None,
    ) -> Dict[str, Any]:
        state = state or self._get_session(request)
        draft = self.normalize_draft(
            parsed.get("draft_trip_request")
            or state.draft_trip_request
            or request.draft_trip_request
            or {}
        )
        current_trip_plan = state.current_trip_plan or request.current_trip_plan
        missing_fields = self.missing_required_fields(draft)
        intent = parsed.get("intent") or "chat"
        should_generate = (
            bool(parsed.get("should_generate_plan")) or intent == "generate_plan"
        )
        should_modify = (
            bool(parsed.get("should_modify_plan")) or intent == "modify_plan"
        ) and current_trip_plan is not None

        return {
            "draft": draft,
            "missing_fields": missing_fields,
            "intent": intent,
            "should_generate": should_generate,
            "should_modify": should_modify,
            "current_trip_plan": current_trip_plan,
            "plan_version": state.plan_version,
        }

    def _default_parsed(self, request: AssistantChatRequest) -> Dict[str, Any]:
        state = self._get_session(request)
        return {
            "intent": "chat",
            "draft_trip_request": state.draft_trip_request or request.draft_trip_request or {},
            "missing_fields": [],
            "should_generate_plan": False,
            "should_modify_plan": False,
            "modification_request": "",
        }

    def _get_session(self, request: AssistantChatRequest) -> AssistantSessionState:
        """获取会话并回填请求上的 session_id。"""
        state = get_assistant_session_store().get_or_create_session(request.session_id)
        request.session_id = state.session_id
        return state

    def _build_response(
        self,
        state: AssistantSessionState,
        decision: Dict[str, Any],
        reply: str,
    ) -> AssistantChatResponse:
        """根据决策结果构造基础响应。"""
        return AssistantChatResponse(
            success=True,
            session_id=state.session_id,
            message="assistant response",
            reply=reply,
            intent=decision["intent"],
            draft_trip_request=decision["draft"],
            missing_fields=decision["missing_fields"],
            should_generate_plan=False,
            should_modify_plan=False,
            plan_version=decision["plan_version"],
        )

    def _apply_version_conflict(
        self,
        response: AssistantChatResponse,
        exc: TripPlanVersionConflict,
        action: str,
    ) -> None:
        """把 TripPlan 乐观锁冲突转换为用户可读响应。"""
        response.success = False
        response.plan_version = exc.current_version
        if action == "modify":
            response.message = "行程版本已更新，请基于最新行程重新修改"
            response.reply = "当前行程刚刚被更新过，我没有覆盖最新版本。请刷新后再告诉我需要怎样调整。"
            return

        response.message = "行程版本已更新，请重新确认后生成"
        response.reply = "当前行程在生成过程中被更新过，我没有覆盖最新版本。请确认后再重新生成。"

    def _apply_action_error(
        self,
        response: AssistantChatResponse,
        exc: Exception,
        action: str,
    ) -> None:
        """把生成或修改异常转换为稳定响应。"""
        response.success = False
        if action == "modify":
            response.message = f"修改行程失败: {exc}"
            response.reply = "我理解你的修改要求了，但这次没有成功更新行程。你可以把修改目标说得更具体一点。"
            return

        response.message = f"生成旅行计划失败: {exc}"
        response.reply = "信息已经基本齐了，但生成旅行计划时失败了。请稍后再试，或者把需求简化后重新发送。"

    def _extract_json(self, text: str) -> Dict[str, Any]:
        content = text.strip()
        content = re.sub(r"^```(?:json)?", "", content).strip()
        content = re.sub(r"```$", "", content).strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise


_assistant_agent: TravelAssistantAgent | None = None


def get_travel_assistant_agent() -> TravelAssistantAgent:
    """返回共享的旅行问答助手实例。"""
    global _assistant_agent
    if _assistant_agent is None:
        _assistant_agent = TravelAssistantAgent()
    return _assistant_agent
