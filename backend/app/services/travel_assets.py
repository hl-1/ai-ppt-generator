from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
from io import BytesIO
from urllib.parse import urljoin, urlparse

import httpx
from markdown_it import MarkdownIt
from PIL import Image

from app.images.validate import ImageRejected, validate_image
from app.schemas.travel import ResearchIssue, TravelImage, TravelMap
from app.services.media import media_url, store_image
from app.services.travel_providers import coordinates, public_url


async def download_public_image(client, url, *, timeout, max_bytes):
    for _ in range(4):
        if not public_url(url):
            raise ValueError("invalid_image_url")
        host = urlparse(url).hostname
        addresses = await asyncio.to_thread(socket.getaddrinfo, host, 443)
        if not addresses or any(
            not ipaddress.ip_address(item[4][0]).is_global for item in addresses
        ):
            raise ValueError("private_image_host")
        async with client.stream("GET", url, timeout=timeout, follow_redirects=False) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers.get("location", ""))
                continue
            response.raise_for_status()
            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise ValueError("image_too_large")
            data = bytes(content)
            validate_image(data)
            with Image.open(BytesIO(data)) as image:
                image.verify()
            with Image.open(BytesIO(data)) as image:
                if image.format == "WEBP":
                    converted = BytesIO()
                    image.convert("RGB").save(converted, format="PNG")
                    data = converted.getvalue()
            return data
    raise ValueError("image_redirect_limit")


def source_photos(data, place):
    candidates = list(place.photos)
    parser = MarkdownIt()
    for source in data.sources:
        if source.service != "firecrawl" or source.trust != "official":
            continue
        for token in parser.parse(source.text):
            for child in token.children or []:
                if (
                    child.type != "image"
                    or not child.content
                    or not (place.name in child.content or child.content in place.name)
                ):
                    continue
                url = urljoin(source.url, child.attrGet("src") or "")
                if public_url(url):
                    candidates.append({"url": url, "source_id": source.id, "title": child.content})
    return candidates


async def collect_travel_assets(providers, plan, *, user_id, project_id):
    data, settings = providers.data, providers.settings
    visited_ids = list(dict.fromkeys(stop.place_id for day in plan.days for stop in day.stops))
    places = {place.id: place for place in data.places}

    async def photo(place):
        for candidate in source_photos(data, place)[:4]:
            try:
                content = await download_public_image(
                    providers.client,
                    candidate["url"],
                    timeout=settings.travel_service_timeout_seconds,
                    max_bytes=settings.max_image_bytes,
                )
                extension, _ = validate_image(content)
                key = store_image(
                    user_id=user_id, project_id=project_id, data=content, extension=extension
                )
                data.images.append(
                    TravelImage(
                        place_id=place.id,
                        place_name=place.name,
                        url=media_url(key),
                        original_url=candidate["url"],
                        source_id=candidate["source_id"],
                        credit=f"{place.name} · "
                        + ("官方资料" if candidate not in place.photos else "高德 POI 图片"),
                    )
                )
                return
            except (httpx.HTTPError, ValueError, OSError, ImageRejected):
                continue
        data.issues.append(
            ResearchIssue(
                stage="景点图片",
                code="photo_unavailable",
                message=f"{place.name}未取得可显示的对应实景照片",
                action="补充官方图片或上传已核实的照片。",
            )
        )

    await asyncio.gather(*(photo(places[item]) for item in visited_ids if item in places))
    points = [
        places[item]
        for item in visited_ids
        if item in places and coordinates(places[item].location)
    ]
    missing = [
        places[item].name
        for item in visited_ids
        if item in places and not coordinates(places[item].location)
    ]
    if missing:
        data.issues.append(
            ResearchIssue(
                stage="路线图",
                code="map_coordinates_missing",
                message="未取得可靠坐标：" + "、".join(missing),
                action="补充可核实的地图位置后重新查询。",
            )
        )
    if not points or not providers.configured("amap"):
        return
    # The static map connects sourced POIs in visit order; it is not a navigation polyline.
    params = {
        "key": settings.amap_api_key,
        "size": "900*600",
        "markers": "|".join(
            f"mid,0xC94444,{index}:{place.location}" for index, place in enumerate(points, 1)
        ),
    }
    if len(points) > 1:
        params["paths"] = "4,0x27806F,1,,:" + ";".join(place.location for place in points)
    try:
        async with providers.client.stream(
            "GET",
            "https://restapi.amap.com/v3/staticmap",
            params=params,
            timeout=settings.travel_service_timeout_seconds,
        ) as response:
            response.raise_for_status()
            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > settings.max_image_bytes:
                    raise ValueError("map_too_large")
        extension, _ = validate_image(bytes(content))
        key = store_image(
            user_id=user_id, project_id=project_id, data=bytes(content), extension=extension
        )
        source = providers.source(
            "amap",
            "高德行程静态地图",
            "https://lbs.amap.com/api/webservice/guide/api/staticmaps",
            json.dumps(
                [
                    {"name": place.name, "location": place.location, "source_id": place.source_id}
                    for place in points
                ],
                ensure_ascii=False,
            ),
        )
        data.route_map = TravelMap(
            url=media_url(key),
            source_id=source.id,
            place_ids=[place.id for place in points],
            status="ready" if len(points) == len(visited_ids) else "partial",
            note="高德 GCJ-02 坐标；编号为游览顺序，连线仅示意顺序，不是导航路线"
            + ("；缺少坐标：" + "、".join(missing) if missing else ""),
        )
    except (httpx.HTTPError, ValueError, OSError, ImageRejected):
        data.issues.append(
            ResearchIssue(
                stage="路线图",
                code="map_unavailable",
                message="静态地图未能取得或校验失败",
                action="检查高德静态地图权限后刷新旅行资料。",
            )
        )
