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
from app.services.travel_providers import (
    coordinates,
    photo_url,
    place_in_text,
    place_search_name,
    public_url,
)


async def download_public_image(client, url, *, timeout, max_bytes, referer=None):
    for _ in range(4):
        if not public_url(url, allow_official_http=True):
            raise ValueError("invalid_image_url")
        parsed = urlparse(url)
        addresses = await asyncio.to_thread(
            socket.getaddrinfo, parsed.hostname, 80 if parsed.scheme == "http" else 443
        )
        if not addresses or any(
            not ipaddress.ip_address(item[4][0]).is_global for item in addresses
        ):
            raise ValueError("private_image_host")
        headers = {"Referer": referer} if referer else None
        async with client.stream(
            "GET", url, timeout=timeout, follow_redirects=False, headers=headers
        ) as response:
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
                width, height = image.size
                if width < 320 or height < 180 or not 0.4 <= width / height <= 3.2:
                    raise ValueError("photo_dimensions_unsuitable")
                if image.format == "WEBP":
                    converted = BytesIO()
                    image.convert("RGB").save(converted, format="PNG")
                    data = converted.getvalue()
            return data
    raise ValueError("image_redirect_limit")


def source_photos(data, place):
    official, web = [], []
    parser = MarkdownIt()
    for source in data.sources:
        if source.service != "firecrawl":
            continue
        for token in parser.parse(source.text):
            children = token.children or []
            link_caption = ""
            for index, child in enumerate(children):
                if child.type == "link_open":
                    caption = []
                    for following in children[index + 1 :]:
                        if following.type == "link_close":
                            break
                        caption.append(following.content)
                    link_caption = " ".join(caption)
                elif child.type == "link_close":
                    link_caption = ""
                if (
                    child.type != "image"
                    or not child.content
                    or not (
                        place_in_text(place.name, child.content)
                        or place_in_text(place.name, link_caption)
                    )
                    or any(
                        word in child.content.casefold()
                        for word in (
                            "二维码", "地图", "示意", "海报", "插画", "手绘", "效果图",
                            "头像", "门票", "旅游指南", "园区景点", "logo", "banner",
                            "渲染图", "合成图", "ai生成", "ai绘画", "纪念品", "文创",
                        )
                    )
                ):
                    continue
                url = photo_url(urljoin(source.url, child.attrGet("src") or ""))
                if url:
                    target = official if source.trust == "official" else web
                    target.append(
                        {
                            "url": url,
                            "source_id": source.id,
                            "title": child.content,
                            "referer": source.url,
                            "credit": "景区官网" if source.trust == "official" else source.title,
                        }
                    )
    candidates = [
        *official,
        *({**photo, "credit": "高德 POI 实景图片"} for photo in place.photos),
        *web,
    ]
    unique = {}
    for candidate in candidates:
        unique.setdefault(candidate["url"], candidate)
    return list(unique.values())


async def collect_travel_assets(providers, plan, *, user_id, project_id):
    data, settings = providers.data, providers.settings
    visited_ids = list(dict.fromkeys(stop.place_id for day in plan.days for stop in day.stops))
    places = {place.id: place for place in data.places}

    async def photo(place):
        async def use_photo(candidate):
            try:
                content = await download_public_image(
                    providers.client,
                    candidate["url"],
                    timeout=settings.travel_service_timeout_seconds,
                    max_bytes=settings.max_image_bytes,
                    referer=candidate.get("referer"),
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
                        credit=f"{place.name} · {candidate.get('credit', '实景图片')}",
                    )
                )
                return True
            except (httpx.HTTPError, ValueError, OSError, ImageRejected):
                return False

        tried = set()
        for candidate in source_photos(data, place)[:8]:
            tried.add(candidate["url"])
            if await use_photo(candidate):
                return
        if providers.configured("firecrawl"):
            await providers.search(
                f'{plan.conditions.destination} "{place_search_name(place.name)}" 实景 照片 游记',
                subject=place.name,
            )
            for candidate in [
                candidate for candidate in source_photos(data, place) if candidate["url"] not in tried
            ][:4]:
                if await use_photo(candidate):
                    return
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
