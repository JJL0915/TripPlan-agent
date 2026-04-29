"""LLM service built on LangChain."""

import os

from langchain_openai import ChatOpenAI

from ..config import get_settings

_llm_instance: ChatOpenAI | None = None


def get_llm() -> ChatOpenAI:
    """Return a shared LangChain chat model instance."""
    global _llm_instance

    if _llm_instance is None:
        settings = get_settings()

        api_key = (
            os.getenv("LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or settings.openai_api_key
        )
        base_url = (
            os.getenv("LLM_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or settings.openai_base_url
        )
        model = (
            os.getenv("LLM_MODEL_ID")
            or os.getenv("OPENAI_MODEL")
            or settings.openai_model
        )

        kwargs = {
            "model": model,
            "temperature": 0.2,
            "timeout": 180,
            "max_retries": 2,
        }
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url

        _llm_instance = ChatOpenAI(**kwargs)

        print("[LangChain] LLM service initialized")
        print(f"   Base URL: {base_url}")
        print(f"   Model: {model}")

    return _llm_instance


def reset_llm():
    """Reset the shared LLM instance."""
    global _llm_instance
    _llm_instance = None
