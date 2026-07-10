import math
import re
from src.utils.logger_handler import logger


class Calculator():
    """安全计算器,只允许基础算术运算"""

    # 只允许数字、运算符、空格
    ALLOWED_PATTERN = re.compile(r"^[\d+\-*/().%\s]+$")


    # 回答MCP CLIENT的问题: 你是什么? 告诉外面 "我有什么能力、要什么参数"
    def get_definition(self) -> dict:  
        return{
            "name":"calculator",           # 工具名:calculator
            "description":"执行数学计算,支持+ - * / % ( )",   # 描述--LLM根据这个 决定要不要调用它
            "inputSchema": {                #参数定义,告诉LLM传什么参数
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式，如 (12 + 34) * 5",
                    },
                },
                "required": ["expression"],        # 该参数必须填写
            },
        }
    

    async def execute(self, expression: str) -> str:
        """安全执行数学表达式"""
        # 安全检查 — 不通过直接返回，不执行 eval
        if not self.ALLOWED_PATTERN.match(expression):
            logger.error(f"表达式包含不允许的字符: {expression}")
            return f"错误：表达式包含不允许的字符，仅支持数字和 + - * / ( ) %"

        try:
            # eval 但限制命名空间，只暴露 math 模块
            # 这样用户只能调 math 里的函数（如 math.sqrt），调不了 os、sys 等
            result = eval(expression, {"__builtins__": {}}, {"math": math})
            return f"{expression} = {result}"
        except Exception as e:
            logger.error(f"[calculator execute]计算错误: {e}")
            return f"计算错误: {e}"
            