"""MCP TOOL 网络搜索"""
from src.utils.logger_handler import logger

import httpx
from bs4 import BeautifulSoup


class WebSearchTool():
    """网络搜索工具,搜索互联网获取最新消息"""

    def get_definition(self) -> dict:
        return {
            "name": "web_search",
            "description": "搜索互联网最新消息",
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
                    },
                    "freshness": {
                        "type": "string",
                        "description": "时间范围，可选值: Day(一天内), Week(一周内), Month(一月内), 不传则不限定",
                        "default": "",
                    },
                },
                "required": ["query"],
            },
        }

    async def execute(self, query: str, max_results: int = 3, freshness: str = "") -> str:
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                params = {"q": query, "count": max_results}
                if freshness:
                    params["freshness"] = freshness
                resp = await client.get(
                    "https://www.bing.com/search",
                    params=params,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                resp.raise_for_status()
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return f"搜索失败: {e} "

        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select(".b_algo")[:max_results]

        if not items:
            return f"未找到关于「{query}」的结果"

        lines = []
        for i, item in enumerate(items, 1):
            title_el = item.select_one("h2 a")
            snippet_el = item.select_one(".b_caption p")
            title = title_el.get_text(strip=True) if title_el else "无标题"
            link = title_el.get("href", "") if title_el else ""
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            lines.append(f"{i}. {title}\n   {link}\n   {snippet}")

        return "\n\n".join(lines)
