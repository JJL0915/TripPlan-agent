"""应用配置。"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

backend_env = Path(__file__).parent.parent / ".env"
if backend_env.exists():
    load_dotenv(backend_env)
load_dotenv()

shared_env = Path(__file__).parent.parent.parent.parent / "HelloAgents" / ".env"
if shared_env.exists():
    load_dotenv(shared_env, override=False)


class Settings(BaseSettings):
    """应用配置项。"""

    app_name: str = "LangGraph智能旅行助手"
    app_version: str = "1.0.0"
    debug: bool = False

    host: str = "0.0.0.0"
    port: int = 8000

    cors_origins: str = (
        "http://localhost:5173,http://localhost:3000,"
        "http://127.0.0.1:5173,http://127.0.0.1:3000"
    )

    amap_api_key: str = ""

    unsplash_access_key: str = ""
    unsplash_secret_key: str = ""

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4"

    log_level: str = "INFO"

    class Config:
        env_file = str(Path(__file__).parent.parent / ".env")
        case_sensitive = False
        extra = "ignore"

    def get_cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]


settings = Settings()


def get_settings() -> Settings:
    return settings


def validate_config():
    """验证必要配置是否完整。"""
    errors = []
    warnings = []

    if not settings.amap_api_key:
        errors.append("AMAP_API_KEY 未配置")

    llm_api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not llm_api_key:
        warnings.append("LLM_API_KEY 或 OPENAI_API_KEY 未配置，LLM 功能可能不可用")

    if errors:
        raise ValueError("配置错误:\n" + "\n".join(f"  - {e}" for e in errors))

    for warning in warnings:
        logger.warning("配置警告", extra={"warning": warning})

    return True


def print_config():
    """记录当前配置，敏感信息只输出是否已配置。"""
    llm_api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    llm_base_url = os.getenv("LLM_BASE_URL") or settings.openai_base_url
    llm_model = os.getenv("LLM_MODEL_ID") or settings.openai_model

    logger.info(
        "应用配置已加载",
        extra={
            "app_name": settings.app_name,
            "app_version": settings.app_version,
            "host": settings.host,
            "port": settings.port,
            "amap_api_key_configured": bool(settings.amap_api_key),
            "llm_api_key_configured": bool(llm_api_key),
            "llm_base_url": llm_base_url,
            "llm_model": llm_model,
            "log_level": settings.log_level,
        },
    )
