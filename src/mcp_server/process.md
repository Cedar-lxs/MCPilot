完整运行流程，从你敲命令到工具被执行，六个阶段：

---

### 阶段 1：启动

```bash
python -m src.mcp_server.server
```

Python 加载 `src/mcp_server/server.py`，开始执行文件顶层的所有代码。

---

### 阶段 2：import 链（初始化）

```
server.py 开始执行
  │
  ├─ import asyncio / sys / Path
  │
  ├─ from mcp.server.stdio import stdio_server
  ├─ from mcp.server.models import InitializationOptions
  │
  └─ from src.mcp_server.tools.server import app
                       │
                       ▼
           tools/server.py 开始执行
             │
             ├─ from mcp.server import Server
             ├─ from mcp.types import Tool, TextContent
             ├─ from .calculator import Calculator      ← 加载工具类
             ├─ from .note import NoteTool
             ├─ from .web_serach import WebSearchTool
             │
             ├─ app = Server("MCPilot")                ← 创建服务实例
             ├─ _TOOLS = [Calculator(), ...]           ← 实例化工具
             │
             ├─ @app.list_tools() → 注册 list_tools    ← 挂载处理器
             ├─ @app.call_tool()  → 注册 call_tool
             │
             └─ 返回 app 给 server.py
```

**关键：** 工具在 import 时就已经注册到 `app` 实例上了。

---

### 阶段 3：进入 `main()`

```python
if __name__ == "__main__":
    asyncio.run(main())
```

拉起事件循环，跑 `main()` 协程。

---

### 阶段 4：stdio 就绪

```python
async with stdio_server() as (read_stream, write_stream):
```

`stdio_server()` 在后台拉起两个协程：

```
stdin_reader  ← 异步循环，不断读 sys.stdin 的行
stdout_writer ← 异步循环，不断把消息写回 sys.stdout

      ↓                      ↓
read_stream           write_stream
（接收客户端请求）      （返回响应）
```

---

### 阶段 5：MCP 协议循环

```python
await app.run(read_stream, write_stream, InitializationOptions(...))
```

`app.run()` 进入主循环：

```
                              ┌─────────────────┐
                              │  app.run() 主循环 │
                              └────────┬────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                  ▼                  ▼
              客户端发请求       app 收到消息         app 返回响应
                    │                  │                  │
                    ▼                  ▼                  ▼
             JSON-RPC 行      ┌─────────────────┐     JSON-RPC 行
           → stdin_reader     │  路由分发        │   ← stdout_writer
           → read_stream      │                 │     ← write_stream
                              │  tools/list     │
                              │    → list_tools()│
                              │                 │
                              │  tools/call     │
                              │    → call_tool() │
                              └─────────────────┘
```

**具体到 MCP 协议交互：**

```
Client → Server:   tools/list                  (获取工具列表)
Server → Client:   [calculator, note_take, web_search]   (返回注册的工具)

Client → Server:   tools/call { name: "calculator",
                                arguments: { expression: "(12+34)*5" } }
Server → Client:   (12 + 34) * 5 = 230
```

---

### 阶段 6：退出

连接断开 → `app.run()` 结束 → `async with stdio_server()` 退出 → 后台协程自动清理 → 进程结束。

---

### 整条链路概览

```
你敲命令
    │
    ▼
python -m src.mcp_server.server
    │
    ▼
import tools → 注册 Calculator / NoteTool / WebSearchTool
    │
    ▼
stdio_server() → 包装 stdin/stdout 为异步流
    │
    ▼
app.run() → 循环收消息、路由、返回结果
    │
    ▼
客户端断连 → 清理退出
```

有任何一段不够清楚吗？🦊