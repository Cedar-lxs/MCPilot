"""测试 datetime 工具"""
import re

import pytest

from src.mcp_server.tools.datetime_tool import DateTimeTool


@pytest.fixture
def datetime_tool():
    return DateTimeTool()


def test_definition(datetime_tool: DateTimeTool):
    definition = datetime_tool.get_definition()
    assert definition["name"] == "datetime_now"
    assert "format" in definition["inputSchema"]["properties"]
    assert "timezone" in definition["inputSchema"]["properties"]


@pytest.mark.asyncio
async def test_default_datetime(datetime_tool: DateTimeTool):
    result = await datetime_tool.execute()
    assert "当前日期时间" in result
    assert "Asia/Shanghai" in result
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("format", "expected"),
    [
        ("date", "当前日期"),
        ("time", "当前时间"),
        ("datetime", "当前日期时间"),
        ("timestamp", "当前 Unix 时间戳"),
        ("iso", "当前 ISO 时间"),
    ],
)
async def test_supported_formats(datetime_tool: DateTimeTool, format: str, expected: str):
    result = await datetime_tool.execute(format=format, timezone="UTC")
    assert expected in result


@pytest.mark.asyncio
async def test_invalid_timezone(datetime_tool: DateTimeTool):
    result = await datetime_tool.execute(timezone="No/Such_Zone")
    assert "未知时区" in result


@pytest.mark.asyncio
async def test_invalid_format(datetime_tool: DateTimeTool):
    result = await datetime_tool.execute(format="unknown")
    assert "未知格式" in result
