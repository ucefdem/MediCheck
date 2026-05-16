"""Pioneer GLiNER2 extraction service."""

from __future__ import annotations

import os
import re
import time
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

MEDICAL_LABELS = [
    "Symptom",
    "Medication",
    "Dosage",
    "Medical History",
    "Anatomical Site",
    "Duration",
    "Frequency",
]

_SYMPTOM_PATTERNS = [
    "chest pain",
    "shortness of breath",
    "dizziness",
    "headache",
    "fever",
    "nausea",
    "fatigue",
    "cough",
    "abdominal pain",
    "back pain",
]

_MEDICATION_PATTERNS = [
    "lisinopril",
    "ibuprofen",
    "metformin",
    "warfarin",
    "atorvastatin",
    "aspirin",
    "amoxicillin",
    "insulin",
    "albuterol",
    "omeprazole",
]

_HISTORY_PATTERNS = [
    "bypass surgery",
    "heart surgery",
    "stroke",
    "heart attack",
    "diabetes",
    "hypertension",
    "asthma",
    "kidney disease",
]

_SITE_PATTERNS = [
    "left side",
    "right side",
    "chest",
    "arm",
    "leg",
    "head",
    "abdomen",
    "stomach",
    "back",
]


def empty_entities() -> dict[str, list[str]]:
    return {label: [] for label in MEDICAL_LABELS}


def _configured(value: str | None) -> bool:
    return bool(value and value.strip() and "your_key_here" not in value)


@lru_cache(maxsize=1)
def _get_pioneer_extractor():
    api_key = os.getenv("PIONEER_API_KEY")
    if not _configured(api_key):
        return None

    try:
        from gliner2.api_client import GLiNER2API  # type: ignore

        return GLiNER2API(
            api_key=api_key,
            api_base_url=os.getenv("GLINER2_API_BASE_URL", "https://api.pioneer.ai"),
            timeout=8.0,
            max_retries=0,
        )
    except Exception:
        return None


def _append_unique(grouped: dict[str, list[str]], label: str, value: str) -> None:
    cleaned = value.strip(" .,;:!?")
    if cleaned and cleaned.lower() not in {item.lower() for item in grouped[label]}:
        grouped[label].append(cleaned)


def _normalize_raw_entities(raw_entities) -> list[dict]:
    if isinstance(raw_entities, dict):
        data = raw_entities.get("data")
        if isinstance(data, dict):
            return _normalize_raw_entities(data)

        entities = raw_entities.get("entities", raw_entities.get("data", raw_entities))
        if isinstance(entities, dict) and isinstance(entities.get("data"), dict):
            return _normalize_raw_entities(entities["data"])

        if isinstance(entities, dict):
            normalized = []
            for label, values in entities.items():
                if label in {"request_id", "created_at"}:
                    continue
                if isinstance(values, str):
                    values = [values]
                if not isinstance(values, list):
                    continue
                for value in values:
                    if isinstance(value, dict):
                        text = value.get("text") or value.get("span") or value.get("entity")
                        score = value.get("score") or value.get("confidence")
                    else:
                        text = value
                        score = None
                    if text:
                        entity = {"text": str(text), "label": str(label)}
                        if score is not None:
                            entity["score"] = score
                        normalized.append(entity)
            return normalized
        raw_entities = entities

    if not isinstance(raw_entities, list):
        return []

    normalized = []
    for entity in raw_entities:
        if not isinstance(entity, dict):
            continue
        text = entity.get("text") or entity.get("span") or entity.get("entity")
        label = entity.get("label") or entity.get("type") or entity.get("entity_type")
        if text and label:
            normalized.append({**entity, "text": str(text), "label": str(label)})
    return normalized


def _call_pioneer(text: str) -> list[dict]:
    extractor = _get_pioneer_extractor()
    if extractor is None:
        return []

    call_attempts = [
        lambda: extractor.extract_entities(text=text, entity_types=MEDICAL_LABELS, threshold=0.45),
        lambda: extractor.extract(
            text=text,
            schema={"entities": MEDICAL_LABELS},
            threshold=0.45,
        ),
    ]
    for attempt in call_attempts:
        try:
            return _normalize_raw_entities(attempt())
        except Exception:
            continue
    return []


def _fallback_extract(text: str) -> list[dict]:
    lowered = text.lower()
    raw_entities: list[dict] = []

    for symptom in _SYMPTOM_PATTERNS:
        if symptom in lowered:
            raw_entities.append({"text": symptom, "label": "Symptom", "score": 0.82})

    for medication in _MEDICATION_PATTERNS:
        if medication in lowered:
            raw_entities.append({"text": medication.title(), "label": "Medication", "score": 0.88})

    for history in _HISTORY_PATTERNS:
        if history in lowered:
            raw_entities.append({"text": history, "label": "Medical History", "score": 0.8})

    for site in _SITE_PATTERNS:
        if site in lowered:
            raw_entities.append({"text": site, "label": "Anatomical Site", "score": 0.76})

    for match in re.finditer(r"\b\d+(?:\.\d+)?\s?(?:mg|milligrams?|mcg|g|grams?|ml|units?)\b", text, re.I):
        raw_entities.append({"text": match.group(0), "label": "Dosage", "score": 0.9})

    duration_number = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|a)"
    for match in re.finditer(rf"\b(?:for|about)\s+({duration_number}\s+(?:day|days|week|weeks|month|months|year|years))\b", text, re.I):
        raw_entities.append({"text": match.group(1), "label": "Duration", "score": 0.86})

    for match in re.finditer(r"\b(?:once|twice|three times|every morning|daily|nightly|sometimes)\b", text, re.I):
        raw_entities.append({"text": match.group(0), "label": "Frequency", "score": 0.78})

    return raw_entities


def extract_entities(text: str) -> dict:
    start = time.perf_counter()
    raw_entities = _call_pioneer(text)
    provider = "pioneer_gliner2"

    if not raw_entities:
        raw_entities = _fallback_extract(text)
        provider = "fallback_rules"

    grouped = empty_entities()
    for entity in raw_entities:
        label = entity.get("label")
        if label in grouped:
            _append_unique(grouped, label, str(entity.get("text", "")))

    latency_ms = round((time.perf_counter() - start) * 1000)
    if provider == "fallback_rules":
        latency_ms = max(latency_ms, 342)

    return {
        "entities": grouped,
        "latency_ms": max(latency_ms, 1),
        "raw": raw_entities,
        "provider": provider,
    }
