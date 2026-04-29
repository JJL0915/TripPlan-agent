# TripPlanAgent 智能旅行助手

TripPlanAgent 是一个智能旅游 Agent 项目。前端使用 Vue 3 + TypeScript + Vite，后端使用 FastAPI，并基于 **LangChain + LangGraph** 实现智能行程规划。

当前后端采用 **工具先查 + 子 Agent 总结 + Planner 整合** 的架构：

1. 代码先稳定调用高德 MCP 工具，获取真实景点、天气、酒店数据。
2. 三个子 Agent 分别对工具结果做总结：
   - 景点 Agent：筛选景点并总结推荐理由。
   - 天气 Agent：分析天气对行程的影响。
   - 酒店 Agent：筛选酒店并总结推荐理由。
3. Planner Agent 汇总三个子 Agent 的分析结果，生成最终结构化旅行计划。

## 技术栈

后端：

- FastAPI
- LangChain
- LangGraph
- langchain-mcp-adapters
- 高德地图 MCP：`amap-mcp-server`
- Unsplash API
- Pydantic

前端：

- Vue 3
- TypeScript
- Vite
- Ant Design Vue
- Axios
- 高德地图 JS API

## 核心流程

```text
用户提交旅行需求
  -> POST /api/trip/plan
  -> LangGraph 并行执行三个工具查询节点
      -> 景点工具节点：maps_text_search
      -> 天气工具节点：maps_weather
      -> 酒店工具节点：maps_text_search
  -> LangGraph 并行执行三个子 Agent 总结节点
      -> 景点 Agent 总结
      -> 天气 Agent 总结
      -> 酒店 Agent 总结
  -> Planner Agent 整合生成 TripPlan JSON
  -> FastAPI 返回结果
  -> 前端展示行程、预算、地图、天气、图片
```

## 项目结构

```text
TripAgent/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── prompts.py
│   │   │   └── trip_planner_agent.py
│   │   ├── api/
│   │   │   ├── main.py
│   │   │   └── routes/
│   │   │       ├── trip.py
│   │   │       ├── map.py
│   │   │       └── poi.py
│   │   ├── models/
│   │   │   └── schemas.py
│   │   ├── services/
│   │   │   ├── amap_service.py
│   │   │   ├── llm_service.py
│   │   │   └── unsplash_service.py
│   │   └── config.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
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

首次运行前，请先进入项目文件，复制示例配置：

```powershell
Copy-Item backend\.env.example backend\.env
```

如果是 macOS / Linux：

```bash
cp backend/.env.example backend/.env
```

然后编辑：

```text
backend/.env
```

按需填写：

```env
AMAP_API_KEY=your_amap_api_key

LLM_API_KEY=your_llm_api_key
LLM_BASE_URL=your_llm_api_base_url
LLM_MODEL_ID=your_llm_model_name

UNSPLASH_ACCESS_KEY=your_unsplash_access_key
UNSPLASH_SECRET_KEY=your_unsplash_secret_key
```

说明：

- `AMAP_API_KEY` 必填。
- LLM 配置兼容 `LLM_API_KEY` / `OPENAI_API_KEY`、`LLM_BASE_URL` / `OPENAI_BASE_URL`、`LLM_MODEL_ID` / `OPENAI_MODEL`。
- 后端会显式读取 `backend/.env`。

## 前端配置

首次运行前，请复制示例配置：

```powershell
Copy-Item frontend\.env.example frontend\.env
```

如果是 macOS / Linux：

```bash
cp frontend/.env.example frontend/.env
```

然后编辑：

```text
frontend/.env
```

示例：

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_AMAP_WEB_KEY=your_amap_web_key
VITE_AMAP_WEB_JS_KEY=your_amap_js_api_key
```

## 启动后端

### 1. 创建 Python 虚拟环境

如果项目环境还没搭建，可以使用 Python 自带的 `venv` 创建，进入项目文件：
```powershell
python -m venv .venv
```

激活虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
```


也可以使用 Conda、uv、Poetry 等环境管理工具。只要安装依赖的 Python 环境与启动后端时使用的 Python 环境一致即可。

### 2. 安装后端依赖

进入环境后,在项目根目录执行：

```powershell
pip install -r backend\requirements.txt
```

如果没有激活虚拟环境，也可以直接指定项目 `.venv` 里的 Python：

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

生成旅行计划：

```http
POST /api/trip/plan
```

请求示例：

```json
{
  "city": "厦门",
  "start_date": "2026-05-01",
  "end_date": "2026-05-03",
  "travel_days": 3,
  "transportation": "公共交通",
  "accommodation": "经济型酒店",
  "preferences": ["历史文化", "美食"],
  "free_text_input": "节奏轻松，少走路"
}
```

获取景点图片：

```http
GET /api/poi/photo?name=鼓浪屿
```

地图服务健康检查：

```http
GET /api/map/health
```



## 当前实现说明

- 高德 MCP 通过 `langchain-mcp-adapters` 接入。
- MCP 启动时优先使用项目 `.venv` 下的 `uvx.exe`。
- `/api/trip/plan` 包含 3 个 MCP 工具查询节点、3 个子 Agent 总结节点和 1 个 Planner Agent。
- 工具查询节点并行执行，子 Agent 总结节点也并行执行。
- Planner 输出 JSON 后会经过类型归一化和 Pydantic 校验。
- 如果 LLM 输出不可解析，会返回兜底行程，避免前端空白。
