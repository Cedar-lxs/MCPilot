# MCPilot Code Review 报告

**日期:** 2026-07-10  
**审核范围:** 全项目源码（src/、ui/、scripts/）  
**项目性质:** MCP 协议驱动的 AI Agent，含 RAG 知识库

---

## 一、项目总览

**架构层次:**
```
User → Streamlit UI → FastAPI API → Agent ReAct Loop → MCP Client → stdio → MCP Server → Tools
                                                                                → RAG (ChromaDB)
```

整体架构清晰，从手写 Function Calling 演进到 MCP 协议驱动，方向正确。代码量适中（~40 个文件），可读性不错。

---

## 二、🔴 严重问题（建议立即修复）

### 1. `.env` 包含真实 API Key —— 安全隐患

`.env` 文件中直接硬编码了 DeepSeek 和 DashScope 的 API Key。
- `.gitignore` 虽然排除了 `.env`，但开发协作中仍可能意外泄露
- 建议：使用环境变量或密钥管理服务，或至少对 `.env` 文件设置文件权限

### 2. `calculator.py` —— `eval()` 的安全边界不够牢

```python
result = eval(expression, {"__builtins__": {}}, {"math": math})
```

限制了 `__builtins__` 和仅暴露 `math`，但仍有风险：
- `().__class__.__bases__[0].__subclasses__()` 可以逃逸
- 正则 `ALLOWED_PATTERN` **只 log 不拦截**，安全检查形同虚设

**建议:** 改用 `ast.literal_eval` + 自定义解析器，或直接用 `numexpr` 库。

### 3. `note.py` —— `_store` 是类变量，多会话共享状态

```python
class NoteTool:
    _store: dict[str, str] = {}  # 类变量！
```

所有 `NoteTool` 实例共享同一个字典。如果并发对话，笔记内容会互相污染。

**建议:** 改为实例变量 `self._store = {}`，或在构造函数中初始化。

### 4. `rag_tool.py` —— GBK 编码会截断/损坏文本

```python
doc.encode("gbk", errors="replace").decode("gbk")
```

GBK 无法编码所有 Unicode 字符（如 emoji、生僻字），导致数据丢失。纯中文场景也未必全覆盖。

**建议:** 直接返回 UTF-8 文本，不需要做 GBK 编码转换。

---

## 三、🟡 中等问题（建议迭代修复）

### 5. MCP Client 每次对话都创建子进程 —— 性能浪费

`core.py` 的 `run()` 每次调用都 `async with MCPClient()`，这意味着：
- 启动一个 Python 子进程
- 建立 stdio 连接
- 初始化 MCP 会话
- 用完再销毁

对于多轮对话，每次都要重复这个开销。

**建议:** 将 MCPClient 实例化在更上层（FastAPI 启动时），在 Agent 间复用。

### 6. `core.py` 硬编码 `max_tokens=1024`

```python
response = client.chat.completions.create(..., max_tokens=1024)
```

长回答会被截断。建议从 `.env` 读取或设为更大的值（如 4096）。

### 7. `web_serach.py` 文件名拼写错误

文件名 `web_serach.py` 应为 `web_search.py`。这不影响运行但影响可维护性。

### 8. Bing 爬虫实现脆弱

```python
soup.select(".b_algo")  # 依赖 Bing HTML 结构
```

- 违反 Bing ToS
- HTML 结构一变就挂
- 无反爬处理（IP被封风险）
- 无速率限制

**建议:** 换用正式搜索 API（SerpAPI、Bing Search API、或至少 DuckDuckGo）。

### 9. `calculator.py` —— 安全检查形同虚设

`ALLOWED_PATTERN` 检查不通过时只打了 log，程序仍然继续执行 `eval()`。

```python
if not self.ALLOWED_PATTERN.match(expression):
    logger.error(...)  # 只记录日志，没return没raise
```

**建议:** 不匹配时应直接 return 错误信息。

### 10. 大量死代码未清理

`core.py` 中注释掉了 ~80 行旧版 Function Calling 代码。`rag_tool.py` 也有两套实现共存。`langchain_tools.py` 虽然写得完整但从未被引用。

**建议:** 删除无用死代码，保持仓库整洁。

### 11. `logger_handler.py` —— 日志重复添加

```python
if logger.handlers:
    return logger
```

这个检查是对的，但更标准的做法是用 `logging.getLogger` 的单例特性 + `hasHandlers()`。

### 12. FastAPI 同步阻塞操作

`api/app.py` 中的 `upload_document` 和 `delete_document` 使用了同步文件/DB操作，会阻塞事件循环。

```python
text = path.read_text(encoding="utf-8")  # 同步
store.collection.delete(ids=ids_to_delete)  # ChromaDB 同步操作
```

**建议:** 用 `asyncio.to_thread()` 包装，或使用 ChromaDB 的异步客户端。

### 13. `rag_query` 提示词模板混入了工具描述

`rag.py` 的 `RAG_PROMPT_TEMPLATE` 末尾有一行工具使用说明：
```
4. **rag_query** — 从本地知识库检索信息...
```

RAG 回答阶段的 prompt 不应该包含 Agent 工具描述。

---

## 四、🟢 小问题 / 代码风格

### 14. 导入风格不统一

- `mcp_server/tools/` 内部使用相对导入 `from .calculator import Calculator` ✅
- `agent/` 使用绝对导入 `from src.mcp_client.client import MCPClient`
- 建议全项目统一为绝对导入

### 15. LLM 客户端重复创建

`core.py` 和 `rag.py` 各自独立创建了 OpenAI 客户端，用同样的 API Key/Base URL。应该抽取共享实例。

### 16. `rag_tool.py` —— read 操作的错误信息有误

```python
if val is None:
    return f"笔记:[{val}]不存在"
```

会输出 `笔记:[None]不存在`，应为 `f"笔记 [{key}] 不存在"`。

### 17. `prompt.py` 工具信息与 MCP 注册重复

Prompt 里手写了工具名称和用法，同时 MCP Server 也通过 Schema 注册了工具定义。LLM 收到两套信息。

**建议:** Prompt 只写行为规则和示例，工具定义通过 MCP Schema 传递即可。

### 18. `scripts/ingest_docs.py` —— 缺少错误处理

文件读取、向量化过程中任何异常都会导致脚本崩溃。应该有 try/except。

### 19. `.gitignore` 排除了 `docs/` 整个目录

```gitignore
docs/
```

但 `docs/` 里放的是项目文档（产品知识库、面试记录），这些应该被版本控制。建议只排除 `chroma_data/` 和 `*.log`。

### 20. `requirements.txt` 缺少 `ddgs` 和 `beautifulsoup4`

`web_serach.py` 中 `from ddgs import DDGS` 和 `from bs4 import BeautifulSoup` 依赖未在 requirements.txt 中声明。

---

## 五、架构建议

### MCP Client 生命周期管理

当前每个 `run()` 都创建/销毁 MCPClient（子进程）。建议：

```python
# FastAPI 启动时创建全局 MCPClient
@app.on_event("startup")
async def startup():
    mcp_client = await MCPClient().__aenter__()
    app.state.mcp_client = mcp_client
```

### Agent → Tool 调用链路优化

当前链路：Agent → MCP Client (stdio) → MCP Server (子进程) → Tool

对于本地 Tools，4 个工具都运行在同一个进程中，MCP stdio 通信是多此一举。建议：
- **短期:** 保留 MCP 架构，因为它是设计目标
- **长期:** 考虑将高频工具做成 `in-process` 调用，MCP 用于远程/插件化工具

### 日志系统

`logger_handler.py` 每条日志同时写控制台和文件，且文件按天滚动。建议增加日志级别配置和日志轮转（RotatingFileHandler），避免单日日志过大。

---

## 六、总结

| 类别 | 数量 | 关键项 |
|------|------|--------|
| 🔴 严重 | 4 | API Key 泄露、eval 安全、类变量共享、GBK 编码 |
| 🟡 中等 | 9 | 子进程开销、硬编码、爬虫脆弱、死代码、同步阻塞等 |
| 🟢 轻微 | 7 | 导入风格、重复创建、拼写错误等 |
| **总计** | **20** | |

**核心建议优先级:**
1. 🔥 修复 `eval` 安全漏洞（加返回值拦截）
2. 🔥 `NoteTool._store` 改为实例变量
3. 🔥 去掉 GBK 编码转换
4. 清理死代码
5. 替换 Bing 爬虫为正式 API
6. 复用 MCP Client 连接

整体代码质量中等偏上，架构思路清晰，演进轨迹明确。主要问题集中在安全性和工程细节上，核心流程没有设计硬伤。
