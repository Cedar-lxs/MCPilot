import ast
import operator
import re
from src.utils.logger_handler import logger


class Calculator():
    """安全计算器,只允许基础算术运算"""

    # 只允许数字、运算符、空格
    ALLOWED_PATTERN = re.compile(r"^[\d+\-*/().%\s]+$")

    _BIN_OPS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Mod: operator.mod,
    }
    _UNARY_OPS = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    def get_definition(self) -> dict:
        return {
            "name": "calculator",
            "description": "执行数学计算,支持+ - * / % ( )",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式，如 (12 + 34) * 5",
                    },
                },
                "required": ["expression"],
            },
        }

    def _eval_node(self, node):
        """只允许字面量与四则运算的 AST 求值，不使用 eval"""
        if isinstance(node, ast.Expression):
            return self._eval_node(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp):
            op = self._BIN_OPS.get(type(node.op))
            if op is None:
                raise ValueError(f"不支持的运算符: {type(node.op).__name__}")
            return op(self._eval_node(node.left), self._eval_node(node.right))
        if isinstance(node, ast.UnaryOp):
            op = self._UNARY_OPS.get(type(node.op))
            if op is None:
                raise ValueError(f"不支持的一元运算符: {type(node.op).__name__}")
            return op(self._eval_node(node.operand))
        raise ValueError(f"不支持的表达式节点: {type(node).__name__}")

    async def execute(self, expression: str) -> str:
        """安全执行数学表达式"""
        if not self.ALLOWED_PATTERN.match(expression):
            logger.error(f"表达式包含不允许的字符: {expression}")
            return f"错误：表达式包含不允许的字符，仅支持数字和 + - * / ( ) %"

        try:
            tree = ast.parse(expression, mode="eval")
            result = self._eval_node(tree)
            return f"{expression} = {result}"
        except Exception as e:
            logger.error(f"[calculator execute]计算错误: {e}")
            return f"计算错误: {e}"
