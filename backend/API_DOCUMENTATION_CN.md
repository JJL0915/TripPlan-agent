# TripAgent 后端接口文档

## 1. 后端整体逻辑

后端基于 FastAPI 实现，入口文件是 `app/api/main.py`。应用启动时会读取配置、校验高德地图 Key，并注册三组业务路由：

- `/api/trip`：智能行程规划接口。
- `/api/map`：地图基础能力接口，包括 POI、天气、路线。
- `/api/poi`：POI 详情和景点图片接口。

核心分层如下：

- `app/api/routes/*.py`：HTTP 路由层，负责接收请求、参数校验、调用服务或 Agent、包装响应。
- `app/models/schemas.py`：Pydantic 请求和响应模型。
- `app/agents/trip_planner_agent.py`：多 Agent 行程规划核心逻辑。
- `app/services/amap_service.py`：高德地图 MCP 工具封装。
- `app/services/llm_service.py`：HelloAgentsLLM 单例封装。
- `app/services/unsplash_service.py`：Unsplash 图片搜索封装。
- `app/config.py`：环境变量和启动配置。

## 2. 核心调用链

### 2.1 行程规划主链路

`POST /api/trip/plan`

1. `plan_trip()` 接收 `TripRequest`。
2. 调用 `get_trip_planner_agent()` 获取全局 `MultiAgentTripPlanner` 单例。
3. `MultiAgentTripPlanner.plan_trip()` 顺序执行四个 Agent：
   - `attraction_agent.run()`：景点搜索 Agent，调用高德 MCP 的 `maps_text_search`。
   - `weather_agent.run()`：天气查询 Agent，调用高德 MCP 的 `maps_weather`。
   - `hotel_agent.run()`：酒店推荐 Agent，调用高德 MCP 的 `maps_text_search`。
   - `planner_agent.run()`：行程整合 Agent，不直接调用工具，只使用 LLM 整合前三步结果并生成 JSON。
4. `_parse_response()` 从 LLM 响应中提取 JSON，并反序列化为 `TripPlan`。
5. 如果 Agent 调用或 JSON 解析失败，则 `_create_fallback_plan()` 生成兜底行程结构。
6. 路由层包装成 `TripPlanResponse` 返回。

### 2.2 地图服务链路

`/api/map/*` 和 `/api/poi/*` 会调用 `get_amap_service()` 获取 `AmapService` 单例。`AmapService` 内部通过 `MCPTool` 启动 `uvx amap-mcp-server`，并使用 `mcp_tool.run()` 调用具体高德 MCP 工具。

当前封装的方法：

| 方法 | 底层 MCP 工具 | 用途 |
| --- | --- | --- |
| `search_poi()` | `maps_text_search` | 按关键词搜索 POI |
| `get_weather()` | `maps_weather` | 查询城市天气 |
| `plan_route()` | `maps_direction_walking_by_address` / `maps_direction_driving_by_address` / `maps_direction_transit_integrated_by_address` | 路线规划 |
| `geocode()` | `maps_geo` | 地址转经纬度 |
| `get_poi_detail()` | `maps_search_detail` | 查询 POI 详情 |

注意：`search_poi()`、`get_weather()`、`plan_route()` 当前已经调用 MCP，但返回值解析仍是 TODO，所以接口目前可能返回空数组或空对象。`get_poi_detail()` 会尝试从 MCP 返回文本中提取 JSON。

## 3. 公共响应和错误

成功响应通常为：

```json
{
  "success": true,
  "message": "操作成功",
  "data": {}
}
```

异常时路由层抛出 `HTTPException`：

- 普通业务异常：`500`
- 健康检查不可用：`503`
- Pydantic 参数校验失败：FastAPI 自动返回 `422`

## 4. 系统接口

### 4.1 获取服务信息

`GET /`

用途：返回应用基础信息。

调用函数：`root()`

响应示例：

```json
{
  "name": "HelloAgents智能旅行助手",
  "version": "1.0.0",
  "status": "running",
  "docs": "/docs",
  "redoc": "/redoc"
}
```

### 4.2 全局健康检查

`GET /health`

用途：检查 FastAPI 服务是否存活。

调用函数：`health()`

响应示例：

```json
{
  "status": "healthy",
  "service": "HelloAgents智能旅行助手",
  "version": "1.0.0"
}
```

## 5. 旅行规划接口

### 5.1 生成旅行计划

`POST /api/trip/plan`

用途：根据目的地、日期、交通、住宿偏好和兴趣标签，生成多日旅行计划。

调用函数：

- 路由：`plan_trip()`
- Agent 单例：`get_trip_planner_agent()`
- 核心规划：`MultiAgentTripPlanner.plan_trip()`
- 查询构造：`_build_attraction_query()`、`_build_planner_query()`
- 响应解析：`_parse_response()`
- 兜底方案：`_create_fallback_plan()`

请求体 `TripRequest`：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `city` | string | 是 | 目的地城市 |
| `start_date` | string | 是 | 开始日期，格式 `YYYY-MM-DD` |
| `end_date` | string | 是 | 结束日期，格式 `YYYY-MM-DD` |
| `travel_days` | integer | 是 | 旅行天数，范围 1-30 |
| `transportation` | string | 是 | 交通方式 |
| `accommodation` | string | 是 | 住宿偏好 |
| `preferences` | string[] | 否 | 偏好标签，如历史文化、美食 |
| `free_text_input` | string | 否 | 额外需求 |

请求示例：

```json
{
  "city": "北京",
  "start_date": "2026-05-01",
  "end_date": "2026-05-03",
  "travel_days": 3,
  "transportation": "公共交通",
  "accommodation": "经济型酒店",
  "preferences": ["历史文化", "美食"],
  "free_text_input": "希望多安排博物馆"
}
```

响应体 `TripPlanResponse`：

```json
{
  "success": true,
  "message": "旅行计划生成成功",
  "data": {
    "city": "北京",
    "start_date": "2026-05-01",
    "end_date": "2026-05-03",
    "days": [
      {
        "date": "2026-05-01",
        "day_index": 0,
        "description": "第1天行程概述",
        "transportation": "公共交通",
        "accommodation": "经济型酒店",
        "hotel": {
          "name": "酒店名称",
          "address": "酒店地址",
          "location": { "longitude": 116.397128, "latitude": 39.916527 },
          "price_range": "300-500元",
          "rating": "4.5",
          "distance": "距离景点2公里",
          "type": "经济型酒店",
          "estimated_cost": 400
        },
        "attractions": [
          {
            "name": "故宫博物院",
            "address": "北京市东城区景山前街4号",
            "location": { "longitude": 116.397128, "latitude": 39.916527 },
            "visit_duration": 180,
            "description": "景点描述",
            "category": "历史文化",
            "rating": 4.8,
            "image_url": null,
            "ticket_price": 60
          }
        ],
        "meals": [
          {
            "type": "lunch",
            "name": "午餐推荐",
            "address": "餐厅地址",
            "location": null,
            "description": "餐饮描述",
            "estimated_cost": 80
          }
        ]
      }
    ],
    "weather_info": [
      {
        "date": "2026-05-01",
        "day_weather": "晴",
        "night_weather": "多云",
        "day_temp": 25,
        "night_temp": 15,
        "wind_direction": "南风",
        "wind_power": "1-3级"
      }
    ],
    "overall_suggestions": "整体旅行建议",
    "budget": {
      "total_attractions": 180,
      "total_hotels": 1200,
      "total_meals": 600,
      "total_transportation": 200,
      "total": 2180
    }
  }
}
```

### 5.2 旅行规划服务健康检查

`GET /api/trip/health`

用途：检查旅行规划 Agent 是否可初始化。

调用函数：

- `health_check()`
- `get_trip_planner_agent()`

响应示例：

```json
{
  "status": "healthy",
  "service": "trip-planner"
}
```

## 6. 地图服务接口

### 6.1 搜索 POI

`GET /api/map/poi`

用途：根据关键词和城市搜索兴趣点。

调用函数：

- 路由：`search_poi()`
- 服务单例：`get_amap_service()`
- 服务方法：`AmapService.search_poi()`
- MCP 工具：`maps_text_search`

Query 参数：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `keywords` | string | 是 | 无 | 搜索关键词 |
| `city` | string | 是 | 无 | 城市 |
| `citylimit` | boolean | 否 | `true` | 是否限制在城市范围内 |

请求示例：

```http
GET /api/map/poi?keywords=故宫&city=北京&citylimit=true
```

响应体 `POISearchResponse`：

```json
{
  "success": true,
  "message": "POI搜索成功",
  "data": [
    {
      "id": "B000A8UIN8",
      "name": "故宫博物院",
      "type": "风景名胜",
      "address": "北京市东城区景山前街4号",
      "location": { "longitude": 116.397128, "latitude": 39.916527 },
      "tel": "010-85007421"
    }
  ]
}
```

当前实现注意：服务方法暂未解析 MCP 返回结果，实际可能返回 `data: []`。

### 6.2 查询天气

`GET /api/map/weather`

用途：查询指定城市天气。

调用函数：

- 路由：`get_weather()`
- 服务单例：`get_amap_service()`
- 服务方法：`AmapService.get_weather()`
- MCP 工具：`maps_weather`

Query 参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `city` | string | 是 | 城市名称 |

请求示例：

```http
GET /api/map/weather?city=北京
```

响应体 `WeatherResponse`：

```json
{
  "success": true,
  "message": "天气查询成功",
  "data": [
    {
      "date": "2026-05-01",
      "day_weather": "晴",
      "night_weather": "多云",
      "day_temp": 25,
      "night_temp": 15,
      "wind_direction": "南风",
      "wind_power": "1-3级"
    }
  ]
}
```

当前实现注意：服务方法暂未解析 MCP 返回结果，实际可能返回 `data: []`。

### 6.3 路线规划

`POST /api/map/route`

用途：规划起点和终点之间的路线，支持步行、驾车、公交。

调用函数：

- 路由：`plan_route()`
- 服务单例：`get_amap_service()`
- 服务方法：`AmapService.plan_route()`
- MCP 工具：
  - `walking` -> `maps_direction_walking_by_address`
  - `driving` -> `maps_direction_driving_by_address`
  - `transit` -> `maps_direction_transit_integrated_by_address`

请求体 `RouteRequest`：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `origin_address` | string | 是 | 无 | 起点地址 |
| `destination_address` | string | 是 | 无 | 终点地址 |
| `origin_city` | string | 否 | `null` | 起点城市 |
| `destination_city` | string | 否 | `null` | 终点城市 |
| `route_type` | string | 否 | `walking` | `walking`、`driving` 或 `transit` |

请求示例：

```json
{
  "origin_address": "北京市东城区景山前街4号",
  "destination_address": "北京市东城区天安门广场",
  "origin_city": "北京",
  "destination_city": "北京",
  "route_type": "walking"
}
```

响应体 `RouteResponse`：

```json
{
  "success": true,
  "message": "路线规划成功",
  "data": {
    "distance": 1500,
    "duration": 1200,
    "route_type": "walking",
    "description": "步行约1.5公里，预计20分钟"
  }
}
```

当前实现注意：服务方法暂未解析 MCP 返回结果，实际可能返回 `data: {}`，且该空对象不满足 `RouteInfo` 的完整字段要求，运行时可能触发响应模型校验问题。

### 6.4 地图服务健康检查

`GET /api/map/health`

用途：检查高德 MCP 工具是否可初始化，并返回可用工具数量。

调用函数：

- `health_check()`
- `get_amap_service()`

响应示例：

```json
{
  "status": "healthy",
  "service": "map-service",
  "mcp_tools_count": 7
}
```

## 7. POI 接口

### 7.1 获取 POI 详情

`GET /api/poi/detail/{poi_id}`

用途：根据 POI ID 获取 POI 详情。

调用函数：

- 路由：`get_poi_detail()`
- 服务单例：`get_amap_service()`
- 服务方法：`AmapService.get_poi_detail()`
- MCP 工具：`maps_search_detail`

Path 参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `poi_id` | string | 是 | 高德 POI ID |

请求示例：

```http
GET /api/poi/detail/B000A8UIN8
```

响应示例：

```json
{
  "success": true,
  "message": "获取POI详情成功",
  "data": {
    "id": "B000A8UIN8",
    "name": "故宫博物院",
    "address": "北京市东城区景山前街4号"
  }
}
```

### 7.2 搜索 POI 简化接口

`GET /api/poi/search`

用途：POI 搜索的简化入口，默认城市为北京。

调用函数：

- 路由：`search_poi()`
- 服务单例：`get_amap_service()`
- 服务方法：`AmapService.search_poi()`
- MCP 工具：`maps_text_search`

Query 参数：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `keywords` | string | 是 | 无 | 搜索关键词 |
| `city` | string | 否 | `北京` | 城市 |

请求示例：

```http
GET /api/poi/search?keywords=故宫&city=北京
```

响应示例：

```json
{
  "success": true,
  "message": "搜索成功",
  "data": []
}
```

当前实现注意：底层 `AmapService.search_poi()` 暂未解析 MCP 返回结果，实际通常返回空数组。

### 7.3 获取景点图片

`GET /api/poi/photo`

用途：根据景点名称从 Unsplash 搜索图片。

调用函数：

- 路由：`get_attraction_photo()`
- 服务单例：`get_unsplash_service()`
- 服务方法：`UnsplashService.get_photo_url()`
- 底层 HTTP：`GET https://api.unsplash.com/search/photos`

Query 参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `name` | string | 是 | 景点名称 |

内部逻辑：

1. 优先搜索 `"{name} China landmark"`。
2. 如果没有结果，降级搜索 `name`。
3. 返回第一张图片的 `regular` URL。

请求示例：

```http
GET /api/poi/photo?name=故宫博物院
```

响应示例：

```json
{
  "success": true,
  "message": "获取图片成功",
  "data": {
    "name": "故宫博物院",
    "photo_url": "https://images.unsplash.com/photo-xxx"
  }
}
```

## 8. 配置项

配置在 `app/config.py` 中定义，通过 `.env` 或环境变量读取。

| 配置字段 | 环境变量 | 是否关键 | 说明 |
| --- | --- | --- | --- |
| `amap_api_key` | `AMAP_API_KEY` | 是 | 高德地图 API Key，启动时强校验 |
| `unsplash_access_key` | `UNSPLASH_ACCESS_KEY` | 否 | Unsplash Access Key |
| `unsplash_secret_key` | `UNSPLASH_SECRET_KEY` | 否 | Unsplash Secret Key |
| `openai_api_key` | `OPENAI_API_KEY` 或 `LLM_API_KEY` | 否 | LLM Key，缺失时启动只警告 |
| `openai_base_url` | `OPENAI_BASE_URL` 或 `LLM_BASE_URL` | 否 | LLM API 地址 |
| `openai_model` | `OPENAI_MODEL` 或 `LLM_MODEL_ID` | 否 | LLM 模型名 |
| `host` | `HOST` | 否 | 默认 `0.0.0.0` |
| `port` | `PORT` | 否 | 默认 `8000` |
| `cors_origins` | `CORS_ORIGINS` | 否 | 代码当前固定允许 `http://localhost:5173` |

## 9. 当前实现风险和后续建议

- `AmapService.search_poi()`、`get_weather()`、`plan_route()` 还没有把 MCP 返回文本解析成 Pydantic 模型，地图类接口目前更像“已接通工具，但未完成结构化输出”。
- `TripPlan` 主要依赖 LLM 输出 JSON，虽然有兜底方案，但真实结果稳定性取决于 prompt 和模型响应格式。
- `trip_planner_agent.py` 和 `amap_service.py` 各自创建了一个 `MCPTool`，系统里实际有两套高德 MCP 实例，可以考虑统一复用。
- `/api/trip/plan` 是前端当前实际调用的核心接口，`frontend/src/services/api.ts` 中超时时间设置为 5 分钟，说明该接口预期耗时较长。
