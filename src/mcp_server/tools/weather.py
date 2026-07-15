"""MCP Tool: Open-Meteo 天气查询"""

import httpx

from src.utils.logger_handler import logger


class WeatherTool:
    """通过 Open-Meteo 查询城市当前天气和短期预报。"""

    GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
    FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
    WEATHER_CODES = {
        0: "晴朗",
        1: "大部晴朗",
        2: "局部多云",
        3: "阴天",
        45: "雾",
        48: "雾凇",
        51: "毛毛雨",
        53: "中等毛毛雨",
        55: "强毛毛雨",
        56: "冻毛毛雨",
        57: "强冻毛毛雨",
        61: "小雨",
        63: "中雨",
        65: "大雨",
        66: "冻雨",
        67: "强冻雨",
        71: "小雪",
        73: "中雪",
        75: "大雪",
        77: "雪粒",
        80: "阵雨",
        81: "强阵雨",
        82: "暴雨",
        85: "阵雪",
        86: "强阵雪",
        95: "雷暴",
        96: "伴有冰雹的雷暴",
        99: "强冰雹雷暴",
    }

    def get_definition(self) -> dict:
        return {
            "name": "weather_query",
            "description": "查询指定城市或地区的真实当前天气和短期预报，无需 API Key",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "城市或地区名称，如 北京、上海、London",
                    },
                    "forecast_days": {
                        "type": "integer",
                        "description": "预报天数，包含当天，范围 1 至 7 天",
                        "default": 1,
                        "minimum": 1,
                        "maximum": 7,
                    },
                    "temperature_unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "温度单位，celsius=摄氏度，fahrenheit=华氏度",
                        "default": "celsius",
                    },
                },
                "required": ["location"],
            },
        }

    async def execute(
        self,
        location: str,
        forecast_days: int = 1,
        temperature_unit: str = "celsius",
    ) -> str:
        """查询地点的当前天气和每日预报。"""
        if not location or not location.strip():
            logger.error("location不能为空")
            return "location 不能为空"
        if not isinstance(forecast_days, int) or isinstance(forecast_days, bool) or not 1 <= forecast_days <= 7:
            logger.error("forecast_days 必须是 1 到 7 之间的整数")
            return "forecast_days 必须是 1 到 7 之间的整数"
        if temperature_unit not in {"celsius", "fahrenheit"}:
            logger.error("不支持的温度单位，可选: celsius, fahrenheit")
            return "不支持的温度单位，可选: celsius, fahrenheit"

        location = location.strip()
        logger.info(
            "查询天气: location=%s, forecast_days=%s, temperature_unit=%s",
            location,
            forecast_days,
            temperature_unit,
        )

        try:
            async with self._create_client() as client:
                geocoding_response = await client.get(
                    self.GEOCODING_URL,
                    params={"name": location, "count": 1, "language": "zh", "format": "json"},
                )
                geocoding_response.raise_for_status()
                matches = geocoding_response.json().get("results", [])
                if not matches:
                    return f"未找到地点「{location}」，请尝试提供更具体的城市或地区名称"

                place = matches[0]
                forecast_response = await client.get(
                    self.FORECAST_URL,
                    params={
                        "latitude": place["latitude"],
                        "longitude": place["longitude"],
                        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code",
                        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                        "forecast_days": forecast_days,
                        "temperature_unit": temperature_unit,
                        "wind_speed_unit": "kmh",
                        "timezone": "auto",
                    },
                )
                forecast_response.raise_for_status()
                forecast = forecast_response.json()
        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code
            logger.error("Open-Meteo 请求失败: HTTP %s", status_code)
            return f"天气服务暂时不可用（HTTP {status_code}）"
        except httpx.RequestError as error:
            logger.error("Open-Meteo 网络请求失败: %s", error)
            return "天气服务请求失败，请稍后重试"
        except (KeyError, TypeError, ValueError) as error:
            logger.error("Open-Meteo 返回数据格式异常: %s", error)
            return "天气服务返回的数据格式异常，请稍后重试"

        return self._format_weather(place, forecast, forecast_days, temperature_unit)

    def _create_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=15.0, follow_redirects=True)

    def _format_weather(
        self,
        place: dict,
        forecast: dict,
        forecast_days: int,
        temperature_unit: str,
    ) -> str:
        current = forecast.get("current")
        daily = forecast.get("daily")
        if not current or not daily:
            return "天气服务未返回完整天气数据，请稍后重试"

        temperature_symbol = "°C" if temperature_unit == "celsius" else "°F"
        place_name = place.get("name", "未知地点")
        admin_area = place.get("admin1")
        country = place.get("country")
        place_parts = [part for part in (place_name, admin_area, country) if part]
        display_place = "，".join(place_parts)

        weather_code = current.get("weather_code")
        current_weather = self.WEATHER_CODES.get(weather_code, f"未知天气（代码 {weather_code}）")
        lines = [
            f"地点: {display_place}",
            f"当地观测时间: {current.get('time', '未知')}",
            f"当前天气: {current_weather}",
            f"当前温度: {current.get('temperature_2m', '未知')}{temperature_symbol}，体感: {current.get('apparent_temperature', '未知')}{temperature_symbol}",
            f"相对湿度: {current.get('relative_humidity_2m', '未知')}%，风速: {current.get('wind_speed_10m', '未知')} km/h",
            "预报:",
        ]

        dates = daily.get("time", [])
        codes = daily.get("weather_code", [])
        maximums = daily.get("temperature_2m_max", [])
        minimums = daily.get("temperature_2m_min", [])
        precipitation_probabilities = daily.get("precipitation_probability_max", [])

        for index in range(forecast_days):
            try:
                lines.append(
                    f"- {dates[index]}: {self.WEATHER_CODES.get(codes[index], f'未知天气（代码 {codes[index]}）')}，"
                    f"{minimums[index]}~{maximums[index]}{temperature_symbol}，"
                    f"降水概率 {precipitation_probabilities[index]}%"
                )
            except (IndexError, TypeError):
                break

        return "\n".join(lines)
