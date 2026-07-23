"""测试博查 AI 网络搜索工具。"""

import json

import httpx
import pytest

from src.mcp_server.tools.web_search import WebSearchTool


def mock_client_factory(handler):
    transport = httpx.MockTransport(handler)

    def create_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, follow_redirects=True)

    return create_client


@pytest.fixture
def search_tool() -> WebSearchTool:
    return WebSearchTool(api_key="test-key", max_results_limit=5)


def test_definition(search_tool: WebSearchTool):
    definition = search_tool.get_definition()
    properties = definition["inputSchema"]["properties"]

    assert definition["name"] == "web_search"
    assert "博查 AI" in definition["description"]
    assert properties["freshness"]["enum"] == ["", "Day", "Week", "Month"]
    assert properties["max_results"]["minimum"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"query": ""}, "query 不能为空"),
        ({"query": "test", "max_results": 0}, "max_results 必须是 1 到 5 之间的整数"),
        ({"query": "test", "max_results": True}, "max_results 必须是 1 到 5 之间的整数"),
        ({"query": "test", "freshness": "Year"}, "freshness 仅支持 Day、Week、Month 或空值"),
    ],
)
async def test_rejects_invalid_arguments(search_tool: WebSearchTool, kwargs: dict, expected: str):
    assert expected == await search_tool.execute(**kwargs)


@pytest.mark.asyncio
async def test_reports_missing_api_key():
    tool = WebSearchTool(api_key="", max_results_limit=5)
    assert "BOCHA_API_KEY" in await tool.execute("Python")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("freshness", "expected_freshness"),
    [("", None), ("Day", "oneDay"), ("Week", "oneWeek"), ("Month", "oneMonth")],
)
async def test_sends_expected_request_and_formats_results(
    search_tool: WebSearchTool,
    monkeypatch: pytest.MonkeyPatch,
    freshness: str,
    expected_freshness: str | None,
):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.host == "api.bochaai.com"
        assert request.url.path == "/v1/web-search"
        assert request.headers["Authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        assert body["query"] == "Python async"
        assert body["count"] == 2
        assert body.get("freshness") == expected_freshness
        return httpx.Response(
            200,
            json={
                "data": {
                    "webPages": {
                        "value": [
                            {
                                "name": "Asyncio documentation",
                                "url": "https://docs.python.org/3/library/asyncio.html",
                                "snippet": "Asynchronous I/O.",
                                "datePublished": "2026-07-22T00:00:00+08:00",
                            },
                            {"name": "Second result", "url": "https://example.com", "summary": "More info."},
                            {"name": "Excluded result", "url": "https://excluded.example"},
                        ]
                    }
                }
            },
            request=request,
        )

    monkeypatch.setattr(search_tool, "_create_client", mock_client_factory(handler))

    result = await search_tool.execute("Python async", max_results=2, freshness=freshness)

    assert "1. Asyncio documentation" in result
    assert "2026-07-22T00:00:00+08:00 Asynchronous I/O." in result
    assert "2. Second result" in result
    assert "Excluded result" not in result


@pytest.mark.asyncio
async def test_returns_not_found_for_empty_results(
    search_tool: WebSearchTool, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        search_tool,
        "_create_client",
        mock_client_factory(
            lambda request: httpx.Response(
                200, json={"data": {"webPages": {"value": []}}}, request=request
            )
        ),
    )

    assert await search_tool.execute("不存在的查询") == "未找到关于「不存在的查询」的结果"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (401, "搜索服务认证失败，请检查 BOCHA_API_KEY"),
        (403, "搜索服务认证失败，请检查 BOCHA_API_KEY"),
        (429, "搜索服务请求过于频繁或配额已用尽，请稍后重试"),
        (503, "搜索服务暂时不可用，请稍后重试"),
        (400, "搜索服务请求失败（HTTP 400）"),
    ],
)
async def test_handles_upstream_http_errors(
    search_tool: WebSearchTool,
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    expected: str,
):
    monkeypatch.setattr(
        search_tool,
        "_create_client",
        mock_client_factory(lambda request: httpx.Response(status_code, request=request)),
    )

    assert await search_tool.execute("Python") == expected


@pytest.mark.asyncio
async def test_handles_request_error(search_tool: WebSearchTool, monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    monkeypatch.setattr(search_tool, "_create_client", mock_client_factory(handler))

    assert await search_tool.execute("Python") == "搜索服务请求失败，请稍后重试"


@pytest.mark.asyncio
async def test_handles_invalid_json_response(search_tool: WebSearchTool, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        search_tool,
        "_create_client",
        mock_client_factory(
            lambda request: httpx.Response(200, content=b"not valid json", request=request)
        ),
    )

    assert await search_tool.execute("Python") == "搜索服务返回的数据格式异常，请稍后重试"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"data": {"webPages": {"value": "invalid"}}},
        {"error": "Invalid API key"},
    ],
)
async def test_handles_unexpected_response_payload(
    search_tool: WebSearchTool, monkeypatch: pytest.MonkeyPatch, payload: dict
):
    monkeypatch.setattr(
        search_tool,
        "_create_client",
        mock_client_factory(lambda request: httpx.Response(200, json=payload, request=request)),
    )

    result = await search_tool.execute("Python")

    assert "搜索服务返回" in result
