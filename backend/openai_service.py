"""OpenAI benchmark extraction service."""

from __future__ import annotations

import json
import os
import time

from dotenv import load_dotenv

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None  # type: ignore[assignment]

import pioneer_service

load_dotenv()

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

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
Each value must be a list of strings found directly in the transcript.
Do not include markdown, explanations, or extra keys."""


def _configured(value: str | None) -> bool:
    return bool(value and value.strip() and "your_key_here" not in value)


def _empty_entities() -> dict[str, list[str]]:
    return {label: [] for label in pioneer_service.MEDICAL_LABELS}


def _normalize_entities(value: object) -> dict[str, list[str]]:
    entities = _empty_entities()
    if not isinstance(value, dict):
        return entities

    for label in entities:
        raw_values = value.get(label, [])
        if isinstance(raw_values, str):
            raw_values = [raw_values]
        if isinstance(raw_values, list):
            entities[label] = [str(item).strip() for item in raw_values if str(item).strip()]
    return entities


def _fallback_extract(text: str) -> dict[str, list[str]]:
    result = pioneer_service.extract_entities(text)
    return _normalize_entities(result.get("entities", {}))


async def extract_entities(text: str) -> dict:
    start = time.perf_counter()
    api_key = os.getenv("OPENAI_API_KEY")

    if not _configured(api_key) or AsyncOpenAI is None:
        return {
            "entities": _fallback_extract(text),
            "latency_ms": max(round((time.perf_counter() - start) * 1000), 1200),
            "provider": "fallback_rules",
        }

    try:
        client = AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = response.choices[0].message.content or "{}"
        entities = _normalize_entities(json.loads(content))
        provider = OPENAI_MODEL
    except Exception:
        entities = _fallback_extract(text)
        provider = "fallback_rules"

    return {
        "entities": entities,
        "latency_ms": max(round((time.perf_counter() - start) * 1000), 1),
        "provider": provider,
    }
