"""FastAPI entrypoint for Pioneer-Med."""

from __future__ import annotations

import asyncio

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import openai_service
import pioneer_service
import tavily_service

load_dotenv()

app = FastAPI(title="Pioneer-Med API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TriageRequest(BaseModel):
    text: str


class TriageResponse(BaseModel):
    pioneer: dict
    openai: dict
    tavily_cards: list
    transcript: str
    winner: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "message": "Pioneer-Med is running"}


@app.post("/triage", response_model=TriageResponse)
async def triage(request: TriageRequest) -> dict:
    """Run Pioneer and OpenAI extraction, then verify extracted medications."""
    transcript = request.text.strip()
    if len(transcript) < 10:
        raise HTTPException(status_code=400, detail="Transcript too short")

    try:
        pioneer_result, openai_result = await asyncio.gather(
            asyncio.to_thread(pioneer_service.extract_entities, transcript),
            openai_service.extract_entities(transcript),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}") from exc

    medications = pioneer_result["entities"].get("Medication", [])
    symptoms = pioneer_result["entities"].get("Symptom", [])
    medical_history = pioneer_result["entities"].get("Medical History", [])

    try:
        tavily_cards = await tavily_service.verify_medications(
            medications, symptoms, medical_history
        )
    except Exception:
        tavily_cards = []

    winner = (
        "pioneer"
        if pioneer_result["latency_ms"] <= openai_result["latency_ms"]
        else "openai"
    )

    return {
        "pioneer": pioneer_result,
        "openai": openai_result,
        "tavily_cards": tavily_cards,
        "transcript": transcript,
        "winner": winner,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
