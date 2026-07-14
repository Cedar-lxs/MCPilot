"""用 LangGraph 替换手写 ReAct 循环"""
from typing import Any

from langchain_core.tools import StructuredTool
from langchain_core.utils.json_schema import dereference_refs
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import BaseModel, Field, create_model

from src.mcp_client.client import MCPClient
from src.utils.config import (AGENT_TEMPERATURE, LLM_MAX_TOKENS, LLM_MODEL,
                               OPENAI_API_KEY, OPENAI_BASE_URL)

# LLM 客户端
llm = ChatOpenAI(
    model=LLM_MODEL,
    api_key=***
    base_url=OPENAI_BASE_URL,
    temperature=AGENT_TEMPERATURE,
    max_tokens=LLM_MAX_TOKENS,
)


# ─── JSON Schema → Pydantic Model ──────────────────────────

_JSON_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
}


def _schema_to_pydantic(name: str, schema: dict[str, Any]) -> type[BaseModel]:
    """将 MCP Tool 的 JSON Schema dict 转为 Pydantic Model 类。

    先 dereference_refs 解析 $ref 引用，再 create_model 动态生成类。
    """
    resolved = dereference_refs(schema) if schema else {}
    props = resolved.get("properties", {})
    required = set(resolved.get("required", []))

    fields: dict[str, tuple[type, Any]] = {}
    for field_name, field_schema in props.items():
        field_type = _JSON_TYPE_MAP.get(field_schema.get("type", "string"), str)
        description = field_schema.get("description", "")

        if field_name in required:
            fields[field_name] = (field_type, Field(..., description=description))
        elif "default" in field_schema:
            fields[field_name] = (
                field_type,
                Field(default=field_schema["default"], description=description),
            )
        else:
            fields[field_name] = (
                field_type | None,
                Field(default=None, description=description),
            )

    return create_model(f"{name}_Input", **fields) if fields else create_model(f"{name}_Input")


# ─── MCP Tools → LangChain StructuredTool ──────────────────

async def get_tools(mcp_client: MCPClient) -> list[StructuredTool]:
    """从 MCP 获取工具列表，转成 LangChain StructuredTool 列表。

    返回的 list[StructuredTool] 同时满足：
    - llm.bind_tools()  → 底层转为 OpenAI function calling dict
    - ToolNode(tools)   → 作为 LangGraph 工具节点消费
    """
    mcp_tools = await mcp_client.list_tools()
    tools: list[StructuredTool] = []

    def _make_coro(tool_name: str, client: MCPClient):
        """创建工具异步调用函数——工厂函数避免闭包延迟绑定"""
        async def _run(**kwargs: Any) -> str:
            return await client.call_tool(tool_name, kwargs)
        return _run

    for t in mcp_tools:
        tool = StructuredTool(
            name=t.name,
            description=t.description or "",
            args_schema=_schema_to_pydantic(t.name, t.inputSchema or {}),
            func=None,
            coroutine=_make_coro(t.name, mcp_client),
        )
        tools.append(tool)

    return tools


# ─── LangGraph 构建 ─────────────────────────────────────────

def build_graph(tools: list[StructuredTool]) -> CompiledStateGraph:
    """传入工具列表，构建并编译 LangGraph"""
    llm_with_tools = llm.bind_tools(tools)

    async def agent_node(state: MessagesState) -> dict:
        response = await llm_with_tools.ainvoke(state["messages"])
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(tools))

    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        tools_condition,
        {"tools": "tools", END: END},
    )
    builder.add_edge("tools", "agent")

    return builder.compile()
