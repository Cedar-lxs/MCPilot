# MCPilot — 基于 MCP 协议的 AI Agent

MCPilot 是一个基于 LLM 的智能助手。它通过 **Model Context Protocol（MCP）** 自动发现并调用工具，结合 **RAG 知识库** 提供检索增强问答能力，并支持**会话持久化**，对话历史在重启或刷新后仍可恢复。

当前内置搜索、网页抓取、计算、临时笔记、真实日期时间、天气查询和本地知识库问答等工具。

## 核心能力

- **MCP 工具调用**：通过 MCP Server 注册、发现和路由工具，Agent 启动时动态获取工具列表。
- **LangGraph ReAct Agent**：由 `react_graph.py` 统一编排"思考 → 调用工具 → 观察 → 回答"的多步执行流程。
- **流式输出**：`/chat/stream` 接口通过 SSE 实时推送模型生成的 token，Streamlit 前端逐字渲染。
- **会话持久化**：使用 SQLite 存储对话历史，支持多会话管理、切换和删除，重启后自动恢复。
- **RAG 知识库**：使用 ChromaDB 保存向量并检索本地文档。
- **真实时间感知**：避免模型基于训练截止日期编造当前时间。
- **实时互联网信息**：支持搜索、获取公开网页内容和查询城市天气。

## 项目架构

```text
src/
├── agent/                         ← LangGraph Agent 实现
│   ├── prompt.py                  ← 系统提示词（工具列表由 bind_tools 动态注入）
│   └── react_graph.py             ← 构建并执行 ReAct Agent 图
│
├── mcp_client/                    ← MCP 客户端（stdio 连接 Server）
│   └── client.py                  ← 自动发现工具、调用工具
│
├── mcp_server/                    ← MCP 服务端
│   ├── server.py                  ← stdio 主循环入口
│   └── tools/
│       ├── server.py              ← 工具注册与调用路由
│       ├── calculator.py          ← 安全数学计算
│       ├── note.py                ← 临时笔记
│       ├── web_search.py          ← Bing 网络搜索
│       ├── rag_tool.py            ← 本地知识库检索
│       ├── datetime_tool.py       ← 当前真实日期时间
│       ├── url_fetch.py           ← 安全获取公开网页内容
│       └── weather.py             ← Open-Meteo 天气查询
│
├── rag/                           ← RAG 知识库
│   ├── chunk.py                   ← 文本分块
│   ├── embeddings.py              ← 文本向量化
│   ├── vector_store.py            ← ChromaDB 存储与检索（asyncio.to_thread 包裹）
│   └── rag.py                     ← RAG 查询链路（模块级单例 LLM + VectorStore）
│
├── session/                       ← 会话持久化
│   └── store.py                   ← SQLite SessionStore，CRUD + asyncio.to_thread
│
├── api/                           ← FastAPI 接口
│   └── app.py                     ← 聊天、流式、会话管理、RAG、文档接口
│
└── utils/                         ← 公共工具
    ├── config.py                  ← 环境配置
    ├── logger_handler.py          ← 日志管理
    └── path_tool.py               ← 统一路径

ui/
└── app.py                         ← Streamlit 前端（流式输出 + 会话侧边栏）

data/                              ← 运行时数据（不提交到版本控制）
└── mcpilot.db                     ← SQLite 会话数据库

tests/                             ← 单元测试与集成测试
```

## API 接口

### 聊天接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/chat` | 非流式对话，返回完整 JSON 回答 |
| `POST` | `/chat/stream` | 流式对话，SSE 逐 token 推送，`done` 事件携带 `session_id` 和 `history` |

`ChatRequest` 字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `message` | `string` | 用户当前消息 |
| `session_id` | `string?` | 传入则从数据库加载历史，忽略 `history` 字段 |
| `history` | `list?` | 旧接口兼容，不传 `session_id` 时使用 |

### 会话管理接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/sessions` | 创建会话，返回 `id`、`title`、`created_at`、`updated_at` |
| `GET` | `/sessions` | 列出所有会话，按最近更新排序 |
| `GET` | `/sessions/{id}` | 获取会话信息及完整消息历史 |
| `DELETE` | `/sessions/{id}` | 删除会话及其所有消息（级联） |

### 其他接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/health` | 服务与 MCP 连接状态检查 |
| `POST` | `/rag/search` | 仅检索知识库，返回原文片段 |
| `POST` | `/rag/query` | 检索 + LLM 回答 |
| `GET` | `/documents` | 列出知识库中已导入的文档 |
| `POST` | `/documents/upload` | 导入项目目录内的文件到知识库 |
| `DELETE` | `/documents/{source}` | 从知识库删除指定文档 |

## MCP 工具

| 工具名 | 功能 | 主要参数 |
|---|---|---|
| `calculator` | 安全执行基础数学表达式 | `expression` |
| `note_take` | 写入、读取、列出或删除临时笔记 | `action`、`key`、`content` |
| `web_search` | 使用 Bing 搜索互联网最新信息 | `query`、`max_results`、`freshness` |
| `rag_query` | 检索本地知识库并返回相关内容 | `question` |
| `datetime_now` | 获取真实当前日期、时间或 Unix 时间戳 | `format`、`timezone` |
| `url_fetch` | 获取并清理公开 HTTP/HTTPS 网页内容 | `url`、`max_length`、`output_format`、`timeout` |
| `weather_query` | 查询城市当前天气及最多 7 天预报，无需 API Key | `location`、`forecast_days`、`temperature_unit` |

### 日期时间工具

`datetime_now` 默认返回 `Asia/Shanghai` 的当前日期时间，也支持 `UTC` 等 IANA 时区。

```text
format: datetime | date | time | timestamp | iso
timezone: Asia/Shanghai | UTC | ...
```

### URL 抓取安全限制

`url_fetch` 仅允许访问公开的 `http` / `https` 地址，并拒绝 `localhost`、私网 IP、回环地址、链路本地地址和保留地址，以降低 SSRF 风险。可返回纯文本或保留标题、链接结构的 Markdown。

### 天气查询

`weather_query` 使用 Open-Meteo 的地理编码与天气接口，不需要配置 API Key。

```text
location: 北京
forecast_days: 3
temperature_unit: celsius
```

返回地点当地时间、当前天气、温度、体感温度、湿度、风速及每日预报。

## 快速开始

### 1. 安装依赖

建议使用 Python 3.11 或更高版本：

```bash
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS / Linux：

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### 2. 配置环境变量

复制示例配置文件并填写 API Key：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

| 配置项 | 说明 | 默认值 |
|---|---|---|
| `OPENAI_API_KEY` | LLM API Key（支持 OpenAI 兼容服务） | — |
| `OPENAI_BASE_URL` | LLM API 地址 | — |
| `LLM_MODEL` | 对话模型名 | `deepseek-v4-flash` |
| `EMBEDDING_API_KEY` | Embedding API Key，例如 DashScope | — |
| `EMBEDDING_BASE_URL` | Embedding API 地址 | — |
| `EMBEDDING_MODEL` | Embedding 模型名 | — |
| `LLM_MAX_TOKENS` | 单次回答最大 token 数 | `4096` |
| `MAX_ITERATIONS` | Agent 最大推理循环步数 | `10` |
| `AGENT_TEMPERATURE` | Agent 温度参数 | `0.3` |
| `SESSION_DB_PATH` | SQLite 会话数据库路径 | `./data/mcpilot.db` |
| `CHROMA_DB_PATH` | ChromaDB 向量数据库路径 | `./chroma_data` |

> `datetime_now` 和 `weather_query` 无需 API Key。`weather_query`、`web_search` 和 `url_fetch` 需要能访问互联网。

### 3. 启动服务

**启动 FastAPI 后端**（默认端口 8000）：

```bash
uvicorn src.api.app:app --reload
```

**启动 Streamlit 前端**（默认端口 8501）：

```bash
streamlit run ui/app.py
```

服务启动后访问 [http://localhost:8501](http://localhost:8501) 使用对话界面。

**验证已注册的 MCP 工具**：

```bash
python -m src.mcp_server.tools.server
```

## 流式输出

前端通过 `POST /chat/stream` 接收 SSE 事件流：

```text
event: token
data: {"token": "你好"}

event: done
data: {"session_id": "...", "history": [...]}
```

- `token` 事件：模型每产生一个文本片段就实时推送。
- `done` 事件：整张 LangGraph 执行结束后推送，包含 `session_id` 和完整 `history`。

## 会话持久化

MCPilot 使用 SQLite 在服务端保存对话历史，数据库文件默认位于 `data/mcpilot.db`，结构如下：

```text
sessions 表  — 会话 ID、标题、创建时间、更新时间
messages 表  — 消息角色、内容、附加信息（tool_calls / tool_call_id）
```

Streamlit 侧边栏功能：

- 新建会话
- 切换历史会话（列表按最近更新排序）
- 删除当前会话

## 测试

执行全部测试：

```bash
python -m pytest
```

执行特定测试套件：

```bash
python -m pytest tests/test_session_store.py -v   # 会话持久化单元测试
python -m pytest tests/test_chat_stream.py -v     # 流式接口集成测试
python -m pytest tests/test_datetime_tool.py -v   # 日期时间工具测试
python -m pytest tests/test_weather.py -v         # 天气工具测试
```

测试中 `test_weather.py` 和 `test_url_fetch.py` 使用 `httpx.MockTransport` 模拟外部响应，不依赖外网。`test_session_store.py` 使用临时目录创建独立数据库，不影响运行时数据。`test_chat_stream.py` 需要 FastAPI 服务和 MCP 服务正在运行。

## 技术栈

| 类别 | 技术 |
|---|---|
| LLM | OpenAI 兼容 API / DeepSeek |
| MCP | Model Context Protocol Python SDK |
| Agent 编排 | LangGraph |
| 向量数据库 | ChromaDB |
| Embedding | DashScope 等 OpenAI 兼容 Embedding 服务 |
| 会话持久化 | SQLite（Python 标准库 sqlite3） |
| 后端 | FastAPI |
| 前端 | Streamlit |
| 异步 HTTP | httpx |
| 网页解析 | BeautifulSoup、html2text |
| 天气数据 | Open-Meteo |

## 项目履历

- 从手写 Function Calling 逐步演进到 MCP 协议驱动。
- 修复 DeepSeek 调工具时 `content` 为空导致的工具循环问题。
- 使用独立 Embedding 服务处理向量化。
- 集成 MCP Client，Agent 动态发现工具。
- 集成 LangChain ReAct Agent，清理废弃代码。
- 添加 RAG 模块：DashScope 向量化、Chroma 存储检索、LLM 问答链路、`rag_query` 工具集成到 Agent、RAG API 接口。
- CODE REVIEW：修复 MCP 依赖缺失、ddgs 导入崩溃、RAG 默认值、工具 Schema、并发锁、文件上传沙箱与计算器安全问题。
- 使用 LangGraph 替换手写 ReAct 循环。
- 修复 LangGraph 版本并发安全、消息历史、System Prompt 等问题。
- 工程化整改：Config 集中管理、Type Hints、测试、Docker。
- 增加真实日期时间、带 SSRF 基础防护的网页抓取，以及无需 API Key 的 Open-Meteo 天气查询工具。
- 新增 `/chat/stream` SSE 流式接口，Streamlit 前端改为逐 token 渲染。
- 统一 LLM 客户端（RAG 和 Agent 均使用 `ChatOpenAI`），修复 ChromaDB 同步调用阻塞事件循环问题，`VectorStore` 改为模块级单例。
- 移除 System Prompt 中的静态工具列表，改由 `bind_tools` 动态注入，避免工具信息重复。
- 集成 SQLite 会话持久化：`SessionStore`、会话管理 CRUD API、Streamlit 会话侧边栏（新建 / 切换 / 删除），对话历史重启后可恢复。
