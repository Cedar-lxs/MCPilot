"""MCPilot — MCP 服务主入口 (stdio 模式)
启动 stdin/stdout 的 MCP 服务，等客户端发 JSON-RPC 请求过来，
路由到 tools/server.py 里注册好的 list_tools 和 call_tool 处理，把
结果写回 stdout。
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from mcp.server.stdio import stdio_server
from mcp.server.models import InitializationOptions
from src.mcp_server.tools.server import app
from mcp.server import NotificationOptions


async def main():
    """
        进入 stdio_server 的上下文 = 启动 stdin 读取循环 + stdout 写入循环。它会在后台跑两个协程：

        stdin_reader — 不断读 stdin 的行，解析成 JSON-RPC 消息
        stdout_writer — 不断把返回的消息写回 stdout
        拿到两个流之后丢给 app.run()。

        await app.run(read_stream, write_stream, InitializationOptions(...))

        这是 MCP Server 的主循环：

        创建 ServerSession — 跟客户端建立会话
        循环收消息 → 分发给对应的 handler（list_tools → 你的 list_tools() 函数，call_tool → 你的 call_tool() 函数）→ 返回结果
        直到连接断开
    """
    async with stdio_server() as (read_stream, write_stream): 
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="MCPilot",
                server_version="0.1.0",
                capabilities=app.get_capabilities(
                    NotificationOptions(),
                    {},
                ),
            ),
        )


if __name__ == "__main__":
    # asyncio.run() 是 Python 3.7+ 的 async 入口。把 main() 这个协程放进事件循环里跑。
    asyncio.run(main())
