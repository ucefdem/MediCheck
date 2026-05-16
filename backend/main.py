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
import storage_service
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


class Doctor(BaseModel):
    id: str
    name: str
    avatar_url: str = ""
    created_at: Optional[str] = None


class PatientSession(BaseModel):
    id: str
    patient_id: str
    title: str
    status: str = "active"
    summary: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class Patient(BaseModel):
    id: str
    doctor_id: str = storage_service.DEMO_DOCTOR_ID
    name: str
    age: Optional[int] = None
    sex: Optional[str] = None
    summary: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    sessions: list[PatientSession] = []


class Recording(BaseModel):
    id: str
    session_id: str
    transcript: str
    duration_seconds: int = 0
    created_at: Optional[str] = None


class Analysis(BaseModel):
    id: Optional[str] = None
    recording_id: Optional[str] = None
    session_id: Optional[str] = None
    pioneer: dict
    pioneer_finetuned: Optional[dict] = None
    openai: dict
    tavily_cards: list[dict]
    winner: str
    created_at: Optional[str] = None


class FollowUpQuestion(BaseModel):
    id: str
    session_id: str
    recording_id: Optional[str] = None
    question: str
    reason: str = ""
    priority: str = "medium"
    answered: bool = False
    created_at: Optional[str] = None


class WorkspaceResponse(BaseModel):
    doctor: Doctor
    patients: list[Patient]


class SessionDetailResponse(BaseModel):
    session: PatientSession
    recordings: list[Recording]
    analyses: list[Analysis]
    follow_up_questions: list[FollowUpQuestion]


class CreatePatientRequest(BaseModel):
    name: str = Field(..., min_length=1)
    age: Optional[int] = None
    sex: Optional[str] = None
    summary: str = ""


class CreateSessionRequest(BaseModel):
    title: str = Field(..., min_length=1)
    status: str = "active"
    summary: str = "Awaiting first recording."


class CreateRecordingRequest(BaseModel):
    transcript: str = Field(..., min_length=1)
    duration_seconds: int = 0


class CreateRecordingResponse(BaseModel):
    recording: Recording
    analysis: Analysis
    session_summary: str
    follow_up_questions: list[FollowUpQuestion]


class UpdateFollowUpQuestionRequest(BaseModel):
    answered: bool


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


def _model_dump(model: BaseModel) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[attr-defined]
    return model.dict()


def _response_to_analysis_dict(response: TriageResponse) -> dict:
    return _model_dump(response)


async def _analyze_transcript(transcript: str) -> TriageResponse:
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


def _combined_entities(analysis: TriageResponse) -> dict[str, list[str]]:
    combined = {}
    analysis_dict = _response_to_analysis_dict(analysis)
    for label in MEDICAL_LABELS:
        combined[label] = _merge_entities(
            analysis_dict.get("pioneer_finetuned"),
            analysis_dict.get("pioneer"),
            analysis_dict.get("openai"),
            label=label,
        )
    return combined


def _generate_session_summary(transcripts: list[str], entities: dict[str, list[str]]) -> str:
    parts = []
    if entities.get("Symptom"):
        parts.append(f"Symptoms: {', '.join(entities['Symptom'][:4])}.")
    if entities.get("Medication"):
        parts.append(f"Medications: {', '.join(entities['Medication'][:4])}.")
    if entities.get("Duration"):
        parts.append(f"Duration: {', '.join(entities['Duration'][:2])}.")
    if entities.get("Medical History"):
        parts.append(f"History: {', '.join(entities['Medical History'][:3])}.")
    if parts:
        return " ".join(parts)
    latest = transcripts[-1].strip() if transcripts else ""
    return latest[:220] + ("..." if len(latest) > 220 else "") if latest else "Awaiting clinical context."


def _generate_follow_up_questions(
    transcripts: list[str],
    entities: dict[str, list[str]],
    tavily_cards: list[dict],
) -> list[dict]:
    text = " ".join(transcripts).lower()
    questions: list[dict] = []

    def add(question: str, reason: str, priority: str = "medium") -> None:
        if len(questions) < 5 and question not in {item["question"] for item in questions}:
            questions.append(
                {
                    "question": question,
                    "reason": reason,
                    "priority": priority,
                    "answered": False,
                }
            )

    if entities.get("Symptom") and not any(word in text for word in ["severity", "scale", "1 to 10", "one to ten"]):
        add(
            "Can you rate the main symptom from 1 to 10?",
            "Severity is important for triage and has not been captured yet.",
            "high",
        )
    if not entities.get("Duration"):
        add(
            "When did this start, and has it changed over time?",
            "Duration and progression are missing from the session context.",
            "high",
        )
    if not entities.get("Anatomical Site") and entities.get("Symptom"):
        add(
            "Where exactly do you feel the symptom?",
            "The anatomical location is missing or unclear.",
            "medium",
        )
    if entities.get("Medication") and not entities.get("Dosage"):
        add(
            "What dose do you take for each medication?",
            "Medication dosage is needed for safety checks.",
            "high",
        )
    if entities.get("Medication") and not entities.get("Frequency"):
        add(
            "How often do you take each medication?",
            "Medication frequency is missing from the current history.",
            "medium",
        )
    if "allerg" not in text:
        add(
            "Do you have any medication allergies?",
            "Allergy status is important before medication advice or escalation.",
            "high",
        )
    if tavily_cards:
        add(
            "Did a clinician prescribe these medications, or are any self-directed?",
            "Medication verification found drugs that should be tied to indication and source.",
            "medium",
        )
    if not entities.get("Medical History"):
        add(
            "Do you have any relevant medical history or prior surgeries?",
            "Past history can change triage risk and medication safety.",
            "medium",
        )

    if not questions:
        add(
            "Is there anything else about the symptoms that feels unusual or worrying?",
            "The current session is fairly complete, so this checks for missed context.",
            "low",
        )
    return questions[:5]


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
    return await _analyze_transcript(transcript)


@app.get("/workspace", response_model=WorkspaceResponse)
def workspace() -> WorkspaceResponse:
    return WorkspaceResponse(**storage_service.get_store().workspace())


@app.get("/patients/{patient_id}", response_model=Patient)
def get_patient(patient_id: str) -> Patient:
    patient = storage_service.get_store().patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return Patient(**patient)


@app.get("/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session(session_id: str) -> SessionDetailResponse:
    detail = storage_service.get_store().session_detail(session_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionDetailResponse(**detail)


@app.post("/patients", response_model=Patient)
def create_patient(request: CreatePatientRequest) -> Patient:
    patient = storage_service.get_store().create_patient(_model_dump(request))
    return Patient(**{**patient, "sessions": []})


@app.post("/patients/{patient_id}/sessions", response_model=PatientSession)
def create_session(patient_id: str, request: CreateSessionRequest) -> PatientSession:
    store = storage_service.get_store()
    if not store.patient(patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    session = store.create_session(patient_id, _model_dump(request))
    return PatientSession(**session)


@app.post("/sessions/{session_id}/recordings", response_model=CreateRecordingResponse)
async def create_recording(
    session_id: str,
    request: CreateRecordingRequest,
) -> CreateRecordingResponse:
    store = storage_service.get_store()
    session_before = store.session_detail(session_id)
    if not session_before:
        raise HTTPException(status_code=404, detail="Session not found")

    transcript = request.transcript.strip()
    recording = store.create_recording(
        session_id,
        {
            "transcript": transcript,
            "duration_seconds": max(request.duration_seconds, 0),
        },
    )

    analysis_response = await _analyze_transcript(transcript)
    analysis_dict = _response_to_analysis_dict(analysis_response)
    analysis = store.create_analysis(
        {
            "recording_id": recording["id"],
            "session_id": session_id,
            "pioneer": analysis_dict["pioneer"],
            "pioneer_finetuned": analysis_dict.get("pioneer_finetuned"),
            "openai": analysis_dict["openai"],
            "tavily_cards": analysis_dict["tavily_cards"],
            "winner": analysis_dict["winner"],
        }
    )

    detail = store.session_detail(session_id)
    transcripts = [item["transcript"] for item in (detail or {}).get("recordings", [])]
    entities = _combined_entities(analysis_response)
    session_summary = _generate_session_summary(transcripts, entities)
    store.update_session_summary(session_id, session_summary)
    questions = store.replace_follow_up_questions(
        session_id,
        recording["id"],
        _generate_follow_up_questions(
            transcripts,
            entities,
            analysis_dict["tavily_cards"],
        ),
    )

    return CreateRecordingResponse(
        recording=Recording(**recording),
        analysis=Analysis(**analysis),
        session_summary=session_summary,
        follow_up_questions=[FollowUpQuestion(**question) for question in questions],
    )


@app.patch("/follow-up-questions/{question_id}", response_model=FollowUpQuestion)
def update_follow_up_question(
    question_id: str,
    request: UpdateFollowUpQuestionRequest,
) -> FollowUpQuestion:
    question = storage_service.get_store().update_question(question_id, request.answered)
    if not question:
        raise HTTPException(status_code=404, detail="Follow-up question not found")
    return FollowUpQuestion(**question)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
