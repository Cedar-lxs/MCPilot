# server.py - MCPilot MCP Server
import sys
from pathlib import Path

# 项目根目录(项目根目录加到 Python 路径里，让所有工具能正常 import 项目公共模块。)
ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from mcp.server import Server
from mcp.types import Tool, TextContent
import asyncio

from src.utils.logger_handler import logger
from .calculator import Calculator
from .note import NoteTool
from .web_serach import WebSearchTool

# 创建MCP实例
app = Server("MCPilot")


# 工具注册列表：加新工具在这里加一行
_TOOLS: list = [Calculator(), NoteTool(), WebSearchTool()]


@app.list_tools()
async def list_tools() -> list[Tool]:
    tools: list[Tool] = []
    for tool in _TOOLS:
        definition = tool.get_definition()
        tools.append(Tool(
            name=definition["name"],
            description=definition["description"],
            inputSchema=definition["inputSchema"],
        ))
    return tools


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    for tool in _TOOLS:
        if tool.get_definition()["name"] == name:
            result = await tool.execute(**arguments)
            return [TextContent(type="text", text=result)]
    raise ValueError(f"未知工具: {name}")


def main():
    """验证工具注册与调用"""
    print("=" * 48)
    print("  MCPilot — 工具注册验证")
    print("=" * 48)
    print()

    # 1. 验证注册列表
    print(f"已注册工具: {len(_TOOLS)} 个\n")
    for tool in _TOOLS:
        d = tool.get_definition()
        print(f"  [{d['name']}]")
        print(f"    描述: {d['description']}")
        props = d["inputSchema"]["properties"]
        reqs = d["inputSchema"].get("required", [])
        for k, v in props.items():
            required = "*" if k in reqs else " "
            print(f"    {required} {k}: {v.get('description', '')}")
        print()

    # 2. 异步验证 list_tools / call_tool
    async def _verify():
        print("-" * 48)
        print("  异步验证")
        print("-" * 48)

        tools = await list_tools()
        print(f"\n  list_tools() -> {len(tools)} 个 Tool 对象")
        for t in tools:
            print(f"    - {t.name}: {t.description[:40]}...")

        # 测试 call_tool: calculator
        result = await call_tool("calculator", {"expression": "(12 + 34) * 5"})
        print(f"\n  call_tool(calculator) -> {result[0].text}")
        print()
        print("[OK] 验证通过")

    asyncio.run(_verify())


if __name__ == "__main__":
    main()