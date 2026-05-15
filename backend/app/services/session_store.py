"""内存版问答助手会话存储。

该模块通过 session_id 在后端维护对话状态。当前实现保持轻量和可替换，
后续可以在不大改 Agent 逻辑的前提下替换为 Redis 实现。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Optional

from ..models.schemas import AssistantMessage, TripPlan


class TripPlanVersionConflict(Exception):
    """当 TripPlan 写入基于过期版本时抛出。"""

    def __init__(self, expected_version: int, current_version: int):
        self.expected_version = expected_version
        self.current_version = current_version
        super().__init__(
            f"TripPlan version conflict: expected {expected_version}, current {current_version}"
        )


@dataclass
class AssistantSessionState:
    """后端维护的一次问答助手会话状态。"""

    session_id: str
    history: list[AssistantMessage] = field(default_factory=list)
    draft_trip_request: dict[str, Any] = field(default_factory=dict)
    current_trip_plan: Optional[TripPlan] = None
    plan_version: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class InMemoryAssistantSessionStore:
    """面向本地演示的线程安全内存会话存储。"""

    def __init__(self, max_history: int = 50):
        self._sessions: dict[str, AssistantSessionState] = {}
        self._lock = RLock()
        self._max_history = max_history

    def get_or_create_session(
        self, session_id: Optional[str] = None
    ) -> AssistantSessionState:
        with self._lock:
            clean_session_id = (session_id or "").strip() or self.create_session_id()
            state = self._sessions.get(clean_session_id)
            if state is None:
                state = AssistantSessionState(session_id=clean_session_id)
                self._sessions[clean_session_id] = state
            return self._copy_state(state)

    def create_session_id(self) -> str:
        return uuid.uuid4().hex

    def append_turn(self, session_id: str, user_message: str, assistant_reply: str) -> None:
        with self._lock:
            state = self._get_existing_or_new(session_id)
            if user_message:
                state.history.append(AssistantMessage(role="user", content=user_message))
            if assistant_reply:
                state.history.append(
                    AssistantMessage(role="assistant", content=assistant_reply)
                )
            if len(state.history) > self._max_history:
                state.history = state.history[-self._max_history :]
            state.updated_at = datetime.now(timezone.utc)

    def update_draft(self, session_id: str, draft: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            state = self._get_existing_or_new(session_id)
            state.draft_trip_request = dict(draft or {})
            state.updated_at = datetime.now(timezone.utc)
            return dict(state.draft_trip_request)

    def get_trip_plan(self, session_id: str) -> tuple[Optional[TripPlan], int]:
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return None, 0
            trip_plan = (
                state.current_trip_plan.model_copy(deep=True)
                if state.current_trip_plan
                else None
            )
            return trip_plan, state.plan_version

    def save_trip_plan(
        self,
        session_id: str,
        trip_plan: TripPlan,
        expected_version: Optional[int] = None,
    ) -> int:
        with self._lock:
            state = self._get_existing_or_new(session_id)
            if (
                expected_version is not None
                and expected_version != state.plan_version
            ):
                raise TripPlanVersionConflict(
                    expected_version=expected_version,
                    current_version=state.plan_version,
                )

            state.current_trip_plan = trip_plan.model_copy(deep=True)
            state.plan_version += 1
            state.updated_at = datetime.now(timezone.utc)
            return state.plan_version

    def snapshot(self, session_id: str) -> AssistantSessionState:
        with self._lock:
            return self._copy_state(self._get_existing_or_new(session_id))

    def _get_existing_or_new(self, session_id: str) -> AssistantSessionState:
        clean_session_id = (session_id or "").strip() or self.create_session_id()
        state = self._sessions.get(clean_session_id)
        if state is None:
            state = AssistantSessionState(session_id=clean_session_id)
            self._sessions[clean_session_id] = state
        return state

    @staticmethod
    def _copy_state(state: AssistantSessionState) -> AssistantSessionState:
        return AssistantSessionState(
            session_id=state.session_id,
            history=[message.model_copy(deep=True) for message in state.history],
            draft_trip_request=dict(state.draft_trip_request),
            current_trip_plan=(
                state.current_trip_plan.model_copy(deep=True)
                if state.current_trip_plan
                else None
            ),
            plan_version=state.plan_version,
            created_at=state.created_at,
            updated_at=state.updated_at,
        )


_assistant_session_store: InMemoryAssistantSessionStore | None = None


def get_assistant_session_store() -> InMemoryAssistantSessionStore:
    """返回共享的问答助手会话存储。"""
    global _assistant_session_store
    if _assistant_session_store is None:
        _assistant_session_store = InMemoryAssistantSessionStore()
    return _assistant_session_store
