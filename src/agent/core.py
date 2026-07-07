from dotenv import load_dotenv
load_dotenv(override=True)

from src.mcp_client.client import MCPClient
from src.agent.prompt import SYSTEM_PROMPT
from src.utils.logger_handler import logger
from src.agent.langchain_tools import build_langchain_tools_async
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
import os


async def run(user_input: str, history: list | None = None) -> tuple[str, list]:
    """
    执行一次对话,返回 (最终答案, 更新后的消息历史)
        - history: 传入上轮的消息历史（OpenAI 格式 dict 列表），None 表示新对话
        - 返回 (answer, messages) 元组，messages 可传入下一次
    """
    async with MCPClient() as mcp:
        tools = await build_langchain_tools_async(mcp)

        llm = ChatOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
            model=os.getenv("LLM_MODEL", "deepseek-v4-flash"),
            temperature=0.3,
        )

        agent = create_react_agent(llm, tools, version="v2")

        lc_messages = []
        if history is None:
            lc_messages.append(SystemMessage(content=SYSTEM_PROMPT))
        else:
            for msg in history:
                role = msg["role"]
                content = msg.get("content", "")
                if role == "system":
                    lc_messages.append(SystemMessage(content=content))
                elif role == "user":
                    lc_messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    lc_messages.append(AIMessage(content=content))

        lc_messages.append(HumanMessage(content=user_input))

        result = await agent.ainvoke({"messages": lc_messages})

        all_msgs = result["messages"]
        answer = all_msgs[-1].content

        updated_history = []
        for msg in all_msgs:
            if isinstance(msg, SystemMessage):
                updated_history.append({"role": "system", "content": msg.content})
            elif isinstance(msg, HumanMessage):
                updated_history.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                updated_history.append({"role": "assistant", "content": msg.content})

        return answer, updated_history
