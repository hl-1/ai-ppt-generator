from __future__ import annotations

import uuid
from datetime import date as Date
from datetime import datetime, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class TimeWindow(BaseModel):
    earliest: time | None = None
    latest: time | None = None

    @model_validator(mode="after")
    def ordered(self):
        if self.earliest and self.latest and self.earliest > self.latest:
            raise ValueError("可接受时段的结束时间须晚于开始时间")
        return self


class VideoPreferences(BaseModel):
    enabled: bool = True
    platforms: list[Literal["douyin", "bilibili"]] = Field(
        default_factory=lambda: ["douyin", "bilibili"], min_length=1, max_length=2
    )
    min_likes: int = Field(default=1_000, ge=1, le=100_000_000)
    min_favorites: int = Field(default=1_000, ge=1, le=100_000_000)
    lookback_days: int = Field(default=180, ge=1, le=1095)


class TravelConditions(BaseModel):
    origin: str = Field(default="", max_length=80)
    destination: str = Field(default="", max_length=80)
    departure_date: Date | None = None
    return_date: Date | None = None
    departure_window: TimeWindow = Field(default_factory=TimeWindow)
    return_window: TimeWindow = Field(default_factory=TimeWindow)
    adults: int = Field(default=1, ge=0, le=50)
    children: int = Field(default=0, ge=0, le=20)
    seniors: int = Field(default=0, ge=0, le=20)
    child_ages: list[int] = Field(default_factory=list, max_length=20)
    senior_ages: list[int] = Field(default_factory=list, max_length=20)
    budget: Decimal | None = Field(default=None, gt=0, le=10_000_000)
    budget_mode: Literal["total", "per_person"] = "total"
    transport: Literal["public", "driving", "walking", "train", "flight"] = "public"
    lodging_area: str = Field(default="", max_length=120)
    lodging_preferences: str = Field(default="", max_length=300)
    room_count: int | None = Field(default=None, ge=1, le=50)
    must_visit: list[str] = Field(default_factory=list, max_length=8)
    meal_budget_per_day: Decimal = Field(default=Decimal("100"), ge=1, le=10000)
    contingency: Decimal = Field(default=Decimal("300"), ge=0, le=1000000)
    interests: list[str] = Field(default_factory=list, max_length=12)
    pace: Literal["relaxed", "balanced", "intensive"] = "balanced"
    draft_days: int = Field(default=3, ge=1, le=14)
    confirmed: bool = False
    video_preferences: VideoPreferences = Field(default_factory=VideoPreferences)

    @model_validator(mode="after")
    def validate_trip(self):
        if self.departure_date and self.return_date:
            days = (self.return_date - self.departure_date).days
            if not 0 <= days <= 29:
                raise ValueError("返程日期须不早于出发日期，单次规划最多 30 天")
        if self.adults + self.children + self.seniors < 1:
            raise ValueError("请至少填写一位出行人员")
        if len(self.child_ages) > self.children or any(
            not 0 <= age <= 17 for age in self.child_ages
        ):
            raise ValueError("儿童年龄须为 0 至 17 岁，数量不能超过儿童人数")
        if len(self.senior_ages) > self.seniors or any(
            not 50 <= age <= 120 for age in self.senior_ages
        ):
            raise ValueError("老人年龄须为 50 至 120 岁，数量不能超过老人人数")
        self.origin = self.origin.strip()
        self.destination = self.destination.strip()
        self.interests = list(dict.fromkeys(s.strip()[:80] for s in self.interests if s.strip()))
        self.must_visit = list(dict.fromkeys(s.strip()[:80] for s in self.must_visit if s.strip()))
        return self


class TravelExtractRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)


class TravelExtractResult(BaseModel):
    conditions: TravelConditions
    missing_fields: list[str]
    warnings: list[str] = Field(default_factory=list)


class TravelSource(BaseModel):
    id: str
    service: Literal["qweather", "amap", "firecrawl", "video"]
    title: str
    url: str
    retrieved_at: datetime
    trust: Literal["official", "provider", "unverified"] = "unverified"
    text: str = ""


class TravelFact(BaseModel):
    id: str = ""
    place: str = Field(min_length=1, max_length=120)
    kind: Literal[
        "price",
        "hours",
        "entry_cutoff",
        "closure",
        "booking",
        "season",
        "internal_route",
        "checkin",
        "identity",
        "entry_process",
        "restriction",
        "pitfall",
        "restaurant",
        "lodging",
        "lodging_price",
        "transport",
    ]
    source_id: str
    quote: str = Field(min_length=1, max_length=800)
    summary: str = Field(default="", max_length=500)
    amount: Decimal | None = Field(default=None, ge=0)
    audience: str = ""
    room_type: str = ""
    price_unit: str = ""
    tax_note: str = ""
    opens: time | None = None
    closes: time | None = None
    last_entry: time | None = None
    closed_weekdays: list[int] = Field(default_factory=list, max_length=7)
    valid_from: Date | None = None
    valid_to: Date | None = None
    applicable_year: int | None = Field(default=None, ge=2000, le=2100)
    status: Literal["verified", "reference", "outdated", "unverified"] = "unverified"


class FactExtraction(BaseModel):
    facts: list[TravelFact] = Field(default_factory=list, max_length=50)

    @model_validator(mode="before")
    @classmethod
    def keep_valid_items(cls, value):
        if isinstance(value, list):
            value = {"facts": value}
        if not isinstance(value, dict) or not isinstance(value.get("facts"), list):
            return value
        facts = []
        for item in value["facts"][:50]:
            if not isinstance(item, dict):
                continue
            item = dict(item)
            for field in ("summary", "audience", "id"):
                if item.get(field) is None:
                    item[field] = ""
            item["status"] = "unverified"
            try:
                facts.append(TravelFact.model_validate(item))
            except ValidationError:
                continue
        return {"facts": facts}


class TravelPlace(BaseModel):
    id: str
    name: str
    location: str
    address: str = ""
    area: str = ""
    city: str = ""
    source_id: str
    photos: list[dict[str, str]] = Field(default_factory=list)
    near_place_id: str | None = None
    business_hours: str = ""


class TravelImage(BaseModel):
    place_id: str
    place_name: str
    url: str
    original_url: str
    source_id: str
    credit: str = ""
    status: Literal["ready", "failed"] = "ready"


class TravelMap(BaseModel):
    url: str | None = None
    source_id: str | None = None
    place_ids: list[str] = Field(default_factory=list)
    status: Literal["ready", "partial", "pending"] = "pending"
    note: str = "路线图待查询；缺少可靠坐标时不生成位置"


class TravelRoute(BaseModel):
    origin_id: str
    destination_id: str
    mode: str
    distance_m: int | None = None
    duration_minutes: int | None = None
    cost: Decimal | None = None
    cost_kind: Literal["supplier_quote", "estimate", "pending"] = "pending"
    cost_scope: str = ""
    source_id: str | None = None
    status: Literal["ready", "pending"] = "pending"
    instructions: list[str] = Field(default_factory=list)


class WeatherDay(BaseModel):
    date: Date | None = None
    status: Literal["ready", "pending"] = "pending"
    condition: str = ""
    temp_min: str = ""
    temp_max: str = ""
    precipitation: str = ""
    wind: str = ""
    source_id: str | None = None
    note: str = "天气待更新"
    issued_at: datetime | None = None
    valid_until: datetime | None = None


class AirQualityDay(BaseModel):
    date: Date | None = None
    status: Literal["ready", "pending"] = "pending"
    kind: Literal["forecast", "current"] = "forecast"
    aqi: Decimal | None = Field(default=None, ge=0)
    aqi_display: str = ""
    standard: str = ""
    category: str = ""
    health_advice: str = ""
    source_id: str | None = None
    retrieved_at: datetime | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    note: str = "暂未发布或未取得对应日期空气质量预报"


class ServiceStatus(BaseModel):
    service: str
    status: Literal["ready", "partial", "failed", "not_configured", "pending"]
    count: int = 0
    error_code: str | None = None
    duration_ms: int = 0
    message: str | None = None
    action: str | None = None


class TravelStop(BaseModel):
    place_id: str
    name: str
    start: time
    end: time
    suggested_duration_minutes: int
    fact_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    internal_route: list[str] = Field(default_factory=list)
    checkin_spots: list[str] = Field(default_factory=list)


class TravelDay(BaseModel):
    day: int
    date: Date | None
    stops: list[TravelStop] = Field(default_factory=list)
    routes: list[TravelRoute] = Field(default_factory=list)
    breaks: list[str] = Field(default_factory=list)
    weather: WeatherDay = Field(default_factory=WeatherDay)
    air_quality: AirQualityDay = Field(default_factory=AirQualityDay)
    alternatives: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CostItem(BaseModel):
    id: str
    label: str
    kind: Literal["official_rule", "supplier_quote", "estimate", "pending"] = "pending"
    unit_price: Decimal | None = Field(default=None, ge=0)
    quantity: int = Field(default=1, ge=1)
    days: int = Field(default=1, ge=1)
    subtotal: Decimal | None = None
    conditions: str = ""
    fact_refs: list[str] = Field(default_factory=list)
    source_id: str | None = None
    category: Literal[
        "intercity", "local_transport", "lodging", "tickets", "meals", "other", "contingency"
    ] = "other"
    currency: str = "CNY"
    unit: str = "人次"


class BookingTask(BaseModel):
    id: str
    title: str
    rule_status: Literal["verified", "pending"] = "pending"
    rule: str = "预约规则待核实"
    fact_refs: list[str] = Field(default_factory=list)
    url: str | None = None
    user_status: Literal["pending", "completed", "failed"] = "pending"


class BookingUpdate(BaseModel):
    user_status: Literal["pending", "completed", "failed"]


class VideoSegment(BaseModel):
    start: float = Field(default=0, ge=0)
    end: float | None = Field(default=None, ge=0)
    text: str = Field(min_length=1, max_length=2000)


class TravelVideo(BaseModel):
    id: str
    platform: Literal["douyin", "bilibili"]
    url: str
    title: str = ""
    author: str = ""
    published_at: datetime | None = None
    retrieved_at: datetime
    likes: int | None = Field(default=None, ge=0)
    favorites: int | None = Field(default=None, ge=0)
    counts_approximate: bool = False
    duration_seconds: float | None = Field(default=None, ge=0)
    topics: list[str] = Field(default_factory=list)
    selected: bool = False
    eligible: bool = False
    status: Literal["candidate", "rejected", "selected", "ready", "unavailable"] = "candidate"
    error_code: str | None = None
    metadata_error_code: str | None = None
    score: float = 0
    content_kind: Literal["subtitles", "transcription", "platform_summary"] | None = None
    content_truncated: bool = False
    source_id: str | None = None
    segments: list[VideoSegment] = Field(default_factory=list, max_length=1200)


class VideoAdvice(BaseModel):
    id: str
    kind: Literal["lodging", "restaurant", "pitfall", "checkin", "route"]
    place: str = Field(min_length=1, max_length=120)
    suggestion: str = Field(min_length=1, max_length=240)
    quote: str = Field(min_length=1, max_length=2000)
    source_id: str
    video_id: str
    timestamp_seconds: float = Field(ge=0)
    end_timestamp_seconds: float | None = Field(default=None, ge=0)
    status: Literal["reference"] = "reference"


class TravelPlan(BaseModel):
    draft: bool = True
    conditions: TravelConditions
    days: list[TravelDay]
    transport: list[str]
    lodging: list[str]
    cost_items: list[CostItem]
    known_subtotal: Decimal = Decimal("0")
    estimated_subtotal: Decimal = Decimal("0")
    contingency_subtotal: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    per_person: Decimal = Decimal("0")
    budget_difference: Decimal | None = None
    total_complete: bool = False
    preparation: list[str] = Field(default_factory=list)
    budget_limit: Decimal | None = None
    budget_exceeded: bool = False
    booking_tasks: list[BookingTask]
    unresolved_items: list[str]
    warnings: list[str] = Field(default_factory=list)
    video_advice: list[VideoAdvice] = Field(default_factory=list)


class ResearchIssue(BaseModel):
    stage: str
    code: str
    message: str
    action: str


class ResearchData(BaseModel):
    sources: list[TravelSource] = Field(default_factory=list)
    facts: list[TravelFact] = Field(default_factory=list)
    places: list[TravelPlace] = Field(default_factory=list)
    hotels: list[TravelPlace] = Field(default_factory=list)
    restaurants: list[TravelPlace] = Field(default_factory=list)
    images: list[TravelImage] = Field(default_factory=list)
    route_map: TravelMap = Field(default_factory=TravelMap)
    routes: list[TravelRoute] = Field(default_factory=list)
    weather: list[WeatherDay] = Field(default_factory=list)
    air_quality: list[AirQualityDay] = Field(default_factory=list)
    current_air_quality: AirQualityDay | None = None
    services: list[ServiceStatus] = Field(default_factory=list)
    issues: list[ResearchIssue] = Field(default_factory=list)
    videos: list[TravelVideo] = Field(default_factory=list)
    video_advice: list[VideoAdvice] = Field(default_factory=list)
    plan: TravelPlan | None = None


class TravelResearchPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    version: int
    status: Literal["queued", "researching", "ready", "partial", "failed"]
    stale: bool
    progress: int
    stage: str
    error_code: str | None
    conditions: TravelConditions
    data: ResearchData
    created_at: datetime
    completed_at: datetime | None


class TravelResearchAccepted(BaseModel):
    job_id: str
    research_id: uuid.UUID


class ConnectivityResult(BaseModel):
    services: list[ServiceStatus]
