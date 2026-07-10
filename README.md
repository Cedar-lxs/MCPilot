# MCPilot — 基于 MCP 协议的 AI Agent

一个基于 LLM 的智能助手，通过 **MCP 协议** 驱动工具调用，支持搜索、计算、笔记等能力，并配备 **RAG 知识库** 实现检索增强问答。

## 项目架构

```
src/
├── agent/              ← Agent 核心（ReAct 循环）
│   ├── core.py         ← 主循环：思考 → 调工具 → 观察 → 回答
│   ├── langchain_tools.py  ← MCP → LangChain 适配层
│   └── prompt.py       ← 系统提示词
│
├── mcp_client/         ← MCP 客户端（stdio 连接 Server）
│   └── client.py       ← 自动发现工具、调用工具
│
├── mcp_server/         ← MCP 服务端
│   ├── server.py       ← stdio 主循环入口
│   └── tools/
│       ├── server.py   ← 工具注册与路由
│       ├── calculator.py   ← 安全数学计算
│       ├── note.py         ← 临时笔记（write/read/list/delete）
│       └── web_serach.py   ← 网络搜索（Bing）
│
├── rag/                ← RAG 知识库
│   ├── chunk.py        ← 文本分块
│   ├── embeddings.py   ← 文本向量化（DashScope）
│   ├── vector_store.py ← ChromaDB 存储与检索
│   └── rag.py          ← RAG 完整查询链路
│
├── api/                ← FastAPI 接口
│   └── app.py          ← POST /chat
│
└── utils/              ← 工具函数
    ├── logger_handler.py   ← 日志管理
    └── path_tool.py        ← 统一路径

ui/
└── app.py              ← Streamlit 前端
```

## 快速开始

### 1. 环境准备

```bash
pip install -r requirements.txt
```

### 2. 配置

复制 `.env` 文件，填写必要的 API Key：

| 配置项 | 说明 |
|--------|------|
| `OPENAI_API_KEY` | LLM API Key（如 DeepSeek） |
| `OPENAI_BASE_URL` | LLM API 地址 |
| `LLM_MODEL` | 对话模型名（如 deepseek-v4-flash） |
| `EMBEDDING_API_KEY` | Embedding API Key（如 DashScope） |
| `EMBEDDING_BASE_URL` | Embedding API 地址 |
| `EMBEDDING_MODEL` | Embedding 模型名 |
| `LLM_MAX_TOKENS` | 单次回答最大 token 数（默认 4096） |
| `MAX_ITERATIONS` | Agent 最大推理循环步数（默认 10） |
| `AGENT_TEMPERATURE` | LLM 温度参数（默认 0.3） |

### 3. 启动

**方式一：API 服务**

```bash
uvicorn src.api.app:app --reload
```

**方式二：Streamlit 前端**

```bash
streamlit run ui/app.py
```

## 技术栈

- **LLM**: DeepSeek / OpenAI 兼容 API
- **MCP**: Model Context Protocol（Python SDK）
- **向量库**: ChromaDB
- **Embedding**: DashScope（阿里百炼）
- **框架**: FastAPI + Streamlit
- **异步**: asyncio + httpx

## 项目履历

- 从手写 Function Calling 逐步演进到 MCP 协议驱动
- 修复了 DeepSeek 调工具时 `content` 为空导致的工具循环 Bug
- 使用 DashScope 替代 DeepSeek 处理 Embedding（DeepSeek 不支持）
