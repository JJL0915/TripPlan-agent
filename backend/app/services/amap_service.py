"""Amap MCP service wrappers built on LangChain MCP adapters."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from ..config import get_settings
from ..models.schemas import Location, POIInfo, RouteInfo, WeatherInfo

_amap_mcp_client: MultiServerMCPClient | None = None
_amap_mcp_tools: list[BaseTool] | None = None


def _build_amap_client() -> MultiServerMCPClient:
    settings = get_settings()
    if not settings.amap_api_key:
        raise ValueError("AMAP_API_KEY is not configured")

    uvx_executable = Path(sys.executable).with_name("uvx.exe")
    command = str(uvx_executable) if uvx_executable.exists() else "uvx"

    return MultiServerMCPClient(
        {
            "amap": {
                "command": command,
                "args": ["amap-mcp-server"],
                "transport": "stdio",
                "env": {"AMAP_MAPS_API_KEY": settings.amap_api_key},
            }
        }
    )


async def get_amap_mcp_tools() -> list[BaseTool]:
    """Return shared LangChain tools exposed by amap-mcp-server."""
    global _amap_mcp_client, _amap_mcp_tools

    if _amap_mcp_client is None:
        _amap_mcp_client = _build_amap_client()

    if _amap_mcp_tools is None:
        _amap_mcp_tools = await _amap_mcp_client.get_tools()
        print("[Amap MCP] Tools initialized")
        print(f"   Tool count: {len(_amap_mcp_tools)}")
        for tool in _amap_mcp_tools[:5]:
            print(f"     - {tool.name}")
        if len(_amap_mcp_tools) > 5:
            print(f"     ... {len(_amap_mcp_tools) - 5} more tools")

    return _amap_mcp_tools


def _find_tool(tools: list[BaseTool], tool_name: str) -> BaseTool:
    for tool in tools:
        if tool.name == tool_name or tool.name.endswith(tool_name):
            return tool

    available = ", ".join(tool.name for tool in tools)
    raise ValueError(f"Amap MCP tool '{tool_name}' not found. Available: {available}")


async def call_amap_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    """Call one amap MCP tool through its LangChain wrapper."""
    tools = await get_amap_mcp_tools()
    tool = _find_tool(tools, tool_name)
    return await tool.ainvoke(arguments)


def _stringify_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False)
    except TypeError:
        return str(result)


def _extract_json_object(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
    if not match:
        return None

    try:
        return json.loads(match.group(1))
    except Exception:
        return None


def _parse_location(value: Any) -> Optional[Location]:
    if not value:
        return None

    if isinstance(value, str):
        parts = value.split(",")
        if len(parts) != 2:
            return None
        try:
            return Location(longitude=float(parts[0]), latitude=float(parts[1]))
        except ValueError:
            return None

    if isinstance(value, dict):
        lng = value.get("longitude") or value.get("lng")
        lat = value.get("latitude") or value.get("lat")
        if lng is None or lat is None:
            return None
        try:
            return Location(longitude=float(lng), latitude=float(lat))
        except ValueError:
            return None

    return None


class AmapService:
    """Higher-level async service for Amap MCP tools."""

    async def search_poi(
        self, keywords: str, city: str, citylimit: bool = True
    ) -> list[POIInfo]:
        try:
            result = await call_amap_tool(
                "maps_text_search",
                {
                    "keywords": keywords,
                    "city": city,
                    "citylimit": str(citylimit).lower(),
                },
            )
            text = _stringify_result(result)
            print(f"POI search result: {text[:200]}...")

            data = _extract_json_object(text)
            pois = []
            raw_pois = []
            if isinstance(data, dict):
                raw_pois = data.get("pois") or data.get("data") or []
            elif isinstance(data, list):
                raw_pois = data

            for item in raw_pois:
                if not isinstance(item, dict):
                    continue
                location = _parse_location(item.get("location"))
                if not location:
                    continue
                pois.append(
                    POIInfo(
                        id=str(item.get("id") or item.get("poiid") or ""),
                        name=str(item.get("name") or ""),
                        type=str(item.get("type") or ""),
                        address=str(item.get("address") or ""),
                        location=location,
                        tel=item.get("tel"),
                    )
                )
            return pois

        except Exception as e:
            print(f"[Amap MCP] POI search failed: {str(e)}")
            return []

    async def get_weather(self, city: str) -> list[WeatherInfo]:
        try:
            result = await call_amap_tool("maps_weather", {"city": city})
            text = _stringify_result(result)
            print(f"Weather query result: {text[:200]}...")

            data = _extract_json_object(text)
            forecasts = []
            if isinstance(data, dict):
                forecasts = data.get("forecasts") or data.get("casts") or []
                if forecasts and isinstance(forecasts[0], dict):
                    forecasts = forecasts[0].get("casts") or forecasts

            weather = []
            for item in forecasts:
                if not isinstance(item, dict):
                    continue
                weather.append(
                    WeatherInfo(
                        date=str(item.get("date") or item.get("reporttime") or ""),
                        day_weather=str(item.get("dayweather") or item.get("day_weather") or ""),
                        night_weather=str(item.get("nightweather") or item.get("night_weather") or ""),
                        day_temp=item.get("daytemp") or item.get("day_temp") or 0,
                        night_temp=item.get("nighttemp") or item.get("night_temp") or 0,
                        wind_direction=str(item.get("daywind") or item.get("wind_direction") or ""),
                        wind_power=str(item.get("daypower") or item.get("wind_power") or ""),
                    )
                )
            return weather

        except Exception as e:
            print(f"[Amap MCP] Weather query failed: {str(e)}")
            return []

    async def plan_route(
        self,
        origin_address: str,
        destination_address: str,
        origin_city: Optional[str] = None,
        destination_city: Optional[str] = None,
        route_type: str = "walking",
    ) -> Optional[RouteInfo]:
        try:
            tool_map = {
                "walking": "maps_direction_walking_by_address",
                "driving": "maps_direction_driving_by_address",
                "transit": "maps_direction_transit_integrated_by_address",
            }
            tool_name = tool_map.get(route_type, "maps_direction_walking_by_address")

            arguments: dict[str, Any] = {
                "origin_address": origin_address,
                "destination_address": destination_address,
            }
            if origin_city:
                arguments["origin_city"] = origin_city
            if destination_city:
                arguments["destination_city"] = destination_city

            result = await call_amap_tool(tool_name, arguments)
            text = _stringify_result(result)
            print(f"Route planning result: {text[:200]}...")

            data = _extract_json_object(text)
            if isinstance(data, dict):
                route = data.get("route") or data
                paths = route.get("paths") if isinstance(route, dict) else None
                first_path = paths[0] if isinstance(paths, list) and paths else route
                if isinstance(first_path, dict):
                    return RouteInfo(
                        distance=float(first_path.get("distance") or 0),
                        duration=int(float(first_path.get("duration") or 0)),
                        route_type=route_type,
                        description=text[:500],
                    )

            return RouteInfo(
                distance=0,
                duration=0,
                route_type=route_type,
                description=text[:500],
            )

        except Exception as e:
            print(f"[Amap MCP] Route planning failed: {str(e)}")
            return None

    async def geocode(self, address: str, city: Optional[str] = None) -> Optional[Location]:
        try:
            arguments: dict[str, Any] = {"address": address}
            if city:
                arguments["city"] = city

            result = await call_amap_tool("maps_geo", arguments)
            text = _stringify_result(result)
            print(f"Geocode result: {text[:200]}...")

            data = _extract_json_object(text)
            if isinstance(data, dict):
                geocodes = data.get("geocodes") or data.get("data") or []
                if geocodes and isinstance(geocodes[0], dict):
                    return _parse_location(geocodes[0].get("location"))
            return None

        except Exception as e:
            print(f"[Amap MCP] Geocode failed: {str(e)}")
            return None

    async def get_poi_detail(self, poi_id: str) -> dict[str, Any]:
        try:
            result = await call_amap_tool("maps_search_detail", {"id": poi_id})
            text = _stringify_result(result)
            print(f"POI detail result: {text[:200]}...")

            data = _extract_json_object(text)
            if isinstance(data, dict):
                return data
            return {"raw": text}

        except Exception as e:
            print(f"[Amap MCP] Get POI detail failed: {str(e)}")
            return {}


_amap_service: AmapService | None = None


def get_amap_service() -> AmapService:
    """Return shared Amap service instance."""
    global _amap_service

    if _amap_service is None:
        _amap_service = AmapService()

    return _amap_service
