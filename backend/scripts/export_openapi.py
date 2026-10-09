"""Include the domain deck contract used by the browser renderer."""

import json

from app.domain.content import Deck
from app.main import app
from app.schemas.outline import OutlineEvent

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


omit_null_defaults(schema)
print(json.dumps(schema, ensure_ascii=False))
