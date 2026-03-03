"""Shared utility functions."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from functools import wraps

logger = logging.getLogger(__name__)


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


def _extract_retry_delay(error: Exception) -> float | None:
    """Extract retry delay from a 429/RESOURCE_EXHAUSTED error message."""
    msg = str(error)
    if "429" not in msg and "RESOURCE_EXHAUSTED" not in msg:
        return None
    # Look for "retryDelay": "56s" or "retry in 56.78s"
    match = re.search(r"retry\s*(?:in|Delay['\"]?\s*[:=]\s*['\"]?)\s*([\d.]+)", msg, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return 60.0  # Default 60s for 429 without explicit delay


def gemini_retry(max_attempts: int = 5, base_wait: float = 2.0, max_wait: float = 30.0):
    """Retry decorator with smart 429 rate-limit handling.

    For 429 errors: waits the API-specified delay (+ 5s buffer).
    For other errors: exponential backoff (2s → 4s → 8s, capped at max_wait).
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    retry_delay = _extract_retry_delay(e)
                    if retry_delay is not None:
                        wait_time = retry_delay + 5  # buffer
                        logger.warning(
                            "429 rate limit hit (attempt %d/%d). "
                            "Waiting %.0fs before retry...",
                            attempt, max_attempts, wait_time,
                        )
                        await asyncio.sleep(wait_time)
                    elif attempt < max_attempts:
                        wait_time = min(base_wait * (2 ** (attempt - 1)), max_wait)
                        logger.warning(
                            "API error (attempt %d/%d): %s. "
                            "Retrying in %.0fs...",
                            attempt, max_attempts, str(e)[:100], wait_time,
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        raise
            raise last_error  # type: ignore[misc]
        return wrapper
    return decorator
