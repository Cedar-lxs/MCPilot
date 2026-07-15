# MCPilot — 基于 MCP 协议的 AI Agent

MCPilot 是一个基于 LLM 的智能助手。它通过 **Model Context Protocol（MCP）** 自动发现并调用工具，结合 **RAG 知识库** 提供检索增强问答能力。

当前内置搜索、网页抓取、计算、临时笔记、真实日期时间、天气查询和本地知识库问答等工具。

## 核心能力

- **MCP 工具调用**：通过 MCP Server 注册、发现和路由工具。
- **ReAct Agent**：按“思考 → 调用工具 → 观察 → 回答”的方式执行多步任务。
- **RAG 知识库**：使用 ChromaDB 保存向量并检索本地文档。
- **真实时间感知**：避免模型基于训练截止日期编造当前时间。
- **实时互联网信息**：支持搜索、获取公开网页内容和查询城市天气。

## 项目架构

```text
src/
├── agent/                         ← Agent 核心（ReAct 循环）
│   ├── core.py                    ← Agent 主逻辑
│   ├── prompt.py                  ← 系统提示词
│   └── react_graph.py             ← ReAct 图编排
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
│   ├── vector_store.py            ← ChromaDB 存储与检索
│   └── rag.py                     ← RAG 查询链路
│
├── api/                           ← FastAPI 接口
│   └── app.py                     ← POST /chat
│
└── utils/                         ← 公共工具
    ├── config.py                  ← 环境配置
    ├── logger_handler.py          ← 日志管理
    └── path_tool.py               ← 统一路径

ui/
└── app.py                         ← Streamlit 前端

tests/                             ← 单元测试
```

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

### 日期时间工具示例

`datetime_now` 默认返回 `Asia/Shanghai` 的当前日期时间，也支持 `UTC` 等 IANA 时区。

```text
format: datetime | date | time | timestamp | iso
timezone: Asia/Shanghai | UTC | ...
```

### URL 抓取安全限制

`url_fetch` 仅允许访问公开的 `http` / `https` 地址，并拒绝 `localhost`、私网 IP、回环地址、链路本地地址和保留地址，以降低 SSRF 风险。可返回纯文本或保留标题、链接结构的 Markdown。

### 天气查询示例

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

Windows PowerShell 可使用：

```powershell
Copy-Item .env.example .env
```

| 配置项 | 说明 |
|---|---|
| `OPENAI_API_KEY` | LLM API Key（支持 OpenAI 兼容服务） |
| `OPENAI_BASE_URL` | LLM API 地址 |
| `LLM_MODEL` | 对话模型名 |
| `EMBEDDING_API_KEY` | Embedding API Key，例如 DashScope |
| `EMBEDDING_BASE_URL` | Embedding API 地址 |
| `EMBEDDING_MODEL` | Embedding 模型名 |
| `LLM_MAX_TOKENS` | 单次回答最大 token 数，默认 `4096` |
| `MAX_ITERATIONS` | Agent 最大推理循环步数，默认 `10` |
| `AGENT_TEMPERATURE` | Agent 温度参数，默认 `0.3` |

> `datetime_now` 和 `weather_query` 无需 API Key。`weather_query`、`web_search` 和 `url_fetch` 需要能访问互联网。

### 3. 启动服务

**方式一：启动 FastAPI 服务**

```bash
uvicorn src.api.app:app --reload
```

**方式二：启动 Streamlit 前端**

```bash
streamlit run ui/app.py
```

**方式三：验证已注册的 MCP 工具**

```bash
python -m src.mcp_server.tools.server
```

## 测试

执行全部测试：

```bash
python -m pytest
```

执行天气工具测试：

```bash
python -m pytest tests/test_weather.py -v
```

测试使用 `httpx.MockTransport` 模拟天气与网页响应，不依赖外网。

## 技术栈

- **LLM**：OpenAI 兼容 API / DeepSeek
- **MCP**：Model Context Protocol Python SDK
- **Agent 编排**：LangGraph
- **向量数据库**：ChromaDB
- **Embedding**：DashScope 等 OpenAI 兼容 Embedding 服务
- **后端**：FastAPI
- **前端**：Streamlit
- **异步 HTTP**：httpx
- **网页解析**：BeautifulSoup、html2text
- **天气数据**：Open-Meteo

## 项目履历

- 从手写 Function Calling 逐步演进到 MCP 协议驱动。
- 修复 DeepSeek 调工具时 `content` 为空导致的工具循环问题。
- 使用独立 Embedding 服务处理向量化。
- 集成MCP Client, Agent动态发现工具
- 集成LangChain ReAct Agent, 清理废弃代码
- 添加RAG模块，DashScope向量化，Chroma存储检索，LLM问答链路,rag_query工具集成到Agent，添加RAG API接口
- CODE REVIEW
- 修复MCP依赖缺失，ddgs导入崩溃，RAG默认值，工具Scheam，并发锁，文件上传沙箱与计算器安全问题
- 使用LangGraph替换手写ReAct循环
- 修复LangGraph版本并发安全，消息历史，System prompt等问题
- 工程化整改——Config类， Type Hints，测试， Docker
- 增加真实日期时间、带 SSRF 基础防护的网页抓取，以及无需 API Key 的 Open-Meteo 天气查询工具。
