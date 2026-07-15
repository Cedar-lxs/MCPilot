"""MCP Tool: 获取URL内容"""
import re
import httpx
import html2text
from bs4 import BeautifulSoup
from src.utils.logger_handler import logger
from ipaddress import ip_address
from urllib.parse import urlparse


class UrlFetchTool:
    """获取URL内容，Agent 经常需要打开链接读具体内容"""

    def get_definition(self) -> dict:
        return {
            "name": "url_fetch",
            "description": "获取URL内容，Agent 经常需要打开链接读具体内容",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string", 
                        "format": "uri",
                        "description": "要获取公开HTTP/HTTPS网页URL的内容，不支持本地文件或私有网络(SSRF风险)"
                    },
                    "max_length": {
                        "type": "integer",
                        "description": "返回内容最大字符数，超出截断。网页通常很长，限制长度避免爆 token",
                        "default": 10000,
                        "minimum": 1,
                        "maximum": 20000,
                    },
                    "output_format": { 
                        "type": "string",
                        "enum": ["text", "markdown"],
                        "description": "输出格式。text 纯文本干净；markdown 保留链接、标题结构，适合后续引用",
                        "default": "markdown",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "请求超时时间，秒。默认 15 秒",
                        "default": 15,
                        "minimum": 5,
                        "maximum": 60,
                    },
                },
                "required": ["url"],
            },
        }

    
    async def execute(self, url: str, max_length: int = 10000, output_format: str = "markdown", timeout: int = 15) -> str:
        """获取网页URL的内容 """
        logger.info(f"获取指定网页url的内容: url={url}, max_length={max_length}, output_format={output_format}, timeout={timeout}")

        # 确认文本输出格式是否支持
        if output_format not in {"text", "markdown"}:
            logger.error(f"不支持的输出格式: {output_format}，只支持 text 和 markdown")
            return "不支持的输出格式"

        # 确认请求超时时间是否合理
        if timeout < 5 or timeout > 60:
            logger.error(f"请求超时时间不合理: {timeout}，范围 5-60 秒")
            return "请求超时时间不合理"

        # 确认最大长度是否合理
        if max_length < 1 or max_length > 20000:
            logger.error(f"最大长度不合理: {max_length}，范围 1-20000")
            return "最大长度不合理"

        # 确认URL是否合法
        validation_error = self._validate_public_url(url)
        if validation_error:
            logger.error(f"URL被拒绝：{url}, 原因：{validation_error}" )
            return validation_error


        # 使用异步HTTP客户端请求URL
        try:
            async with self._create_client(timeout) as client:
                response = await client.get(url)

                validation_error = self._validate_public_url(str(response.url))
                if validation_error:
                    logger.error(f"重定向目标被拒绝：{response.url}, 原因：{validation_error}" )
                    return f"重定向目标不允许访问: {validation_error}"


                # 手动判断状态码，Agent 能看懂
                if response.status_code == 404:
                    logger.error(f"页面不存在 (404): {url}")
                    return f"页面不存在 (404): {url}"
                if response.status_code == 403:
                    logger.error(f"访问被拒绝 (403): {url}")
                    return f"访问被拒绝 (403): {url}"
                if response.status_code >= 500:
                    logger.error(f"服务器错误 ({response.status_code}): {url}")
                    return f"服务器错误 ({response.status_code}): {url}"
                if not 200 <= response.status_code < 300:
                    logger.error(f"请求失败 ({response.status_code}): {url}")
                    return f"请求失败 ({response.status_code}): {url}"
                content = response.text
        except httpx.RequestError as e:
            logger.error(f"请求URL失败: {url}，错误: {e}")
            return f"请求URL失败: {url}，错误: {e}"
        except Exception as e:
            logger.error(f"请求URL失败: {url}，错误: {e}")
            return f"请求URL失败: {url}，错误: {e}"

        # 判断网页内容是否为HTML内容
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type:
            logger.error(f"暂不支持解析该内容类型: {content_type or '未知'}")
            return f"暂不支持解析该内容类型: {content_type or '未知'}"

        # 解析HTML内容
        soup = BeautifulSoup(content, "html.parser")
        # 清除网页噪声内容
        for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside"]):
            tag.decompose()
        # 提取标题，用于后续引用
        title = soup.title.get_text(strip=True) if soup.title else "无标题"
        logger.info(f"网页标题: {title}")

        # 提取主要内容，根据输出格式处理
        if output_format == "text":
            text = soup.get_text("\n", strip=True)
            text = re.sub(r"\n{3,}", "\n\n", text)
            content = text
        elif output_format == "markdown":
            converter = html2text.HTML2Text()
            converter.ignore_links = False
            converter.body_width = 0
            content = converter.handle(str(soup))

        # 截断统一处理
        was_truncated = len(content) > max_length
        if was_truncated:
            content = content[:max_length].rstrip()
            content += f"\n\n[内容已截断，最多返回 {max_length} 个字符]"

        return f"来源: {response.url}\n标题: {title}\n\n{content}"




    def _validate_public_url(self, url: str) -> str | None:
        """验证URL是否为公开可访问的URL"""
        parsed = urlparse(url)

        if parsed.scheme not in {"http", "https"}:
            logger.error("URL 必须以 http:// 或 https:// 开头")
            return "URL 必须以 http:// 或 https:// 开头"

        hostname = parsed.hostname
        if not hostname:
            logger.error("URL 必须包含主机名")
            return "URL 必须包含主机名"

        if hostname == "localhost" or hostname.endswith(".localhost"):
            logger.error("本地主机名不支持公开访问")
            return "本地主机名不支持公开访问"

        try:
            address = ip_address(hostname)
        except ValueError:
            return None

        if(
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_unspecified
        ):
            logger.error("私有IP地址不支持公开访问")
            return "私有IP地址不支持公开访问"

        return None


    def _create_client(self, timeout: int) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0"},
        )