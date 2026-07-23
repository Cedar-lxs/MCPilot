"""MCP Tool: 当前日期时间"""
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.utils.logger_handler import logger


class DateTimeTool:
    """为 Agent 提供真实当前时间，避免依赖模型训练截止日期。"""

    def get_definition(self) -> dict:
        return {
            "name": "datetime_now",
            "description": "获取真实当前日期、时间、日期时间或 Unix 时间戳，解决 Agent 对当前时间缺乏感知的问题",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "format": {
                        "type": "string",
                        "enum": ["date", "time", "datetime", "timestamp", "iso"],
                        "description": "返回格式: date=日期, time=时间, datetime=日期时间, timestamp=Unix时间戳, iso=ISO 8601格式",
                    },
                    "timezone": {
                        "type": "string",
                        "description": "IANA 时区名称，如 Asia/Shanghai、UTC；默认 Asia/Shanghai",
                    },
                },
                "required": [],
            },
        }

    async def execute(self, format: str = "datetime", timezone: str = "Asia/Shanghai") -> str:
        """返回指定时区的当前日期时间。"""
        logger.info(f"获取当前日期时间: format={format}, timezone={timezone}")

        try:
            tz = ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            return f"未知时区: {timezone}，请使用 IANA 时区名称，如 Asia/Shanghai、UTC"

        now = datetime.now(tz)

        if format == "date":
            return f"当前日期: {now:%Y-%m-%d} ({timezone})"
        if format == "time":
            return f"当前时间: {now:%H:%M:%S} ({timezone})"
        if format == "datetime":
            return f"当前日期时间: {now:%Y-%m-%d %H:%M:%S} ({timezone})"
        if format == "timestamp":
            return f"当前 Unix 时间戳: {int(now.timestamp())}"
        if format == "iso":
            return f"当前 ISO 时间: {now.isoformat()}"

        return "未知格式: {format}，可选: date, time, datetime, timestamp, iso".format(format=format)
