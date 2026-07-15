import httpx
import pytest
from src.mcp_server.tools.url_fetch import UrlFetchTool




@pytest.fixture
def url_fetch_tool():
    return UrlFetchTool()

def mock_client_factory(handler):
    transport = httpx.MockTransport(handler)


    def create_client(timeout: int) -> httpx.AsyncClient:
        """MockTransport 不会访问互联网；所有请求都会由 handler 函数返回预设响应。"""
        return httpx.AsyncClient(
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
        )

    return create_client



@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/file.txt",
        "not-a-url",
    ],
)
async def test_rejects_non_http_urls(url_fetch_tool: UrlFetchTool, url: str):
    """先测不依赖 HTTP 的参数与 SSRF 校验"""
    result = await url_fetch_tool.execute(url)
    assert "URL 必须以 http:// 或 https://" in result
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000",
        "http://api.localhost",
        "http://127.0.0.1",
        "http://10.0.0.1",
        "http://192.168.1.1",
        "http://169.254.169.254",
    ],
)


async def test_rejects_local_or_private_addresses(
    url_fetch_tool: UrlFetchTool, url: str
):
    result = await url_fetch_tool.execute(url)
    assert "不支持公开访问" in result




@pytest.mark.asyncio
async def test_rejects_invalid_output_format(url_fetch_tool: UrlFetchTool):
    """参数边界"""
    result = await url_fetch_tool.execute(
        "https://example.com",
        output_format="json",
    )
    assert "不支持的输出格式" in result



@pytest.mark.asyncio
async def test_rejects_invalid_max_length(url_fetch_tool: UrlFetchTool):
    result = await url_fetch_tool.execute(
        "https://example.com",
        max_length=0,
    )
    assert "最大长度不合理" in result



@pytest.mark.asyncio
async def test_extracts_text_from_html(
    url_fetch_tool: UrlFetchTool, monkeypatch: pytest.MonkeyPatch
):
    """测试成功提取 HTML 文本"""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="""
                <html>
                    <head><title>测试标题</title></head>
                    <body>
                        <nav>不应保留的导航</nav>
                        <main><h1>正文标题</h1><p>正文内容</p></main>
                        <script>console.log("不应保留")</script>
                    </body>
                </html>
            """,
            request=request,
        )

    monkeypatch.setattr(
        url_fetch_tool,
        "_create_client",
        mock_client_factory(handler),
    )

    result = await url_fetch_tool.execute(
        "https://example.com/article",
        output_format="text",
    )

    assert "来源: https://example.com/article" in result
    assert "标题: 测试标题" in result
    assert "正文标题" in result
    assert "正文内容" in result
    assert "不应保留的导航" not in result
    assert 'console.log' not in result