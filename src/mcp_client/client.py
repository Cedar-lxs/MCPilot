"""MCPilot — MCP 客户端主入口 (stdio 模式)"""
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from contextlib import AsyncExitStack


class MCPClient:
    """通过 stdio 连接 MCP Server，动态发现和调用工具"""

    def __init__(self):
        self._session = None
        self._exit_stack = AsyncExitStack()

    async def __aenter__(self):
        """启动 MCP Server 子进程 → 建立 stdio 连接 → 初始化会话"""
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "src.mcp_server.server"],
        )

        streams = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        read_stream, write_stream = streams

        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await self._session.initialize()
        return self

    async def __aexit__(self, *args):
        await self._exit_stack.aclose()

    async def list_tools(self):
        """获取 MCP Server 注册的所有工具"""
        if not self._session:
            raise RuntimeError("MCP Client 未连接，请先调用 connect()")
        result = await self._session.list_tools()
        return result.tools

    async def call_tool(self, name: str, arguments: dict = None):
        """调用 MCP Server 上的工具，返回文本结果"""
        if not self._session:
            raise RuntimeError("MCP Client 未连接，请先调用 connect()")
        result = await self._session.call_tool(name, arguments or {})
        texts = [item.text for item in result.content if hasattr(item, "text")]
        return "\n".join(texts) if texts else "(无返回内容)"
