"""FastAPI entrypoint for MediCheck."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

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


class DoctorResponse(BaseModel):
    id: str
    name: str
    avatar_url: Optional[str] = None


class SessionListItem(BaseModel):
    id: str
    title: str
    status: str
    updated_at: str


class PatientResponse(BaseModel):
    id: str
    name: str
    age: Optional[int] = None
    sex: Optional[str] = None
    summary: Optional[str] = None
    sessions: list[SessionListItem] = []


class WorkspaceResponse(BaseModel):
    doctor: DoctorResponse
    patients: list[PatientResponse]


class SessionResponse(BaseModel):
    id: str
    patient_id: str
    title: str
    status: str
    summary: Optional[str] = None


class RecordingRequest(BaseModel):
    transcript: str = Field(..., min_length=1)
    duration_seconds: int = 0


class RecordingResponse(BaseModel):
    id: str
    session_id: str
    transcript: str
    duration_seconds: int
    created_at: str


class AnalysisResponse(BaseModel):
    pioneer: ExtractionResult
    pioneer_finetuned: Optional[ExtractionResult] = None
    openai: ExtractionResult
    tavily_cards: list[TavilyCard]
    winner: str


class FollowUpQuestionResponse(BaseModel):
    id: str
    question: str
    reason: str
    priority: str
    answered: bool


class SessionDetailResponse(BaseModel):
    session: SessionResponse
    recordings: list[RecordingResponse]
    analyses: list[AnalysisResponse]
    follow_up_questions: list[FollowUpQuestionResponse]


class CreateRecordingResponse(BaseModel):
    recording: RecordingResponse
    analysis: AnalysisResponse
    session_summary: str
    follow_up_questions: list[FollowUpQuestionResponse]


class CreatePatientRequest(BaseModel):
    name: str = Field(..., min_length=1)
    age: Optional[int] = None
    sex: Optional[str] = None
    summary: Optional[str] = None


class CreateSessionRequest(BaseModel):
    title: str = Field(..., min_length=1)
    status: str = "active"
    summary: Optional[str] = None


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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _empty_entities() -> dict[str, list[str]]:
    return {label: [] for label in MEDICAL_LABELS}


def _as_extraction_result(result: Optional[dict]) -> ExtractionResult:
    result = result or {}
    return ExtractionResult(
        entities=result.get("entities", _empty_entities()),
        latency_ms=result.get("latency_ms", 0),
        provider=result.get("provider"),
    )


def _as_analysis_response(analysis: dict) -> AnalysisResponse:
    return AnalysisResponse(
        pioneer=_as_extraction_result(analysis.get("pioneer")),
        pioneer_finetuned=(
            _as_extraction_result(analysis.get("pioneer_finetuned"))
            if analysis.get("pioneer_finetuned")
            else None
        ),
        openai=_as_extraction_result(analysis.get("openai")),
        tavily_cards=[TavilyCard(**card) for card in analysis.get("tavily_cards", [])],
        winner=analysis.get("winner", "pioneer"),
    )


def _session_list_item(session: dict) -> SessionListItem:
    return SessionListItem(
        id=session["id"],
        title=session["title"],
        status=session["status"],
        updated_at=session["updated_at"],
    )


def _patient_response(patient: dict) -> PatientResponse:
    sessions = [
        _session_list_item(session)
        for session in _STORE["sessions"].values()
        if session["patient_id"] == patient["id"]
    ]
    sessions.sort(key=lambda session: session.updated_at, reverse=True)
    return PatientResponse(
        id=patient["id"],
        name=patient["name"],
        age=patient.get("age"),
        sex=patient.get("sex"),
        summary=patient.get("summary"),
        sessions=sessions,
    )


def _session_response(session: dict) -> SessionResponse:
    return SessionResponse(
        id=session["id"],
        patient_id=session["patient_id"],
        title=session["title"],
        status=session["status"],
        summary=session.get("summary"),
    )


def _recording_response(recording: dict) -> RecordingResponse:
    return RecordingResponse(
        id=recording["id"],
        session_id=recording["session_id"],
        transcript=recording["transcript"],
        duration_seconds=recording["duration_seconds"],
        created_at=recording["created_at"],
    )


def _question_response(question: dict) -> FollowUpQuestionResponse:
    return FollowUpQuestionResponse(
        id=question["id"],
        question=question["question"],
        reason=question["reason"],
        priority=question["priority"],
        answered=question["answered"],
    )


def _new_store() -> dict:
    return {
        "doctor": {
            "id": "doctor_demo",
            "name": "Dr. Youssef",
            "avatar_url": "/doctor-avatar.jpg",
        },
        "patients": {
            "patient_1": {
                "id": "patient_1",
                "name": "Youssef Amrani",
                "age": 34,
                "sex": "male",
                "summary": "Migraine assessment",
            },
            "patient_2": {
                "id": "patient_2",
                "name": "Amal Benali",
                "age": 42,
                "sex": "female",
                "summary": "Chest pain follow-up",
            },
            "patient_3": {
                "id": "patient_3",
                "name": "Nora Haddad",
                "age": 57,
                "sex": "female",
                "summary": "Medication review",
            },
        },
        "sessions": {
            "session_1": {
                "id": "session_1",
                "patient_id": "patient_1",
                "title": "Migraine intake",
                "status": "active",
                "summary": "Patient reports severe migraine for the past week and started Doliprane.",
                "updated_at": "2026-05-16T12:00:00Z",
            },
            "session_2": {
                "id": "session_2",
                "patient_id": "patient_2",
                "title": "Chest pain intake",
                "status": "active",
                "summary": "Chest pain follow-up with medication and cardiac history review.",
                "updated_at": "2026-05-16T12:10:00Z",
            },
        },
        "recordings": {
            "recording_1": {
                "id": "recording_1",
                "session_id": "session_1",
                "transcript": (
                    "Hi, my name is Youssef. I suffer from severe migraine for the past "
                    "week. I started taking Doliprane."
                ),
                "duration_seconds": 18,
                "created_at": "2026-05-16T12:12:00Z",
            }
        },
        "analyses": {},
        "follow_up_questions": {
            "question_1": {
                "id": "question_1",
                "session_id": "session_1",
                "question": "What dose of Doliprane did you take, and how often?",
                "reason": "Medication dosage and frequency are missing.",
                "priority": "high",
                "answered": False,
            },
            "question_2": {
                "id": "question_2",
                "session_id": "session_1",
                "question": "Do you have vision changes, weakness, fever, or vomiting?",
                "reason": "Associated symptoms help identify migraine red flags.",
                "priority": "high",
                "answered": False,
            },
            "question_3": {
                "id": "question_3",
                "session_id": "session_1",
                "question": "How severe is the migraine from 1 to 10?",
                "reason": "Severity has not been captured yet.",
                "priority": "medium",
                "answered": False,
            },
        },
    }


_STORE = _new_store()


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


async def _analyze_transcript(transcript: str) -> dict:
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

    return {
        "pioneer": pioneer_result,
        "pioneer_finetuned": pioneer_finetuned_result,
        "openai": openai_result,
        "tavily_cards": tavily_cards,
        "winner": winner,
    }


def _build_session_summary(session_id: str, latest_analysis: dict) -> str:
    transcripts = [
        recording["transcript"]
        for recording in _STORE["recordings"].values()
        if recording["session_id"] == session_id
    ]
    symptoms = _merge_entities(
        latest_analysis.get("pioneer_finetuned"),
        latest_analysis.get("pioneer"),
        latest_analysis.get("openai"),
        label="Symptom",
    )
    medications = _merge_entities(
        latest_analysis.get("pioneer_finetuned"),
        latest_analysis.get("pioneer"),
        latest_analysis.get("openai"),
        label="Medication",
    )
    durations = _merge_entities(
        latest_analysis.get("pioneer_finetuned"),
        latest_analysis.get("pioneer"),
        latest_analysis.get("openai"),
        label="Duration",
    )
    histories = _merge_entities(
        latest_analysis.get("pioneer_finetuned"),
        latest_analysis.get("pioneer"),
        latest_analysis.get("openai"),
        label="Medical History",
    )

    parts = []
    if symptoms:
        parts.append(f"Symptoms: {', '.join(symptoms)}.")
    if durations:
        parts.append(f"Duration: {', '.join(durations)}.")
    if medications:
        parts.append(f"Medications mentioned: {', '.join(medications)}.")
    if histories:
        parts.append(f"History: {', '.join(histories)}.")
    if not parts and transcripts:
        parts.append(transcripts[-1][:220])
    return " ".join(parts) or "No clinical summary yet."


def _generate_follow_up_questions(session_id: str, analysis: dict) -> list[dict]:
    medications = _merge_entities(
        analysis.get("pioneer_finetuned"),
        analysis.get("pioneer"),
        analysis.get("openai"),
        label="Medication",
    )
    symptoms = _merge_entities(
        analysis.get("pioneer_finetuned"),
        analysis.get("pioneer"),
        analysis.get("openai"),
        label="Symptom",
    )
    dosages = _merge_entities(
        analysis.get("pioneer_finetuned"),
        analysis.get("pioneer"),
        analysis.get("openai"),
        label="Dosage",
    )
    frequencies = _merge_entities(
        analysis.get("pioneer_finetuned"),
        analysis.get("pioneer"),
        analysis.get("openai"),
        label="Frequency",
    )
    durations = _merge_entities(
        analysis.get("pioneer_finetuned"),
        analysis.get("pioneer"),
        analysis.get("openai"),
        label="Duration",
    )

    medication = medications[0] if medications else "the medication"
    symptom = symptoms[0] if symptoms else "the main symptom"
    questions = []

    if medications and (not dosages or not frequencies):
        questions.append(
            {
                "question": f"What dose of {medication} are you taking, and how often?",
                "reason": "Medication dosage or frequency is missing.",
                "priority": "high",
            }
        )
    if symptoms:
        questions.append(
            {
                "question": f"How severe is {symptom} from 1 to 10?",
                "reason": "Severity helps triage urgency and response.",
                "priority": "high",
            }
        )
    if not durations:
        questions.append(
            {
                "question": f"When did {symptom} start, and has it changed over time?",
                "reason": "Symptom duration and progression are incomplete.",
                "priority": "medium",
            }
        )
    questions.append(
        {
            "question": "Any allergies, pregnancy, kidney disease, or other medication interactions?",
            "reason": "Safety context matters before interpreting medication use.",
            "priority": "high",
        }
    )
    questions.append(
        {
            "question": "Any associated symptoms such as fever, weakness, chest pain, fainting, or breathing trouble?",
            "reason": "Associated symptoms can reveal red flags.",
            "priority": "medium",
        }
    )

    saved_questions = []
    for item in questions[:5]:
        question = {
            "id": _id("question"),
            "session_id": session_id,
            "question": item["question"],
            "reason": item["reason"],
            "priority": item["priority"],
            "answered": False,
        }
        _STORE["follow_up_questions"][question["id"]] = question
        saved_questions.append(question)
    return saved_questions


@app.post("/triage", response_model=TriageResponse)
async def triage(request: TriageRequest) -> TriageResponse:
    transcript = request.text.strip()
    analysis = await _analyze_transcript(transcript)

    return TriageResponse(
        pioneer=ExtractionResult(
            entities=analysis["pioneer"].get("entities", {label: [] for label in MEDICAL_LABELS}),
            latency_ms=analysis["pioneer"].get("latency_ms", 0),
            provider=analysis["pioneer"].get("provider"),
        ),
        pioneer_finetuned=(
            ExtractionResult(
                entities=analysis["pioneer_finetuned"].get("entities", {label: [] for label in MEDICAL_LABELS}),
                latency_ms=analysis["pioneer_finetuned"].get("latency_ms", 0),
                provider=analysis["pioneer_finetuned"].get("provider"),
            )
            if analysis["pioneer_finetuned"]
            else None
        ),
        openai=ExtractionResult(
            entities=analysis["openai"].get("entities", {label: [] for label in MEDICAL_LABELS}),
            latency_ms=analysis["openai"].get("latency_ms", 0),
            provider=analysis["openai"].get("provider"),
        ),
        tavily_cards=[TavilyCard(**card) for card in analysis["tavily_cards"]],
        transcript=transcript,
        winner=analysis["winner"],
    )


@app.get("/workspace", response_model=WorkspaceResponse)
def workspace() -> WorkspaceResponse:
    patients = [_patient_response(patient) for patient in _STORE["patients"].values()]
    return WorkspaceResponse(doctor=DoctorResponse(**_STORE["doctor"]), patients=patients)


@app.get("/patients/{patient_id}", response_model=PatientResponse)
def get_patient(patient_id: str) -> PatientResponse:
    patient = _STORE["patients"].get(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return _patient_response(patient)


@app.post("/patients", response_model=PatientResponse)
def create_patient(request: CreatePatientRequest) -> PatientResponse:
    patient = {
        "id": _id("patient"),
        "name": request.name.strip(),
        "age": request.age,
        "sex": request.sex,
        "summary": request.summary,
    }
    _STORE["patients"][patient["id"]] = patient
    return _patient_response(patient)


@app.get("/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session(session_id: str) -> SessionDetailResponse:
    session = _STORE["sessions"].get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    recordings = [
        _recording_response(recording)
        for recording in _STORE["recordings"].values()
        if recording["session_id"] == session_id
    ]
    analyses = [
        _as_analysis_response(analysis)
        for analysis in _STORE["analyses"].values()
        if analysis["session_id"] == session_id
    ]
    questions = [
        _question_response(question)
        for question in _STORE["follow_up_questions"].values()
        if question["session_id"] == session_id
    ]

    recordings.sort(key=lambda item: item.created_at)
    return SessionDetailResponse(
        session=_session_response(session),
        recordings=recordings,
        analyses=analyses,
        follow_up_questions=questions,
    )


@app.post("/patients/{patient_id}/sessions", response_model=SessionDetailResponse)
def create_session(patient_id: str, request: CreateSessionRequest) -> SessionDetailResponse:
    if patient_id not in _STORE["patients"]:
        raise HTTPException(status_code=404, detail="Patient not found")

    session = {
        "id": _id("session"),
        "patient_id": patient_id,
        "title": request.title.strip(),
        "status": request.status,
        "summary": request.summary or "",
        "updated_at": _now(),
    }
    _STORE["sessions"][session["id"]] = session
    return get_session(session["id"])


@app.post("/sessions/{session_id}/recordings", response_model=CreateRecordingResponse)
async def create_recording(session_id: str, request: RecordingRequest) -> CreateRecordingResponse:
    session = _STORE["sessions"].get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    transcript = request.transcript.strip()
    analysis = await _analyze_transcript(transcript)

    recording = {
        "id": _id("recording"),
        "session_id": session_id,
        "transcript": transcript,
        "duration_seconds": max(request.duration_seconds, 0),
        "created_at": _now(),
    }
    _STORE["recordings"][recording["id"]] = recording

    saved_analysis = {
        "id": _id("analysis"),
        "session_id": session_id,
        **analysis,
    }
    _STORE["analyses"][saved_analysis["id"]] = saved_analysis

    for question_id in [
        question["id"]
        for question in _STORE["follow_up_questions"].values()
        if question["session_id"] == session_id
    ]:
        del _STORE["follow_up_questions"][question_id]
    follow_up_questions = _generate_follow_up_questions(session_id, analysis)

    session_summary = _build_session_summary(session_id, analysis)
    session["summary"] = session_summary
    session["updated_at"] = _now()

    return CreateRecordingResponse(
        recording=_recording_response(recording),
        analysis=_as_analysis_response(saved_analysis),
        session_summary=session_summary,
        follow_up_questions=[_question_response(question) for question in follow_up_questions],
    )


@app.patch("/follow-up-questions/{question_id}", response_model=FollowUpQuestionResponse)
def update_follow_up_question(
    question_id: str,
    request: UpdateFollowUpQuestionRequest,
) -> FollowUpQuestionResponse:
    question = _STORE["follow_up_questions"].get(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Follow-up question not found")
    question["answered"] = request.answered
    return _question_response(question)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
