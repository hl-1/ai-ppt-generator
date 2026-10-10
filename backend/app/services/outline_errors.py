from app.schemas.outline import OutlineErrorCode, OutlineFailure, OutlineIssue, OutlineStage

ERRORS: dict[OutlineErrorCode, tuple[str, str, bool]] = {
    "model_auth_failed": (
        "AI 服务拒绝访问凭证",
        "请联系管理员检查 AI 服务凭证与访问权限后重新生成。",
        False,
    ),
    "model_rate_limited": (
        "AI 服务请求受限或额度不足",
        "请稍后重新生成；持续失败时联系管理员检查额度。",
        True,
    ),
    "model_request_rejected": (
        "AI 服务不接受当前模型请求",
        "请联系管理员检查模型名称、请求参数及输入长度后重新生成。",
        False,
    ),
    "queue_unavailable": (
        "任务未能进入生成队列",
        "请稍后重新生成；持续失败时联系管理员检查队列服务。",
        True,
    ),
    "input_load_failed": (
        "无法读取当前输入材料或设置",
        "请检查输入材料与项目设置，再重新生成。",
        True,
    ),
    "input_missing": ("没有可用的输入材料", "请添加主题或材料，再重新生成。", False),
    "travel_research_failed": (
        "旅行资料查询未完成",
        "请检查旅行条件，查看资料服务状态后重新查询。",
        True,
    ),
    "travel_timeout": ("旅行资料查询超时", "已获取的资料仍然保留，请稍后重新查询。", True),
    "llm_not_configured": ("AI 服务未配置", "请联系管理员配置 AI 服务凭证后重新生成。", False),
    "model_timeout": (
        "AI 规划大纲时响应超时",
        "请稍后重新生成；持续超时时联系管理员检查 AI 服务。",
        True,
    ),
    "model_unavailable": (
        "AI 服务调用失败",
        "请稍后重新生成；持续失败时联系管理员检查服务及额度。",
        True,
    ),
    "invalid_model_output": (
        "AI 返回的大纲格式不符合要求",
        "请重新生成；持续失败时联系管理员检查模型配置。",
        True,
    ),
    "invalid_outline": (
        "大纲结构校验未通过",
        "请重新生成；持续失败时联系管理员检查生成规则。",
        True,
    ),
    "save_failed": ("生成结果未能保存", "请检查项目设置是否在生成期间被修改，然后重新生成。", True),
    "unknown": ("任务执行异常", "请重新生成；持续失败时提供任务编号联系管理员。", True),
}


def outline_failure(code: OutlineErrorCode, stage: OutlineStage) -> OutlineFailure:
    message, action, retryable = ERRORS[code]
    return OutlineFailure(
        code=code, stage=stage, message=message, action=action, retryable=retryable
    )


def travel_service_issue(service: str, code: str | None) -> OutlineIssue:
    label = {"firecrawl": "官网检索", "amap": "地图与路线", "qweather": "天气"}.get(
        service, "资料服务"
    )
    value = code or "unavailable"
    if "not_configured" in value or value == "missing_key":
        reason, action = "未配置", "请联系管理员配置该服务；相关信息暂列为待核实。"
    elif "timeout" in value:
        reason, action = "查询超时", "请稍后刷新旅行资料。"
    elif value in {"http_401", "http_403", "provider_rejected"}:
        reason, action = "访问被拒绝", "请联系管理员检查服务凭证与访问权限。"
    elif value == "http_429":
        reason, action = "触发请求频率或并发限制", "系统已按限流规则等待重试；仍未完成时稍后刷新资料。"
    elif value in {"http_402", "credits_exhausted"}:
        reason, action = "额度不足", "请检查该服务剩余额度或计费状态后刷新资料。"
    elif value in {"no_eligible_videos", "no_candidates"}:
        reason, action = "暂无符合条件的视频", "查看候选视频的热度、发布时间和读取状态后刷新。"
    elif value.startswith("http_5"):
        reason, action = "暂时不可用", "请稍后刷新旅行资料。"
    elif value == "invalid_response":
        reason, action = "返回结果无法识别", "请刷新资料；持续失败时联系管理员检查服务配置。"
    else:
        reason, action = "查询未全部完成", "请查看已获取的资料，补充核实后刷新。"
    return OutlineIssue(code=value, service=service, message=f"{label}{reason}", action=action)
