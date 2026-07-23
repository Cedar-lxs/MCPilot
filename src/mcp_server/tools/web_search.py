"""MCP Tool: Bocha AI structured web search."""

from typing import Any

import httpx

from src.utils.config import BOCHA_API_KEY, SEARCH_MAX_RESULTS, SEARCH_TIMEOUT_SECONDS
from src.utils.logger_handler import logger


class WebSearchTool:
    """通过博查 AI 获取结构化网页搜索结果。"""

    SEARCH_URL = "https://api.bochaai.com/v1/web-search"
    FRESHNESS_TO_BOCHA = {
        "Day": "oneDay",
        "Week": "oneWeek",
        "Month": "oneMonth",
    }

    def __init__(
        self,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        max_results_limit: int | None = None,
    ) -> None:
        self.api_key = BOCHA_API_KEY if api_key is None else api_key
        self.timeout_seconds = (
            SEARCH_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
        )
        self.max_results_limit = (
            SEARCH_MAX_RESULTS if max_results_limit is None else max_results_limit
        )

    def get_definition(self) -> dict:
        return {
            "name": "web_search",
            "description": "使用博查 AI 搜索互联网最新公开信息",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "最大返回结果数",
                        "default": 3,
                        "minimum": 1,
                    },
                    "freshness": {
                        "type": "string",
                        "enum": ["", "Day", "Week", "Month"],
                        "description": "时间范围：Day(一天内)、Week(一周内)、Month(一月内)，不传则不限定",
                        "default": "",
                    },
                },
                "required": ["query"],
            },
        }

    async def execute(self, query: str, max_results: int = 3, freshness: str = "") -> str:
        error = self._validate_arguments(query, max_results, freshness)
        if error:
            return error
        if not self.api_key:
            logger.error("博查 API Key 未配置")
            return "搜索服务未配置：请设置 BOCHA_API_KEY 后重试"

        query = query.strip()
        requested_count = min(max_results, self.max_results_limit)
        payload: dict[str, Any] = {
            "query": query,
            "count": requested_count,
        }
        if freshness:
            payload["freshness"] = self.FRESHNESS_TO_BOCHA[freshness]

        logger.info(
            "调用博查搜索: query=%s, max_results=%s, freshness=%s",
            query,
            requested_count,
            freshness or "不限",
        )
        try:
            async with self._create_client() as client:
                response = await client.post(
                    self.SEARCH_URL,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                response.raise_for_status()
                response_payload = response.json()
        except httpx.HTTPStatusError as error:
            return self._http_error_message(error.response.status_code)
        except httpx.RequestError as error:
            logger.error("博查网络请求失败: %s", error)
            return "搜索服务请求失败，请稍后重试"
        except ValueError as error:
            logger.error("博查返回的不是有效 JSON: %s", error)
            return "搜索服务返回的数据格式异常，请稍后重试"

        if not isinstance(response_payload, dict):
            logger.error("博查返回的数据不是对象")
            return "搜索服务返回的数据格式异常，请稍后重试"
        if response_payload.get("error"):
            logger.error("博查返回错误: %s", response_payload["error"])
            return "搜索服务返回错误，请检查博查 API 配额和配置后重试"

        data = response_payload.get("data")
        if data is None:
            data = response_payload
        if not isinstance(data, dict):
            logger.error("博查响应 data 字段不是对象")
            return "搜索服务返回的数据格式异常，请稍后重试"
        web_pages = data.get("webPages")
        if not isinstance(web_pages, dict):
            logger.error("博查缺少 webPages 对象")
            return "搜索服务返回的数据格式异常，请稍后重试"
        results = web_pages.get("value")
        if not isinstance(results, list):
            logger.error("博查 webPages 缺少 value 列表")
            return "搜索服务返回的数据格式异常，请稍后重试"
        return self._format_results(query, results[:requested_count])

    def _create_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True)

    def _validate_arguments(self, query: str, max_results: int, freshness: str) -> str | None:
        if not isinstance(query, str) or not query.strip():
            return "query 不能为空"
        if (
            not isinstance(max_results, int)
            or isinstance(max_results, bool)
            or not 1 <= max_results <= self.max_results_limit
        ):
            return f"max_results 必须是 1 到 {self.max_results_limit} 之间的整数"
        if freshness not in self.FRESHNESS_TO_BOCHA and freshness != "":
            return "freshness 仅支持 Day、Week、Month 或空值"
        return None

    def _http_error_message(self, status_code: int) -> str:
        logger.error("博查请求失败: HTTP %s", status_code)
        if status_code in {401, 403}:
            return "搜索服务认证失败，请检查 BOCHA_API_KEY"
        if status_code == 429:
            return "搜索服务请求过于频繁或配额已用尽，请稍后重试"
        if 500 <= status_code < 600:
            return "搜索服务暂时不可用，请稍后重试"
        return f"搜索服务请求失败（HTTP {status_code}）"

    @staticmethod
    def _format_results(query: str, results: list[dict[str, Any]]) -> str:
        lines = []
        for item in results:
            if not isinstance(item, dict):
                continue
            title = str(item.get("name") or "无标题")
            link = str(item.get("url") or "")
            snippet = str(item.get("snippet") or item.get("summary") or "")
            date = item.get("datePublished")
            if date:
                snippet = f"{date} {snippet}".strip()
            lines.append(f"{len(lines) + 1}. {title}\n   {link}\n   {snippet}")

        if not lines:
            return f"未找到关于「{query}」的结果"
        return "\n\n".join(lines)
