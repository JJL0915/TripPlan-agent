"""Unsplash 图片服务。"""

from __future__ import annotations

import logging
from typing import List, Optional

import requests

from ..config import get_settings

logger = logging.getLogger(__name__)


class UnsplashService:
    """Unsplash 图片服务。"""

    def __init__(self):
        settings = get_settings()
        self.access_key = settings.unsplash_access_key
        self.base_url = "https://api.unsplash.com"

    def search_photos(self, query: str, per_page: int = 5) -> List[dict]:
        """搜索图片。外部图片服务失败时返回空列表，让业务继续降级运行。"""
        try:
            response = requests.get(
                f"{self.base_url}/search/photos",
                params={
                    "query": query,
                    "per_page": per_page,
                },
                headers={"Authorization": f"Client-ID {self.access_key}"},
                timeout=10,
            )
            response.raise_for_status()

            results = response.json().get("results", [])
            return [
                {
                    "id": photo.get("id"),
                    "url": photo.get("urls", {}).get("regular"),
                    "thumb": photo.get("urls", {}).get("thumb"),
                    "description": photo.get("description") or photo.get("alt_description"),
                    "photographer": photo.get("user", {}).get("name"),
                }
                for photo in results
            ]

        except requests.RequestException as exc:
            logger.warning(
                "Unsplash 图片搜索失败，已降级为空图片",
                extra={
                    "query": query,
                    "error_type": type(exc).__name__,
                    "status_code": getattr(getattr(exc, "response", None), "status_code", None),
                },
            )
            return []
        except Exception as exc:
            logger.exception(
                "Unsplash 图片搜索出现非预期异常，已降级为空图片",
                extra={"query": query, "error_type": type(exc).__name__},
            )
            return []

    def get_photo_url(self, query: str) -> Optional[str]:
        """获取单张图片 URL。"""
        photos = self.search_photos(query, per_page=1)
        if photos:
            return photos[0].get("url")
        return None


_unsplash_service = None


def get_unsplash_service() -> UnsplashService:
    """获取 Unsplash 服务单例。"""
    global _unsplash_service

    if _unsplash_service is None:
        _unsplash_service = UnsplashService()

    return _unsplash_service
