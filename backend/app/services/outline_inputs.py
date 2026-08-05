import hashlib
import json

from app.models.project import Project


def project_input_signature(project: Project) -> str:
    """计算影响大纲的输入指纹。

    大纲草稿生成后仍允许用户调整设置或材料，但确认时必须发现它已经过期，
    不能把旧大纲与新输入静默绑定。
    """
    payload = {
        "title": project.title,
        "audience": project.audience,
        "tone": project.tone,
        "page_count": project.page_count,
        "sources": [
            {
                "id": str(source.id),
                "sections": source.sections,
            }
            for source in project.sources
        ],
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()
