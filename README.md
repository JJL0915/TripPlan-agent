# TripAgent 智能旅行助手

TripAgent 是一个基于大模型和地图工具的智能旅行规划项目。用户可以在网页中填写目的地、日期、交通方式、住宿偏好和旅行偏好，也可以通过右下角的行程问答助手用自然语言补充需求、生成计划或修改已有行程。

后端使用 FastAPI、LangChain 和 LangGraph 构建 Agent 工作流，集成高德 MCP 工具获取真实景点、天气、酒店和路线数据；前端使用 Vue 3、TypeScript、Vite 和 Ant Design Vue 构建交互界面。

## 功能特性

- 旅行计划生成：根据城市、日期、交通、住宿、偏好和额外要求生成多日行程。
- 工具先查：优先调用高德 MCP 获取真实 POI、天气、酒店等数据。
- 子 Agent 总结：景点、天气、酒店分别由子 Agent 总结，再交给 Planner Agent 整合。
- LangGraph 并行工作流：工具查询节点和子 Agent 总结节点并行执行，减少串行等待。
- 行程问答助手：支持规划页需求收集、旅行问答、计划生成和结果页行程修改。
- 流式回答：问答助手支持 NDJSON 流式输出，前端逐字展示回答。
- 行程同步：助手生成或修改计划后，前端结果页自动刷新展示。
- 地图与图片展示：结果页展示景点地图、天气、预算和景点图片。
- 可观测性：后端使用 `logging` 输出请求耗时、Agent 节点耗时、MCP 调用状态和异常信息。
- 浏览器日志采集：提供 Playwright 脚本采集网页控制台、网络失败和截图。

## 技术栈

后端：

- FastAPI
- LangChain
- LangGraph
- langchain-mcp-adapters
- 高德 MCP：`amap-mcp-server`
- Pydantic
- Unsplash API
- Python logging

前端：

- Vue 3
- TypeScript
- Vite
- Ant Design Vue
- Axios / Fetch
- 高德地图 JS API

## 核心架构

主行程规划流程：

```text
POST /api/trip/plan
  -> MultiAgentTripPlanner.aplan_trip()
  -> LangGraph 并行执行工具节点
      -> attraction_tool：高德景点搜索
      -> weather_tool：高德天气查询
      -> hotel_tool：高德酒店搜索
  -> LangGraph 并行执行子 Agent 总结节点
      -> attraction_agent：景点总结
      -> weather_agent：天气总结
      -> hotel_agent：酒店总结
  -> planner_agent：整合生成 TripPlan JSON
  -> Pydantic 校验和类型归一化
  -> FastAPI 返回结果
```

行程问答助手流程：

```text
POST /api/assistant/chat
  -> TravelAssistantAgent.achat()
  -> analyze_message()
  -> complete_response()

POST /api/assistant/chat/stream
  -> TravelAssistantAgent.stream_analysis()
  -> get_action_status()
  -> complete_response()
```

## 项目结构

```text
TripAgent/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── prompts.py                   # Agent 提示词
│   │   │   ├── trip_planner_agent.py        # LangGraph 旅行规划工作流
│   │   │   └── travel_assistant_agent.py    # 行程问答与行程修改 Agent
│   │   ├── api/
│   │   │   ├── main.py                      # FastAPI 入口、CORS、请求日志
│   │   │   └── routes/
│   │   │       ├── assistant.py             # 问答助手接口
│   │   │       ├── trip.py                  # 行程规划接口
│   │   │       ├── map.py                   # 地图服务接口
│   │   │       └── poi.py                   # POI 和图片接口
│   │   ├── models/
│   │   │   └── schemas.py                   # Pydantic 数据模型
│   │   ├── services/
│   │   │   ├── amap_service.py              # 高德 MCP 封装
│   │   │   ├── llm_service.py               # LLM 服务封装
│   │   │   └── unsplash_service.py          # 图片搜索服务
│   │   ├── config.py                        # 环境变量配置
│   │   └── logging_config.py                # 后端日志配置
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   └── FloatingTravelAssistant.vue  # 全局悬浮问答助手
│   │   ├── services/
│   │   │   └── api.ts                       # 前端接口封装
│   │   ├── types/
│   │   │   └── index.ts                     # 前端类型定义
│   │   ├── views/
│   │   │   ├── Home.vue                     # 规划页
│   │   │   └── Result.vue                   # 结果页
│   │   ├── App.vue
│   │   └── main.ts
│   ├── package.json
│   └── .env.example
└── README.md
```

## 环境要求

- Python 3.10+
- Node.js 16+
- 高德地图 API Key
- LLM API Key
- 可选：Unsplash Access Key

## 后端配置

首次运行前复制后端环境变量示例：

```powershell
Copy-Item backend\.env.example backend\.env
```

macOS / Linux：

```bash
cp backend/.env.example backend/.env
```

编辑：

```text
backend/.env
```

常用配置：

```env
AMAP_API_KEY=your_amap_api_key

LLM_API_KEY=your_llm_api_key
LLM_BASE_URL=your_llm_api_base_url
LLM_MODEL_ID=your_llm_model_name

UNSPLASH_ACCESS_KEY=your_unsplash_access_key
UNSPLASH_SECRET_KEY=your_unsplash_secret_key

HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO
```

说明：

- `AMAP_API_KEY` 必填，用于高德 MCP 工具。
- LLM 配置兼容 `LLM_API_KEY` / `OPENAI_API_KEY`、`LLM_BASE_URL` / `OPENAI_BASE_URL`、`LLM_MODEL_ID` / `OPENAI_MODEL`。
- `UNSPLASH_ACCESS_KEY` 可选。图片接口失败或无结果时会返回 `photo_url: null`，不影响主行程生成。
- 后端会显式读取 `backend/.env`。

## 前端配置

复制前端环境变量示例：

```powershell
Copy-Item frontend\.env.example frontend\.env
```

macOS / Linux：

```bash
cp frontend/.env.example frontend/.env
```

编辑：

```text
frontend/.env
```

常用配置：

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_AMAP_WEB_KEY=your_amap_web_key
VITE_AMAP_WEB_JS_KEY=your_amap_js_api_key
```

## 启动后端

### 1. 创建 Python 虚拟环境

在项目根目录执行：

```powershell
python -m venv .venv
```

激活虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

也可以使用 Conda、uv、Poetry 等环境管理工具。只要安装依赖的 Python 环境与启动后端时使用的 Python 环境一致即可。

### 2. 安装后端依赖

```powershell
pip install -r backend\requirements.txt
```

如果没有激活虚拟环境，可以直接指定项目 `.venv` 中的 Python：

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

### 3. 启动后端

```powershell
cd backend
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

启动后访问：

- Swagger：http://localhost:8000/docs
- ReDoc：http://localhost:8000/redoc
- 健康检查：http://localhost:8000/health

## 启动前端

```powershell
cd frontend
npm install
npm run dev
```

默认访问：

```text
http://localhost:5173
```

## 主要接口

行程规划：

```http
POST /api/trip/plan
GET /api/trip/health
```

行程问答助手：

```http
POST /api/assistant/chat
POST /api/assistant/chat/stream
GET /api/assistant/health
```

地图服务：

```http
GET /api/map/poi
GET /api/map/weather
POST /api/map/route
GET /api/map/health
```

POI 与图片：

```http
GET /api/poi/search
GET /api/poi/detail/{poi_id}
GET /api/poi/photo?name=鼓浪屿
```

## 后端日志

后端使用 Python 标准库 `logging`，控制台日志为一行可读格式：

```text
[INFO] 11:58:09 app.api.main - HTTP 请求处理完成 | request_id=... method=GET path=/health status_code=200 duration_ms=0.68
```

日志覆盖：

- HTTP 请求方法、路径、状态码和耗时。
- `X-Request-ID` 请求追踪。
- LangGraph 节点耗时。
- LLM 服务初始化状态。
- 高德 MCP 工具调用状态。
- Unsplash 图片搜索失败降级。


