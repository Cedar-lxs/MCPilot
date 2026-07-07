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

from langchain_core.callbacks import BaseCallbackHandler


class _AgentThoughtHandler(BaseCallbackHandler):
    """只打印 Agent 的关键思考步骤"""

    def on_llm_start(self, serialized, prompts, **kwargs):
        pass  # 不打印原始的 prompt

    def on_agent_action(self, action, **kwargs):
        print(f"  🛠️ 调用工具: {action.tool}")
        print(f"     参数: {action.tool_input}")

    def on_agent_finish(self, finish, **kwargs):
        print(f"  ✅ 最终答案: {finish.return_values['output']}")

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
        # debug=True 会把 LangGraph 的全部内部状态切换都吐出来，调试用
        # agent = create_react_agent(llm, tools, version="v2", debug= True)
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

        # 自定义回调处理器
        handler = _AgentThoughtHandler()
        result = await agent.ainvoke(
            {"messages": lc_messages},
            config={"callbacks": [handler]} # 自定义 Callback，只打印 Agent 思考过程
        )

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
