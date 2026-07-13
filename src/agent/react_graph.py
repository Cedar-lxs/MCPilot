"""用 LangGraph 替换手写 ReAct 循环"""
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
import os
import json
from src.mcp_client.client import MCPClient

load_dotenv(override=True)
MODEL = os.getenv("LLM_MODEL", "deepseek-v4-flash")
API_KEY = os.getenv("OPENAI_API_KEY")
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "10"))
TEMPERATURE = float(os.getenv("AGENT_TEMPERATURE", "0.3"))
BASE_URL = os.getenv("OPENAI_BASE_URL")

# LLM 客户端
llm = ChatOpenAI(
    model=MODEL,
    api_key=API_KEY,
    base_url=BASE_URL,
    temperature=TEMPERATURE,
    max_tokens = MAX_TOKENS
)

# 构造带工具绑定的LLM 
llm_with_tools = None  # 等外部调用时传 tools 进来再绑定


async def get_tools(mcp_client: MCPClient) -> list:
    """从 MCP 获取工具列表，转成 LangChain tool 格式，保留完整参数定义"""
    from langchain_core.tools import StructuredTool
    from langchain_core.utils.json_schema import dereference_refs

    mcp_tools = await mcp_client.list_tools()
    tools = []

    def _make_coro(tool_name: str, client: MCPClient):
        """创建工具异步调用函数"""
        async def _run(**kwargs) -> str:
            return await client.call_tool(tool_name, kwargs)
        return _run

    for t in mcp_tools:
        tool = StructuredTool(
            name=t.name,
            description=t.description or "",
            args_schema=dereference_refs(t.inputSchema) if t.inputSchema else None,
            func=None,
            coroutine=_make_coro(t.name, mcp_client),
        )
        tools.append(tool)

    return tools


# 构建图 
def build_graph(tools: list) -> object:
    """传入工具列表，构建并编译 LangGraph"""
    # 每个 graph 实例绑定自己的 llm_with_tools，互不干扰
    llm_with_tools = llm.bind_tools(tools)

    # Agent 节点 — 定义在 build_graph 内部，闭包捕获上面的 llm_with_tools
    async def agent_node(state: MessagesState) -> dict:
        response = await llm_with_tools.ainvoke(state["messages"])
        return {"messages": [response]}
    

    builder = StateGraph(MessagesState)

    # 节点
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(tools))

    # 边
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        tools_condition,
        {"tools": "tools", END: END},
    )
    builder.add_edge("tools", "agent")

    return builder.compile()