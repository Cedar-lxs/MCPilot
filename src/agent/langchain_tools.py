"""MCP Tool → LangChain BaseTool 适配层"""

from typing import Any, Optional, Type
from langchain.tools import BaseTool
from pydantic import BaseModel, Field, create_model


def _json_to_python_type(json_type: str) -> type:
    """将 JSON Schema 类型名映射为 Python 类型"""
    mapping = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    return mapping.get(json_type, str)


def _build_input_model(name: str, schema: dict) -> Type[BaseModel]:
    """将 MCP JSON Schema 转为 Pydantic BaseModel"""
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    fields = {}
    for field_name, prop in properties.items():
        is_required = field_name in required
        json_type = prop.get("type", "string")
        py_type = _json_to_python_type(json_type)

        if not is_required:
            py_type = Optional[py_type]
        fields[field_name] = (
            py_type,
            Field(description=prop.get("description", ""),
        ))

    return create_model(f"{name}Input", **fields)


class _DynamicTool(BaseTool):
    """通过 MCP Client 调用实际工具的动态包装器"""

    mcp_client: Any = None
    tool_name: str = ""

    async def _arun(self, **kwargs) -> str:
        return await self.mcp_client.call_tool(self.tool_name, kwargs)

    def _run(self, **kwargs) -> str:
        raise NotImplementedError("请使用异步调用")


async def build_langchain_tools_async(mcp_client) -> list[BaseTool]:
    """从 MCP Client 获取工具列表，每个工具包装成 BaseTool"""
    mcptools = await mcp_client.list_tools()

    tools = []
    for mt in mcptools:
        model = _build_input_model(mt.name, mt.inputSchema)
        tool = _DynamicTool(
            name=mt.name,
            description=mt.description or "",
            args_schema=model,
            mcp_client=mcp_client,
            tool_name=mt.name,
        )
        tools.append(tool)
    return tools
