import json, os
from pathlib import Path
# 加载.env
from dotenv import load_dotenv
load_dotenv(override=True)

from openai import OpenAI

# from src.mcp_server.tools.calculator import Calculator
# from src.mcp_server.tools.note import NoteTool
# from src.mcp_server.tools.web_serach import WebSearchTool
from src.mcp_client.client import MCPClient
from src.agent.prompt import SYSTEM_PROMPT
from src.utils.logger_handler import logger

# 加载工具实例列表
# _TOOLS: list = [Calculator(), NoteTool(), WebSearchTool()]

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
)
Model = os.getenv("LLM_MODEL", "deepseek-v4-flash") # 默认使用 deepseek-v4-flash 模型


# def _build_tool_definitions() -> list[dict]:
#     """"把工具定义转换成OpenAI function calling的格式"""
#     tools = []
#     for tool in _TOOLS:
#         definition = tool.get_definition()
#         tools.append({
#             "type": "function",
#             "function": {
#                 "name": definition["name"],
#                 "description": definition["description"],
#                 "parameters": definition["inputSchema"],
#             }
#         })
#     return tools


# async def _execute_tool(name: str, arguments: dict) -> str:
#     """执行工具调用, 返回结果字符串"""
#     for tool in _TOOLS:
#         if tool.get_definition()["name"] == name:
#             """
#             这里注意两点：

#             async def — 因为工具的 execute() 方法都是 async 的
#             **arguments — 把参数字典解包传进去，每个工具需要的参数不一样
#             敲进去，敲完说一声。🦊
#             """
#             result = await tool.execute(**arguments)
#             return result
        

# async def run(user_input: str) -> str:
#     """
#         执行一次对话,返回最终答案
#         run()函数, 一次性对话的逻辑,最核心的一步
#     """
#     messages = [
#         {"role": "system", "content": SYSTEM_PROMPT},
#         {"role": "user", "content": user_input},
#     ]

#     tools = _build_tool_definitions()

#     for _ in range(10):
#         # 最多10步, 防止无限循环
#         response = client.chat.completions.create(
#             model=Model,
#             messages=messages,
#             tools=tools,
#             tool_choice = "auto", # 让 LLM 自己决定调不调工具
#         )

#         message = response.choices[0].message

#         # 情况1: LLM需要调工具
#         if message.tool_calls:

#             print(f"🤔 思考过程: {message.content}")
#             print(f"🔧 调用的工具: {[tc.function.name for tc in message.tool_calls]}")

#             if message.content is None or message.content == "":
#             # DeepSeek 调工具时 content 可能为空，给个占位文本
#                 message.content = f"我需要调用 {[tc.function.name for tc in message.tool_calls]} 来获取信息"

#             # 把带有tool_calls的消息加入上下文,把 LLM 的 tool_calls 消息存进历史
#             messages.append(message) 

#             for tc in message.tool_calls:
#                 tool_name = tc.function.name
#                 tool_args = json.loads(tc.function.arguments)
#                 result = await _execute_tool(tool_name, tool_args)

#                 messages.append({
#                     "role": "tool",
#                     "tool_call_id": tc.id,    # Deepseek兼容要求的是该参数
#                     # "name": tool_name,
#                     "content": result
#                 })
        
#         # 情况2: LLM直接给出最终答案
#         else:
#             return message.content
        
#     logger.error("超过最大循环次数,未能得到最终答案")
#     return "超过最大循环次数,未能得到最终答案"



async def run(user_input: str, history: list | None = None) -> tuple[str, list]:
    """
    执行一次对话,返回 (最终答案, 更新后的消息历史)
        - history: 传入上轮的消息历史，None 表示新对话
        - 返回 (answer, messages) 元组，messages 可传入下一次
    """

    # 新对话 → 建 system → 加 user；续对话 → 复制历史 → 追加 user。
    if history is None:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    else:
        messages = list(history)
    messages.append({"role": "user", "content": user_input})

    # 获取工具定义列表
    # tools = _build_tool_definitions()
    async with MCPClient() as mcp:
        mcptools = await mcp.list_tools()
        tools = mcp.to_openai_tools(mcptools)

        for _ in range(10):
            # 最多10步, 防止无限循环
            response = client.chat.completions.create(
                model=Model,
                messages=messages,
                tools=tools,
                tool_choice = "auto", # 让 LLM 自己决定调不调工具
            )

            message = response.choices[0].message

            # 情况1: LLM需要调工具
            if message.tool_calls:

                print(f"🤔 思考过程: {message.content}")
                print(f"🔧 调用的工具: {[tc.function.name for tc in message.tool_calls]}")

                if message.content is None or message.content == "":
                # DeepSeek 调工具时 content 可能为空，给个占位文本
                    message.content = f"我需要调用 {[tc.function.name for tc in message.tool_calls]} 来获取信息"

                # 把带有tool_calls的消息加入上下文,把 LLM 的 tool_calls 消息存进历史
                messages.append(message) 

                for tc in message.tool_calls:
                    tool_name = tc.function.name
                    tool_args = json.loads(tc.function.arguments)
                    result = await mcp.call_tool(tool_name, tool_args)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,    # Deepseek兼容要求的是该参数
                        # "name": tool_name,
                        "content": result
                    })
            
            # 情况2: LLM直接给出Final Answer
            else:
                messages.append({"role": "assistant", "content": message.content})
                return message.content, messages
            
        logger.error(f"超过最大循环次数,未能得到最终答案{messages}")
        return "超过最大循环次数,未能得到最终答案", messages
        
        

