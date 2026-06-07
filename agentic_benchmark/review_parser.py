from __future__ import annotations

import json
import re
from typing import Any

from .code_processing import strip_ansi

MAX_FEEDBACK_ITEMS = 6
MAX_FEEDBACK_CHARS = 4000


def find_json_objects(text: str) -> list[str]:
    objects = []
    stack = []
    start = None
    in_string = False
    escape = False

    for i, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char == "{":
            if not stack:
                start = i
            stack.append(char)
        elif char == "}":
            if stack:
                stack.pop()
                if not stack and start is not None:
                    objects.append(text[start : i + 1])
                    start = None

    return objects


def extract_review_json(text: str) -> dict[str, Any] | None:
    text = strip_ansi(text).strip()

    fenced = re.findall(
        r"```(?:json)?\s*(.*?)```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    candidates = fenced + find_json_objects(text)

    for candidate in reversed(candidates):
        try:
            data = json.loads(candidate.strip())
        except json.JSONDecodeError:
            continue

        if isinstance(data, dict) and "approved" in data:
            return data

    return None


def clean_list(value: Any, max_items: int = MAX_FEEDBACK_ITEMS) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = [str(item) for item in value]
    else:
        items = [str(value)]

    cleaned = []
    for item in items:
        item = strip_ansi(item).strip()
        item = re.sub(r"\s+", " ", item)
        if item:
            cleaned.append(item)

    return cleaned[:max_items]


def parse_review(text: str) -> dict[str, Any]:
    data = extract_review_json(text)

    if data is None:
        fallback = strip_ansi(text).strip()
        fallback = fallback[-MAX_FEEDBACK_CHARS:]

        return {
            "approved": fallback.upper().startswith("APPROVED"),
            "score": 0,
            "critical_issues": ["Reviewer output was not valid JSON."],
            "suggestions": [
                "Reviewer muss ausschließlich ein valides JSON-Objekt ohne Markdown und ohne Thinking-Text zurückgeben.",
                fallback,
            ],
        }

    score = data.get("score", 0)
    try:
        score = int(score)
    except (TypeError, ValueError):
        score = 0

    return {
        "approved": bool(data.get("approved", False)),
        "score": max(0, min(100, score)),
        "critical_issues": clean_list(data.get("critical_issues")),
        "suggestions": clean_list(data.get("suggestions", data.get("recommendations"))),
    }


def compact_feedback(review: dict[str, Any] | None, syntax_error: str | None) -> str:
    if not review and not syntax_error:
        return "Noch kein Reviewer-Feedback vorhanden."

    payload = {
        "syntax_error": syntax_error or None,
        "approved": review.get("approved") if review else False,
        "score": review.get("score") if review else 0,
        "critical_issues": review.get("critical_issues", [])[:MAX_FEEDBACK_ITEMS] if review else [],
        "suggestions": review.get("suggestions", [])[:MAX_FEEDBACK_ITEMS] if review else [],
    }

    text = json.dumps(payload, ensure_ascii=False, indent=2)

    if len(text) > MAX_FEEDBACK_CHARS:
        text = text[:MAX_FEEDBACK_CHARS] + "\n... gekürzt ..."

    return text
