"""Gradium voice transcription helpers."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

GRADIUM_STT_URL = os.getenv("GRADIUM_STT_URL", "wss://api.gradium.ai/api/speech/asr")


def get_gradium_api_key() -> str | None:
    value = os.getenv("GRADIUM_API_KEY")
    if not value or "your_key_here" in value:
        return None
    return value
