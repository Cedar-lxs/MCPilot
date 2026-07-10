"""
    MCPilot — MCP 客户端主入口 (stdio 模式)
    启动 stdin/stdout 的 MCP 客户端，等服务端发 JSON-RPC 请求过来，
    路由到 tools/client.py 里注册好的 list_tools 和 call_tool 处理
"""
import sys

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from src.utils.logger_handler import logger
from contextlib import AsyncExitStack


class MCPClient:
    """通过 stdio 连接 MCP Server，动态发现和调用工具

    支持两种用法：
    1. 上下文管理器:  async with MCPClient() as mcp: ...
    2. 手动生命周期:  await mcp.connect() / await mcp.close()
    """

    def __init__(self):
        self._session = None
        self._exit_stack = AsyncExitStack()
        self._connected = False

    async def connect(self):
        """显式连接 MCP Server（可替代 __aenter__）"""
        if self._connected:
            return self
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
        self._connected = True
        return self

    async def close(self):
        """显式断开连接（可替代 __aexit__）"""
        if self._connected:
            await self._exit_stack.aclose()
            self._connected = False
            self._session = None

    async def __aenter__(self):
        return await self.connect()

    async def __aexit__(self, *args):
        await self.close()

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

    def to_openai_tools(self, mcptools: list):
        """将 MCP Tool 定义转换为 OpenAI Function Calling 格式"""
        openai_tools = []
        for tool in mcptools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema,
                },
            })
        return openai_tools
