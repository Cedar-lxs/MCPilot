"""测试完整 LangGraph Agent 调用"""
import asyncio

from langchain_core.messages import HumanMessage, SystemMessage

from src.agent.prompt import SYSTEM_PROMPT
from src.agent.react_graph import build_graph, get_tools
from src.mcp_client.client import MCPClient


async def run():
    mcp = MCPClient()
    try:
        await mcp.connect()

        tools = await get_tools(mcp)
        graph = build_graph(tools)

        print("=" * 50)
        print("问题: 1234 * 5678 等于多少？")
        print("=" * 50)

        result = await graph.ainvoke({
            "messages": [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content="1234 * 5678 等于多少？"),
            ]
        })

        print(f"\n最终回答: {result['messages'][-1].content}")
        print("\n完整消息流:")
        for i, msg in enumerate(result["messages"]):
            role = msg.type
            content = str(msg.content)[:150] if msg.content else "(工具调用)"
            print(f"  [{i}] {role}: {content}")

    finally:
        await mcp.close()


if __name__ == "__main__":
    asyncio.run(run())
