from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx

from app.core.config import Settings
from app.schemas.travel import (
    AirQualityDay,
    ResearchData,
    ServiceStatus,
    TravelConditions,
    TravelPlace,
    TravelRoute,
    TravelSource,
    WeatherDay,
)

logger = logging.getLogger(__name__)
OFFICIAL_HOSTS = {
    "dpm.org.cn",
    "tiantanpark.com",
    "summerpalace-china.com",
    "badaling.cn",
    "mutianyugreatwall.com",
    "chnmuseum.cn",
    "bjparky.com",
    "en.namoc.org",
    "namoc.org",
    "s.shbwg.net",
    "shanghaimuseum.net",
    "chinasilk.cn",
    "12306.cn",
    "hilton.com",
    "marriott.com",
    "hyatt.com",
    "ihg.com",
    "huazhu.com",
    "atour.com",
}
OFFICIAL_PLACE_DOMAINS = {
    "故宫": "dpm.org.cn",
    "天坛": "tiantanpark.com",
    "颐和园": "summerpalace-china.com",
    "八达岭": "badaling.cn",
    "慕田峪": "mutianyugreatwall.com",
    "国家博物馆": "chnmuseum.cn",
}


def public_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    return (
        parsed.scheme == "https"
        and bool(host)
        and not parsed.username
        and not parsed.password
        and parsed.port in {None, 443}
        and host != "localhost"
        and not host.replace(".", "").isdigit()
        and not host.endswith((".local", ".internal"))
    )


def official_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host.endswith(".gov.cn") or any(
        host == known or host.endswith("." + known) for known in OFFICIAL_HOSTS
    )


def photo_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme == "http":
        value = parsed._replace(scheme="https").geturl()
    return value if public_url(value) else ""


def trip_dates(conditions: TravelConditions) -> list[date | None]:
    if conditions.departure_date and conditions.return_date:
        return [
            conditions.departure_date + timedelta(days=i)
            for i in range((conditions.return_date - conditions.departure_date).days + 1)
        ]
    return [None] * conditions.draft_days


def number(value) -> Decimal | None:
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result >= 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def coordinates(location: str) -> tuple[float, float] | None:
    try:
        lon, lat = map(float, location.split(","))
        if math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90:
            return lon, lat
    except (ValueError, TypeError, AttributeError):
        pass
    return None


def provider_time(value) -> datetime | None:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo else None
    except (ValueError, TypeError):
        return None


def normalize_air_quality(payload, dates, source_id, *, timezone="Asia/Shanghai", current=False):
    now = datetime.now(UTC)
    zone = ZoneInfo(timezone)
    entries = [payload] if current else payload.get("days", [])
    by_date = {}
    for entry in entries:
        start = provider_time(entry.get("forecastStartTime"))
        end = provider_time(entry.get("forecastEndTime"))
        day = (
            now.astimezone(zone).date()
            if current
            else start.astimezone(zone).date()
            if start
            else None
        )
        indexes = entry.get("indexes") or []
        index = next((item for item in indexes if item.get("code") == "cn-mee"), None)
        index = index or next((item for item in indexes if item.get("code") != "qaqi"), None)
        index = index or next(iter(indexes), {})
        aqi = number(index.get("aqi"))
        if day is None or aqi is None:
            continue
        advice = (index.get("health") or {}).get("advice") or {}
        by_date[day] = AirQualityDay(
            date=day,
            status="ready",
            kind="current" if current else "forecast",
            aqi=aqi,
            aqi_display=str(index.get("aqiDisplay", aqi)),
            standard=str(index.get("name") or index.get("code") or "未提供标准"),
            category=str(index.get("category") or "等级待查询"),
            health_advice="；".join(
                str(advice.get(key) or "") for key in ("generalPopulation", "sensitivePopulation")
            ).strip("；"),
            source_id=source_id,
            retrieved_at=now,
            valid_from=start,
            valid_until=end,
            note="查询时实况，仅供当前参考，不是未来预报"
            if current
            else "对应日期预报，出发前刷新",
        )
    if current:
        return list(by_date.values())
    return [by_date.get(day, AirQualityDay(date=day)) for day in dates]


def normalize_weather(payload: dict, dates: list[date | None], source_id: str) -> list[WeatherDay]:
    raw = payload.get("days") or payload.get("daily") or []
    by_date = {}
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            day = date.fromisoformat(
                str(item.get("fxDate") or item.get("date") or item.get("datetime"))[:10]
            )
        except ValueError:
            continue
        by_date[day] = item
    result = []
    for day in dates:
        item = by_date.get(day)
        if item is None:
            result.append(WeatherDay(date=day, note="暂未发布或未取得对应日期天气预报，出发前刷新"))
            continue
        result.append(
            WeatherDay(
                date=day,
                status="ready",
                source_id=source_id,
                note="预报可能变化，出发前请刷新",
                issued_at=provider_time(payload.get("updateTime")),
                valid_until=provider_time(payload.get("fxLinkExpiry")),
                condition=str(
                    item.get("textDay") or item.get("conditions") or item.get("condition") or ""
                ),
                temp_min=str(item.get("tempMin", item.get("tempmin", ""))),
                temp_max=str(item.get("tempMax", item.get("tempmax", ""))),
                precipitation=str(item.get("precip", "")),
                wind=" ".join(
                    str(item.get(key) or "")
                    for key in ("windDirDay", "windScaleDay", "windSpeedDay")
                ).strip(),
            )
        )
    return result


class TravelProviders:
    def __init__(self, client: httpx.AsyncClient, settings: Settings, data: ResearchData):
        self.client = client
        self.settings = settings
        self.data = data
        self._semaphore = asyncio.Semaphore(4)
        self._counts: dict[str, list[ServiceStatus]] = {}

    def configured(self, service: str) -> bool:
        if service == "qweather":
            return bool(self.settings.qweather_api_host and self.settings.qweather_api_key)
        return bool(getattr(self.settings, f"{service}_api_key", ""))

    def source(
        self, service: str, title: str, url: str, text: str, *, official=False
    ) -> TravelSource:
        source = TravelSource(
            id=f"R{len(self.data.sources) + 1}",
            service=service,
            title=title,
            url=url,
            retrieved_at=datetime.now(UTC),
            text=text[:12_000],
            trust="official"
            if official
            else "provider"
            if service != "firecrawl"
            else "unverified",
        )
        self.data.sources.append(source)
        return source

    async def call(self, service: str, url: str, *, params=None, body=None) -> dict | None:
        started = time.monotonic()
        status = "failed"
        code = "unavailable"
        result = None
        if not self.configured(service):
            status, code = "not_configured", "not_configured"
        else:
            headers = {}
            params = dict(params or {})
            if service == "amap":
                params["key"] = self.settings.amap_api_key
            elif service == "qweather":
                headers["X-QW-Api-Key"] = self.settings.qweather_api_key
            else:
                headers["Authorization"] = f"Bearer {self.settings.firecrawl_api_key}"
            for attempt in range(min(max(self.settings.travel_service_retries, 0), 2) + 1):
                try:
                    async with self._semaphore:
                        async with asyncio.timeout(self.settings.travel_service_timeout_seconds):
                            response = await self.client.request(
                                "POST" if body is not None else "GET",
                                url,
                                params=params or None,
                                json=body,
                                headers=headers,
                                timeout=self.settings.travel_service_timeout_seconds,
                            )
                            response.raise_for_status()
                            result = response.json()
                    if not isinstance(result, dict):
                        code = "invalid_response"
                        result = None
                        break
                    if service == "amap" and str(result.get("status")) != "1":
                        code = "provider_" + str(result.get("infocode", "rejected"))[:20]
                        result = None
                        break
                    if service == "qweather" and str(result.get("code", "200")) != "200":
                        code = "provider_" + str(result.get("code"))[:20]
                        result = None
                        break
                    if service == "firecrawl" and not result.get("success", False):
                        code, result = "provider_rejected", None
                        break
                    status, code = "ready", None
                    break
                except (httpx.TimeoutException, TimeoutError):
                    code = "timeout"
                except httpx.HTTPStatusError as error:
                    code = f"http_{error.response.status_code}"
                    if error.response.status_code < 500 and error.response.status_code != 429:
                        break
                except (httpx.HTTPError, ValueError):
                    code = "invalid_response"
                if attempt < self.settings.travel_service_retries:
                    await asyncio.sleep(0.25 * (attempt + 1))
        elapsed = int((time.monotonic() - started) * 1000)
        self._counts.setdefault(service, []).append(
            ServiceStatus(
                service=service,
                status=status,
                count=1 if result is not None else 0,
                error_code=code,
                duration_ms=elapsed,
            )
        )
        logger.info(
            "travel service=%s stage=query duration_ms=%s count=%s error_code=%s",
            service,
            elapsed,
            int(result is not None),
            code,
        )
        return result

    def statuses(self) -> list[ServiceStatus]:
        results = []
        for service in ("qweather", "amap", "firecrawl"):
            calls = self._counts.get(service, [])
            ready = sum(call.count for call in calls)
            failed = [call for call in calls if call.status != "ready"]
            results.append(
                ServiceStatus(
                    service=service,
                    status=(
                        "not_configured"
                        if not self.configured(service)
                        else "partial"
                        if ready and failed
                        else "ready"
                        if ready
                        else "failed"
                        if calls
                        else "pending"
                    ),
                    count=ready,
                    duration_ms=sum(call.duration_ms for call in calls),
                    error_code=failed[0].error_code if failed else None,
                )
            )
        return results

    def weather_base(self) -> str | None:
        raw = self.settings.qweather_api_host.strip().rstrip("/")
        parsed = urlparse(raw if "://" in raw else "https://" + raw)
        host = parsed.hostname or ""
        if parsed.scheme != "https" or not host.endswith((".qweatherapi.com", ".qweather.com")):
            return None
        if parsed.username or parsed.password or parsed.port not in {None, 443}:
            return None
        return f"https://{host}"

    async def weather(self, conditions: TravelConditions, location: str | None):
        dates = trip_dates(conditions)
        self.data.weather = [WeatherDay(date=day) for day in dates]
        self.data.air_quality = [AirQualityDay(date=day) for day in dates]
        base = self.weather_base()
        if not base:
            self._counts.setdefault("qweather", []).append(
                ServiceStatus(service="qweather", status="failed", error_code="invalid_host")
            )
            return
        geo = await self.call(
            "qweather",
            f"{base}/geo/v2/city/lookup",
            params={"location": conditions.destination},
        )
        matches = (geo or {}).get("location") or []
        city = matches[0] if matches else {}
        location = city.get("id") or location
        if not location:
            return
        payload = await self.call(
            "qweather", f"{base}/v7/weather/10d", params={"location": location}
        )
        if payload is not None:
            source = self.source(
                "qweather",
                "和风天气每日预报",
                "https://www.qweather.com/",
                "10 天预报；按出行日期筛选",
            )
            self.data.weather = normalize_weather(payload, dates, source.id)
            source.text = "\n".join(day.model_dump_json() for day in self.data.weather)
        point = coordinates(f"{city.get('lon')},{city.get('lat')}")
        if not point:
            return
        lon, lat = point
        timezone = city.get("tz") or "Asia/Shanghai"
        for kind in ("daily", "current"):
            air = await self.call(
                "qweather",
                f"{base}/airquality/v1/{kind}/{lat:.2f}/{lon:.2f}",
                params={"lang": "zh"},
            )
            if air is None:
                continue
            source = self.source(
                "qweather",
                f"和风空气质量{'每日预报' if kind == 'daily' else '实况'}",
                "https://dev.qweather.com/docs/api/air-quality/air-"
                + ("daily-forecast/" if kind == "daily" else "current/"),
                str(air),
            )
            values = normalize_air_quality(
                air, dates, source.id, timezone=timezone, current=kind == "current"
            )
            if kind == "daily":
                self.data.air_quality = values
            elif values:
                self.data.current_air_quality = values[0]

    async def geocode(self, city: str) -> str | None:
        data = await self.call(
            "amap", "https://restapi.amap.com/v3/geocode/geo", params={"address": city}
        )
        geocodes = (data or {}).get("geocodes") or []
        return geocodes[0].get("location") if geocodes else None

    async def places(
        self, city: str, keywords: str, *, hotel=False, limit=5, near: TravelPlace | None = None
    ) -> list[TravelPlace]:
        params = {
            "city": city,
            "citylimit": "true",
            "keywords": keywords,
            "offset": max(5, limit),
            "extensions": "all",
        }
        if hotel or keywords == "景点":
            params["types"] = "100000" if hotel else "110000"
        if near:
            params = {
                "location": near.location,
                "radius": 3000,
                "types": "050000",
                "offset": limit,
                "extensions": "all",
                "sortrule": "distance",
            }
        payload = await self.call(
            "amap",
            "https://restapi.amap.com/v3/place/around"
            if near
            else "https://restapi.amap.com/v3/place/text",
            params=params,
        )
        result = []
        pois = (payload or {}).get("pois") or []
        if not hotel and keywords != "景点":
            pois = sorted(pois, key=lambda poi: keywords not in str(poi.get("name", "")))
        for poi in pois:
            if not coordinates(poi.get("location")):
                continue
            if (
                not hotel
                and not near
                and keywords != "景点"
                and keywords not in str(poi.get("name", ""))
            ):
                continue
            source = self.source(
                "amap",
                str(poi.get("name", keywords)),
                "https://www.amap.com/",
                "\n".join(
                    f"{key}: {poi.get(key) or ''}"
                    for key in ("name", "address", "location", "adname", "business_area")
                ),
            )
            result.append(
                TravelPlace(
                    id=poi["id"],
                    name=poi["name"],
                    location=poi["location"],
                    address=poi.get("address") if isinstance(poi.get("address"), str) else "",
                    area=poi.get("adname") or "",
                    source_id=source.id,
                    near_place_id=near.id if near else None,
                    business_hours=str((poi.get("business") or {}).get("opentime_week") or "")
                    if isinstance(poi.get("business"), dict)
                    else "",
                    photos=[
                        {
                            "url": photo_url(photo["url"]),
                            "title": str(photo.get("title") or ""),
                            "status": "待人工核对",
                            "source_id": source.id,
                        }
                        for photo in poi.get("photos") or []
                        if photo_url(photo.get("url", ""))
                    ][:4],
                )
            )
            if len(result) >= limit:
                break
        return result

    async def search(self, query: str, *, official=False):
        official_domain = next(
            (domain for place, domain in OFFICIAL_PLACE_DOMAINS.items() if place in query), None
        )
        if official_domain and (official or "官网" in query):
            subject = next(place for place in OFFICIAL_PLACE_DOMAINS if place in query)
            query = f"site:{official_domain} {subject} 门票 开放 预约 身份证 入园 限流"
        payload = await self.call(
            "firecrawl",
            "https://api.firecrawl.dev/v2/search",
            body={
                "query": query,
                "limit": 3,
                "lang": "zh",
                "scrapeOptions": {"formats": ["markdown"]},
                **({"tbs": "qdr:m6"} if not official and "官网" not in query else {}),
            },
        )
        raw = (payload or {}).get("data") or {}
        results = raw.get("web", []) if isinstance(raw, dict) else raw
        for item in results if isinstance(results, list) else []:
            url = item.get("url") or (item.get("metadata") or {}).get("sourceURL") or ""
            if not public_url(url) or any(source.url == url for source in self.data.sources):
                continue
            text = item.get("markdown") or ""
            if not text:
                scraped = await self.call(
                    "firecrawl",
                    "https://api.firecrawl.dev/v2/scrape",
                    body={
                        "url": url,
                        "formats": ["markdown"],
                        "onlyMainContent": True,
                    },
                )
                text = ((scraped or {}).get("data") or {}).get("markdown") or ""
            if text:
                self.source(
                    "firecrawl",
                    str(item.get("title") or query),
                    url,
                    text,
                    official=official_url(url),
                )

    async def route(
        self, origin: TravelPlace, destination: TravelPlace, conditions: TravelConditions
    ) -> TravelRoute:
        mode = (
            "driving"
            if conditions.transport == "driving"
            else "walking"
            if conditions.transport == "walking"
            else "public"
        )
        endpoint = "transit/integrated" if mode == "public" else mode
        params = {
            "origin": origin.location,
            "destination": destination.location,
            "extensions": "all",
        }
        if mode == "public":
            params.update(city=conditions.destination)
        payload = await self.call(
            "amap", f"https://restapi.amap.com/v3/direction/{endpoint}", params=params
        )
        route = (payload or {}).get("route") or {}
        paths = route.get("transits" if mode == "public" else "paths") or []
        result = TravelRoute(origin_id=origin.id, destination_id=destination.id, mode=mode)
        if not paths:
            return result
        path = paths[0]
        distance, duration = number(path.get("distance")), number(path.get("duration"))
        if distance is None or duration is None:
            return result
        source = self.source(
            "amap", f"{origin.name} → {destination.name}", "https://www.amap.com/", str(path)[:6000]
        )
        cost = (
            number(path.get("cost"))
            if mode == "public"
            else number(path.get("tolls"))
            if mode == "driving"
            else Decimal("0")
        )
        instructions = []
        for segment in path.get("segments") or []:
            for bus in (segment.get("bus") or {}).get("buslines") or []:
                instructions.append(
                    f"{bus.get('name', '线路待查询')}："
                    f"{(bus.get('departure_stop') or {}).get('name', '')} → "
                    f"{(bus.get('arrival_stop') or {}).get('name', '')}"
                )
            railway = segment.get("railway") or {}
            if railway.get("name"):
                instructions.append(str(railway["name"]))
        return result.model_copy(
            update={
                "status": "ready",
                "distance_m": int(distance),
                "duration_minutes": max(1, (int(duration) + 59) // 60),
                "cost": cost,
                "cost_kind": "supplier_quote" if cost is not None else "pending",
                "source_id": source.id,
                "cost_scope": "公共交通方案参考费用，出行当日可能变化"
                if mode == "public"
                else "仅道路通行费，不含燃油、停车、租车"
                if mode == "driving"
                else "步行无需票价",
                "instructions": instructions,
            }
        )
