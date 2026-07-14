"""测试 calculator 工具"""
import pytest

from src.mcp_server.tools.calculator import Calculator


@pytest.fixture
def calc():
    return Calculator()


@pytest.mark.asyncio
async def test_basic_arithmetic(calc: Calculator):
    result = await calc.execute("2 + 3")
    assert "2 + 3 = 5" == result


@pytest.mark.asyncio
async def test_multiplication(calc: Calculator):
    result = await calc.execute("12 * 34")
    assert "12 * 34 = 408" == result


@pytest.mark.asyncio
async def test_parentheses(calc: Calculator):
    result = await calc.execute("(12 + 34) * 5")
    assert "(12 + 34) * 5 = 230" == result


@pytest.mark.asyncio
async def test_division(calc: Calculator):
    result = await calc.execute("100 / 4")
    assert "100 / 4 = 25.0" == result


@pytest.mark.asyncio
async def test_modulo(calc: Calculator):
    result = await calc.execute("10 % 3")
    assert "10 % 3 = 1" == result


@pytest.mark.asyncio
async def test_negative_numbers(calc: Calculator):
    result = await calc.execute("-5 + 10")
    assert "-5 + 10 = 5" == result


@pytest.mark.asyncio
async def test_rejects_dangerous_input(calc: Calculator):
    """禁止执行 eval 类攻击"""
    result = await calc.execute("__import__('os').system('dir')")
    assert "包含不允许的字符" in result
