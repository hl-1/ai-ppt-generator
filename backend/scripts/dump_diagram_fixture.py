"""Generate shared geometry fixtures for the Java/Python diagram parity check."""

import json

from app.core.paths import SHARED_DIR
from app.domain.content import DiagramBlock
from app.domain.diagram_layout import layout_diagram, parse_mermaid

SOURCES = [
    "flowchart LR\n A[接收请求] --> B[处理任务] --> C[完成交付]",
    "flowchart TB\n A{条件是否满足} -->|通过| B[继续处理]\n A -->|未通过| C[退回修改]",
    "flowchart TB\n A[接收任务] --> B[校验资料]\n A --> C[查询结果]\n B --> D[汇总结果]\n C --> D",
    "flowchart LR\n A[执行任务] --> B{结果是否通过}\n B -->|重试| A\n B -->|通过| C[完成]",
]


def main():
    cases = []
    for index, source in enumerate(SOURCES):
        nodes, edges, direction = parse_mermaid(source)
        block = DiagramBlock(
            id=f"flow-{index}",
            slot_id="visual",
            diagram_type="flow",
            nodes=nodes,
            edges=edges,
            direction=direction,
        )
        cases.append(
            {
                "block": block.model_dump(mode="json"),
                "width": 856,
                "height": 320,
                "expected": layout_diagram(block, 856, 320).model_dump(mode="json"),
            }
        )
    path = SHARED_DIR / "diagram-layout-fixtures.json"
    path.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
