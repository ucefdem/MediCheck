"""OpenAI benchmark extraction service."""

from __future__ import annotations

import json
import os
import time
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI

from pioneer_service import MEDICAL_LABELS, empty_entities

load_dotenv()

_client: AsyncOpenAI | None = None

SYSTEM_PROMPT = """Extract medical entities from the patient transcript.
Return ONLY valid JSON with these exact keys:
{
  "Symptom": [],
  "Medication": [],
  "Dosage": [],
  "Medical History": [],
  "Anatomical Site": [],
  "Duration": [],
  "Frequency": []
}
Each value is a list of strings found in the text.
Do not add any explanation or markdown. JSON only."""


def _normalize_entities(value: Any) -> dict[str, list[str]]:
    grouped = empty_entities()
    if not isinstance(value, dict):
        return grouped

    for label in MEDICAL_LABELS:
        items = value.get(label, [])
        if isinstance(items, str):
            items = [items]
        if isinstance(items, list):
            grouped[label] = [str(item).strip() for item in items if str(item).strip()]

    return grouped


async def extract_entities(text: str) -> dict[str, Any]:
    """Extract entities using GPT-4o-mini as the benchmark baseline."""
    start = time.perf_counter()

    if not os.getenv("OPENAI_API_KEY"):
        return {
            "entities": empty_entities(),
            "latency_ms": 9999,
            "error": "OPENAI_API_KEY is not set",
        }

    try:
        global _client
        if _client is None:
            _client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        response = await _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = response.choices[0].message.content or "{}"
        entities = _normalize_entities(json.loads(content))
        error = None
    except Exception as exc:
        entities = empty_entities()
        error = str(exc)

    result: dict[str, Any] = {
        "entities": entities,
        "latency_ms": round((time.perf_counter() - start) * 1000),
    }
    if error:
        result["error"] = error
    return result
