"""Shared utility functions."""

from __future__ import annotations

import json


def parse_json_response(raw_text: str) -> dict | list:
    """Parse JSON from an LLM response, stripping markdown code fences if present.

    Handles cases where the model wraps JSON in ```json ... ``` blocks.
    """
    text = raw_text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0].strip()
        return json.loads(text)
