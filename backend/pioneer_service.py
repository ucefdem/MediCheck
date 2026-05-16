"""Pioneer GLiNER2 extraction service."""

from __future__ import annotations

import os
import re
import time
from typing import Any

from dotenv import load_dotenv

load_dotenv()

MEDICAL_LABELS = [
    "Symptom",
    "Medication",
    "Dosage",
    "Medical History",
    "Anatomical Site",
    "Duration",
    "Frequency",
]

_model: Any | None = None
_model_load_error: str | None = None


def empty_entities() -> dict[str, list[str]]:
    return {label: [] for label in MEDICAL_LABELS}


def _append_unique(grouped: dict[str, list[str]], label: str, value: str) -> None:
    cleaned = value.strip(" .,;:")
    if cleaned and cleaned not in grouped[label]:
        grouped[label].append(cleaned)


def _regex_fallback(text: str) -> list[dict[str, Any]]:
    """Small local fallback for demos when GLiNER is unavailable."""
    patterns: list[tuple[str, str]] = [
        ("Symptom", r"\b(chest pain|headache|fever|shortness of breath|nausea|dizziness|cough|fatigue)\b"),
        ("Medication", r"\b(Lisinopril|Ibuprofen|Metformin|Warfarin|Aspirin|Atorvastatin|Amoxicillin)\b"),
        ("Dosage", r"\b(\d+\s?(?:mg|milligrams|mcg|g|grams|ml|units))\b"),
        ("Medical History", r"\b(bypass surgery|heart attack|stroke|diabetes|hypertension|asthma|surgery)\b(?:\s+(?:in|back in)\s+\d{4})?"),
        ("Anatomical Site", r"\b(left side|right side|chest|arm|leg|head|stomach|back)\b"),
        ("Duration", r"\b(?:for\s+)?(\d+\s+(?:days?|weeks?|months?|years?)|three days|two days|one week)\b"),
        ("Frequency", r"\b(every morning|every night|twice a day|once a day|daily|weekly)\b"),
    ]

    entities: list[dict[str, Any]] = []
    for label, pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            entities.append(
                {
                    "text": match.group(1) if match.groups() else match.group(0),
                    "label": label,
                    "score": 0.72,
                    "start": match.start(),
                    "end": match.end(),
                }
            )
    return entities


def get_model() -> Any | None:
    """Load GLiNER once. Return None if the local model is not available."""
    global _model, _model_load_error

    if os.getenv("PIONEER_USE_LOCAL_GLINER", "").lower() not in {"1", "true", "yes"}:
        _model_load_error = "Set PIONEER_USE_LOCAL_GLINER=true to enable local GLiNER loading"
        return None

    if _model is not None or _model_load_error is not None:
        return _model

    try:
        from gliner import GLiNER

        _model = GLiNER.from_pretrained("knowledgator/gliner-multitask-large-v0.5")
    except Exception as exc:  # pragma: no cover - depends on local model/network.
        _model_load_error = str(exc)
        _model = None

    return _model


def extract_entities(text: str) -> dict[str, Any]:
    """
    Extract medical entities with GLiNER when available.

    Returns a stable response shape for the frontend and benchmark script.
    """
    start = time.perf_counter()
    model = get_model()

    if model is None:
        raw_entities = _regex_fallback(text)
        engine = "regex_fallback"
    else:
        raw_entities = model.predict_entities(text, MEDICAL_LABELS, threshold=0.45)
        engine = "gliner"

    grouped = empty_entities()
    for entity in raw_entities:
        label = entity.get("label")
        value = entity.get("text")
        if label in grouped and isinstance(value, str):
            _append_unique(grouped, label, value)

    latency_ms = round((time.perf_counter() - start) * 1000)
    simulated_latency = False
    if engine == "regex_fallback":
        latency_ms = max(latency_ms, 342)
        simulated_latency = True

    return {
        "entities": grouped,
        "latency_ms": latency_ms,
        "raw": raw_entities,
        "engine": engine,
        "simulated_latency": simulated_latency,
        "model_error": _model_load_error,
    }
