"""Include the domain deck contract used by the browser renderer."""

import argparse
import json
from pathlib import Path

from app.engine.content.content import Deck
from app.main import app
from app.modules.outlines.schemas import OutlineEvent

schema = app.openapi()
deck = Deck.model_json_schema(ref_template="#/components/schemas/{model}")
definitions = deck.pop("$defs", {})
schema["components"]["schemas"].update(definitions)
schema["components"]["schemas"]["Deck"] = deck
outline_event = OutlineEvent.model_json_schema(ref_template="#/components/schemas/{model}")
schema["components"]["schemas"].update(outline_event.pop("$defs", {}))
schema["components"]["schemas"]["OutlineEvent"] = outline_event


def omit_null_defaults(value):
    if isinstance(value, dict):
        if value.get("default", False) is None:
            value.pop("default")
        for child in value.values():
            omit_null_defaults(child)
    elif isinstance(value, list):
        for child in value:
            omit_null_defaults(child)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    omit_null_defaults(schema)
    result = json.dumps(schema, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result + "\n", encoding="utf-8")
    else:
        print(result)
