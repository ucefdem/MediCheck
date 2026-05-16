"""FastAPI entrypoint for MediCheck."""

from __future__ import annotations

import asyncio
import json
from typing import Optional

import websockets
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import gradium_service
import openai_service
import pioneer_service
import tavily_service

MEDICAL_LABELS = pioneer_service.MEDICAL_LABELS


class TriageRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Raw patient transcript")


class ExtractionResult(BaseModel):
    entities: dict[str, list[str]]
    latency_ms: int
    provider: Optional[str] = None


class TavilyCard(BaseModel):
    drug: str
    indication: str
    contraindications: str = ""
    warning: Optional[str] = None
    source: str = ""


class TriageResponse(BaseModel):
    pioneer: ExtractionResult
    pioneer_finetuned: Optional[ExtractionResult] = None
    openai: ExtractionResult
    tavily_cards: list[TavilyCard]
    transcript: str
    winner: str


def _merge_entities(*results: Optional[dict], label: str) -> list[str]:
    merged = []
    seen = set()
    for result in results:
        if not result:
            continue
        values = result.get("entities", {}).get(label, [])
        for value in values:
            cleaned = str(value).strip()
            key = cleaned.lower()
            if cleaned and key not in seen:
                merged.append(cleaned)
                seen.add(key)
    return merged


def _has_any_entities(result: Optional[dict]) -> bool:
    if not result:
        return False
    entities = result.get("entities", {})
    return any(values for values in entities.values())


app = FastAPI(
    title="MediCheck API",
    description="Privacy-first medical entity extraction benchmark API.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "message": "MediCheck API is running"}


@app.websocket("/gradium/stt")
async def gradium_stt_proxy(websocket: WebSocket) -> None:
    await websocket.accept()

    api_key = gradium_service.get_gradium_api_key()
    if api_key is None:
        await websocket.send_json(
            {
                "type": "error",
                "message": "GRADIUM_API_KEY is not configured on the backend.",
            }
        )
        await websocket.close(code=1008)
        return

    setup = {
        "type": "setup",
        "model_name": "default",
        "input_format": "pcm_16000",
    }

    try:
        async with websockets.connect(
            gradium_service.GRADIUM_STT_URL,
            additional_headers={"x-api-key": api_key},
        ) as gradium_ws:
            await gradium_ws.send(json.dumps(setup))

            async def browser_to_gradium() -> None:
                while True:
                    message = await websocket.receive_json()
                    message_type = message.get("type")
                    if message_type in {"audio", "flush", "end_of_stream"}:
                        await gradium_ws.send(json.dumps(message))
                    if message_type == "end_of_stream":
                        return

            async def gradium_to_browser() -> None:
                async for message in gradium_ws:
                    parsed = json.loads(message)
                    await websocket.send_json(parsed)
                    if parsed.get("type") == "end_of_stream":
                        return

            await asyncio.gather(browser_to_gradium(), gradium_to_browser())
    except WebSocketDisconnect:
        return
    except Exception as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass


@app.on_event("startup")
async def warm_up_pioneer() -> None:
    await asyncio.to_thread(
        pioneer_service.extract_entities,
        "Warmup patient takes 10mg Lisinopril for chest pain.",
    )


@app.post("/triage", response_model=TriageResponse)
async def triage(request: TriageRequest) -> TriageResponse:
    transcript = request.text.strip()
    if len(transcript) < 10:
        raise HTTPException(status_code=400, detail="Transcript too short")

    try:
        pioneer_result, pioneer_finetuned_result, openai_result = await asyncio.gather(
            asyncio.to_thread(pioneer_service.extract_entities, transcript),
            asyncio.to_thread(pioneer_service.extract_finetuned_entities, transcript),
            openai_service.extract_entities(transcript),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}") from exc

    medications = _merge_entities(
        pioneer_finetuned_result,
        pioneer_result,
        openai_result,
        label="Medication",
    )
    symptoms = _merge_entities(
        pioneer_finetuned_result,
        pioneer_result,
        openai_result,
        label="Symptom",
    )
    medical_history = _merge_entities(
        pioneer_finetuned_result,
        pioneer_result,
        openai_result,
        label="Medical History",
    )

    tavily_cards = []
    if medications:
        try:
            tavily_cards = await tavily_service.verify_medications(
                medications,
                symptoms,
                medical_history,
            )
        except Exception:
            tavily_cards = []

    candidates = {}
    if _has_any_entities(pioneer_result):
        candidates["pioneer"] = pioneer_result.get("latency_ms", 0)
    if _has_any_entities(openai_result):
        candidates["openai"] = openai_result.get("latency_ms", 0)
    if _has_any_entities(pioneer_finetuned_result):
        candidates["pioneer_finetuned"] = pioneer_finetuned_result.get("latency_ms", 0)
    winner = min(candidates, key=candidates.get) if candidates else "pioneer"

    return TriageResponse(
        pioneer=ExtractionResult(
            entities=pioneer_result.get("entities", {label: [] for label in MEDICAL_LABELS}),
            latency_ms=pioneer_result.get("latency_ms", 0),
            provider=pioneer_result.get("provider"),
        ),
        pioneer_finetuned=(
            ExtractionResult(
                entities=pioneer_finetuned_result.get("entities", {label: [] for label in MEDICAL_LABELS}),
                latency_ms=pioneer_finetuned_result.get("latency_ms", 0),
                provider=pioneer_finetuned_result.get("provider"),
            )
            if pioneer_finetuned_result
            else None
        ),
        openai=ExtractionResult(
            entities=openai_result.get("entities", {label: [] for label in MEDICAL_LABELS}),
            latency_ms=openai_result.get("latency_ms", 0),
            provider=openai_result.get("provider"),
        ),
        tavily_cards=[TavilyCard(**card) for card in tavily_cards],
        transcript=transcript,
        winner=winner,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
