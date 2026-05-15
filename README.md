# TravelPlanner Agent

工具增强型智能旅行规划系统。项目基于 FastAPI、LangChain、LangGraph 和 MCP 构建，支持用户通过表单或自然语言输入旅行需求，自动完成需求理解、地图工具查询、多节点 Agent 分析和结构化行程生成。

系统可以生成包含景点、天气、酒店、餐饮、预算和地图路线的多日旅行计划，并支持在结果页通过问答助手继续补充需求或修改已有行程。

## 核心功能

- 表单生成行程：根据目的地、日期、交通方式、住宿偏好、旅行偏好和额外要求生成多日旅行计划。
- 自然语言问答：悬浮式助手支持需求收集、旅行咨询、行程生成和已有行程修改。
- 工具增强规划：接入高德 MCP 工具链，查询真实 POI、天气、酒店和路线数据后再由大模型分析。
- 多节点 Agent 编排：基于 LangGraph 将景点、天气、酒店查询和领域摘要拆分为独立节点，最后由 Planner 节点统一生成行程。
- 后端会话记忆：通过 `session_id` 在后端维护对话历史、旅行需求草稿和当前 TripPlan，前端只保存会话 ID。
- 并发修改保护：通过 `plan_version` 实现乐观锁，避免用户手动编辑和助手修改行程时互相覆盖。
- 流式交互反馈：问答助手使用 NDJSON Streaming 返回回答片段、任务状态和最终结构化结果。
- 结果页展示与编辑：支持地图标记、天气、预算、景点图片、行程编辑、图片导出和 PDF 导出。

## 技术栈

后端：

- FastAPI
- LangChain
- LangGraph
- langchain-mcp-adapters
- Pydantic
- Python AsyncIO
- NDJSON Streaming
- 高德 MCP / 高德地图服务
- Unsplash 图片服务

前端：

- Vue 3
- TypeScript
- Vite
- Ant Design Vue
- Axios / Fetch
- 高德地图 JS API
- html2canvas / jsPDF

## 技术亮点

**可控编排**：基于 LangGraph 设计可控型 Agentic Workflow，将旅行规划拆分为景点查询、天气查询、酒店查询、领域摘要和最终规划生成等节点，通过 StateGraph 实现工具节点并行执行与 Planner 节点统一聚合。

**工具增强**：集成高德 MCP 工具链，将 POI 搜索、天气查询、酒店搜索等外部能力作为工作流中的工具节点，先获取真实地图数据，再由 LLM 子 Agent 完成筛选、摘要和行程规划，降低纯大模型生成带来的事实幻觉。

**结构化输出**：设计 TripPlan 结构化输出协议，通过 Prompt Schema 约束、JSON 自动提取、字段类型归一化和 Pydantic 校验，将大模型非稳定文本输出转换为稳定的后端业务数据模型。

**会话记忆**：通过后端 `session_id` 管理问答历史、需求草稿和当前 TripPlan，前端不保存完整上下文，便于后续平滑替换为 Redis 持久化方案。

**并发保护**：对 TripPlan 引入 `plan_version` 乐观锁，用户手动编辑和助手自动修改都必须基于最新版本写入，冲突时返回 409，避免静默覆盖。

**工程容错**：针对 LLM 输出解析失败、MCP 工具异常、外部图片服务失败等场景设计兜底策略，并记录 HTTP 请求耗时、Agent 节点耗时和工具调用状态。

## 核心流程

### 行程规划流程

```text
POST /api/trip/plan
  -> 获取或创建后端 session
  -> MultiAgentTripPlanner.aplan_trip()
  -> LangGraph 并行执行工具节点
      -> attraction_tool：高德景点搜索
      -> weather_tool：高德天气查询
      -> hotel_tool：高德酒店搜索
  -> LangGraph 并行执行领域摘要节点
      -> attraction_agent：景点分析
      -> weather_agent：天气分析
      -> hotel_agent：酒店分析
  -> planner：生成 TripPlan JSON
  -> Pydantic 校验与类型归一化
  -> 保存 TripPlan 到后端 session_store
  -> 返回 session_id、plan_version 和 TripPlan
```

### 问答助手流程

```text
POST /api/assistant/chat/stream
  -> stream_analysis() 流式输出自然语言回复
  -> 解析隐藏 metadata 得到 intent / draft / action
  -> complete_response()
      -> 普通问答：保存对话历史
      -> 需求收集：更新 draft_trip_request
      -> 生成行程：调用 TripPlannerAgent
      -> 修改行程：基于当前 TripPlan 调用 LLM 重写
  -> 保存最新 TripPlan 和 plan_version
  -> 返回 final 事件给前端刷新页面
```

## 项目结构

```text
TripAgent/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── prompts.py
│   │   │   ├── trip_planner_agent.py
│   │   │   └── travel_assistant_agent.py
│   │   ├── api/
│   │   │   ├── main.py
│   │   │   └── routes/
│   │   │       ├── assistant.py
│   │   │       ├── trip.py
│   │   │       ├── map.py
│   │   │       └── poi.py
│   │   ├── models/
│   │   │   └── schemas.py
│   │   ├── services/
│   │   │   ├── amap_service.py
│   │   │   ├── llm_service.py
│   │   │   ├── session_store.py
│   │   │   └── unsplash_service.py
│   │   ├── config.py
│   │   └── logging_config.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   └── FloatingTravelAssistant.vue
│   │   ├── services/
│   │   │   └── api.ts
│   │   ├── types/
│   │   │   └── index.ts
│   │   ├── views/
│   │   │   ├── Home.vue
│   │   │   └── Result.vue
│   │   ├── App.vue
│   │   └── main.ts
│   └── package.json
└── README.md
```

## 环境要求

- Python 3.10+
- Node.js 16+
- 高德地图 API Key
- 大模型 API Key
- 可选：Unsplash Access Key

## 后端启动

复制环境变量文件：

```powershell
Copy-Item backend\.env.example backend\.env
```

安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

配置 `backend/.env`：

```env
LLM_MODEL_ID=
LLM_API_KEY=
LLM_BASE_URL=

AMAP_API_KEY=

UNSPLASH_ACCESS_KEY=
UNSPLASH_SECRET_KEY=

HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO
```

启动后端：

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

如果已激活虚拟环境，也可以执行：

```powershell
cd backend
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

访问：

- Swagger: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health: http://localhost:8000/health

## 前端启动

复制环境变量文件：

```powershell
Copy-Item frontend\.env.example frontend\.env
```

配置 `frontend/.env`：

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_AMAP_WEB_KEY=
VITE_AMAP_WEB_JS_KEY=
```

安装依赖并启动：

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

| 模块 | 接口 | 说明 |
| --- | --- | --- |
| 行程规划 | `POST /api/trip/plan` | 根据表单或草稿需求生成 TripPlan |
| 行程规划 | `GET /api/trip/health` | 检查规划服务 |
| 问答助手 | `POST /api/assistant/chat` | 非流式问答入口 |
| 问答助手 | `POST /api/assistant/chat/stream` | NDJSON 流式问答入口 |
| 问答助手 | `GET /api/assistant/session/{session_id}` | 获取后端会话快照 |
| 问答助手 | `GET /api/assistant/session/{session_id}/trip-plan` | 获取当前会话 TripPlan |
| 问答助手 | `PUT /api/assistant/session/{session_id}/trip-plan` | 使用乐观锁保存编辑后的 TripPlan |
| 地图服务 | `GET /api/map/poi` | 搜索 POI |
| 地图服务 | `GET /api/map/weather` | 查询天气 |
| 地图服务 | `POST /api/map/route` | 路线规划 |
| POI | `GET /api/poi/search` | 搜索 POI |
| POI | `GET /api/poi/detail/{poi_id}` | 查询 POI 详情 |
| POI | `GET /api/poi/photo` | 查询景点图片 |


## 说明

- 项目仍在优化中...
