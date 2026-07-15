"""测试 Open-Meteo 天气查询工具"""

import httpx
import pytest

from src.mcp_server.tools.weather import WeatherTool


@pytest.fixture
def weather_tool():
    return WeatherTool()


def mock_client_factory(handler):
    transport = httpx.MockTransport(handler)

    def create_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, follow_redirects=True)

    return create_client


def test_definition(weather_tool: WeatherTool):
    definition = weather_tool.get_definition()
    properties = definition["inputSchema"]["properties"]
    assert definition["name"] == "weather_query"
    assert definition["inputSchema"]["required"] == ["location"]
    assert set(properties["temperature_unit"]["enum"]) == {"celsius", "fahrenheit"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"location": ""}, "location 不能为空"),
        ({"location": "北京", "forecast_days": 0}, "forecast_days 必须是 1 到 7 之间的整数"),
        ({"location": "北京", "forecast_days": 8}, "forecast_days 必须是 1 到 7 之间的整数"),
        ({"location": "北京", "forecast_days": True}, "forecast_days 必须是 1 到 7 之间的整数"),
        ({"location": "北京", "temperature_unit": "kelvin"}, "不支持的温度单位"),
    ],
)
async def test_rejects_invalid_arguments(weather_tool: WeatherTool, kwargs: dict, expected: str):
    result = await weather_tool.execute(**kwargs)
    assert expected in result


@pytest.mark.asyncio
async def test_returns_weather_for_location(weather_tool: WeatherTool, monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "geocoding-api.open-meteo.com":
            assert request.url.params["name"] == "北京"
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "name": "北京市",
                            "admin1": "北京市",
                            "country": "中国",
                            "latitude": 39.9042,
                            "longitude": 116.4074,
                        }
                    ]
                },
                request=request,
            )
        if request.url.host == "api.open-meteo.com":
            assert request.url.params["forecast_days"] == "2"
            assert request.url.params["timezone"] == "auto"
            return httpx.Response(
                200,
                json={
                    "current": {
                        "time": "2026-07-15T10:00",
                        "temperature_2m": 28.5,
                        "apparent_temperature": 31.2,
                        "relative_humidity_2m": 70,
                        "wind_speed_10m": 12.4,
                        "weather_code": 61,
                    },
                    "daily": {
                        "time": ["2026-07-15", "2026-07-16"],
                        "weather_code": [61, 0],
                        "temperature_2m_max": [30.0, 32.0],
                        "temperature_2m_min": [23.0, 24.0],
                        "precipitation_probability_max": [80, 10],
                    },
                },
                request=request,
            )
        raise AssertionError(f"未预期的请求: {request.url}")

    monkeypatch.setattr(weather_tool, "_create_client", mock_client_factory(handler))

    result = await weather_tool.execute("北京", forecast_days=2)

    assert "地点: 北京市，北京市，中国" in result
    assert "当前天气: 小雨" in result
    assert "当前温度: 28.5°C，体感: 31.2°C" in result
    assert "- 2026-07-15: 小雨，23.0~30.0°C，降水概率 80%" in result
    assert "- 2026-07-16: 晴朗，24.0~32.0°C，降水概率 10%" in result


@pytest.mark.asyncio
async def test_returns_not_found_when_geocoding_has_no_match(
    weather_tool: WeatherTool, monkeypatch: pytest.MonkeyPatch
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []}, request=request)

    monkeypatch.setattr(weather_tool, "_create_client", mock_client_factory(handler))

    result = await weather_tool.execute("不存在的地点")

    assert "未找到地点" in result


@pytest.mark.asyncio
async def test_returns_service_error_for_upstream_http_error(
    weather_tool: WeatherTool, monkeypatch: pytest.MonkeyPatch
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    monkeypatch.setattr(weather_tool, "_create_client", mock_client_factory(handler))

    result = await weather_tool.execute("北京")

    assert "天气服务暂时不可用（HTTP 503）" == result


@pytest.mark.asyncio
async def test_returns_incomplete_data_message(
    weather_tool: WeatherTool, monkeypatch: pytest.MonkeyPatch
):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "geocoding-api.open-meteo.com":
            return httpx.Response(
                200,
                json={"results": [{"name": "北京", "latitude": 39.9, "longitude": 116.4}]},
                request=request,
            )
        return httpx.Response(200, json={"current": {}}, request=request)

    monkeypatch.setattr(weather_tool, "_create_client", mock_client_factory(handler))

    result = await weather_tool.execute("北京")

    assert "未返回完整天气数据" in result
