"""Extract JSON objects from LLM text (markdown fences, noisy prefixes)."""

from __future__ import annotations

import json
from typing import Any


def extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if "```" in text:
        parts = text.split("```")
        for chunk in parts:
            chunk = chunk.strip()
            if chunk.lower().startswith("json"):
                chunk = chunk[4:].lstrip()
            if chunk.startswith("{") and chunk.endswith("}"):
                return json.loads(chunk)

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        msg = "Model response does not contain a JSON object"
        raise ValueError(msg)
    return json.loads(text[start : end + 1])


JSON_ONLY_SUFFIX = (
    "\n\nВерни ТОЛЬКО JSON, без пояснений. Начинай с { и заканчивай }"
)
