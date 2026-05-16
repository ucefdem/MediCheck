"""Workspace persistence for MediCheck v1."""

from __future__ import annotations

import os
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

DEMO_DOCTOR_ID = "doctor_demo"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _configured(value: str | None) -> bool:
    return bool(value and value.strip() and "your_" not in value)


def _new_id() -> str:
    return str(uuid.uuid4())


def _seed_data() -> dict[str, list[dict[str, Any]]]:
    now = utc_now()
    return {
        "doctors": [
            {
                "id": DEMO_DOCTOR_ID,
                "name": "Dr. Youssef",
                "avatar_url": "/doctor-avatar.jpg",
                "created_at": now,
            }
        ],
        "patients": [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "doctor_id": DEMO_DOCTOR_ID,
                "name": "Amal Benali",
                "age": 42,
                "sex": "female",
                "summary": "Chest pain follow-up",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "doctor_id": DEMO_DOCTOR_ID,
                "name": "Karim Haddad",
                "age": 58,
                "sex": "male",
                "summary": "Diabetes medication review",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": "33333333-3333-3333-3333-333333333333",
                "doctor_id": DEMO_DOCTOR_ID,
                "name": "Nora Mansour",
                "age": 35,
                "sex": "female",
                "summary": "Migraine and pain medication intake",
                "created_at": now,
                "updated_at": now,
            },
        ],
        "sessions": [
            {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "patient_id": "11111111-1111-1111-1111-111111111111",
                "title": "Chest pain intake",
                "status": "active",
                "summary": "Awaiting first recording.",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "patient_id": "22222222-2222-2222-2222-222222222222",
                "title": "Medication review",
                "status": "active",
                "summary": "Awaiting first recording.",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                "patient_id": "33333333-3333-3333-3333-333333333333",
                "title": "Migraine intake",
                "status": "active",
                "summary": "Awaiting first recording.",
                "created_at": now,
                "updated_at": now,
            },
        ],
        "recordings": [],
        "analyses": [],
        "follow_up_questions": [],
    }


class InMemoryWorkspaceStore:
    def __init__(self) -> None:
        self.data = _seed_data()

    def workspace(self) -> dict[str, Any]:
        doctor = deepcopy(self.data["doctors"][0])
        patients = []
        for patient in self.data["patients"]:
            sessions = [
                deepcopy(session)
                for session in self.data["sessions"]
                if session["patient_id"] == patient["id"]
            ]
            sessions.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
            patients.append({**deepcopy(patient), "sessions": sessions})
        patients.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return {"doctor": doctor, "patients": patients}

    def patient(self, patient_id: str) -> dict[str, Any] | None:
        for patient in self.workspace()["patients"]:
            if patient["id"] == patient_id:
                return patient
        return None

    def session_detail(self, session_id: str) -> dict[str, Any] | None:
        session = self._find("sessions", session_id)
        if not session:
            return None
        recordings = self._by_field("recordings", "session_id", session_id)
        analyses = self._by_field("analyses", "session_id", session_id)
        questions = self._by_field("follow_up_questions", "session_id", session_id)
        return {
            "session": deepcopy(session),
            "recordings": recordings,
            "analyses": analyses,
            "follow_up_questions": questions,
        }

    def create_patient(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        patient = {
            "id": _new_id(),
            "doctor_id": payload.get("doctor_id", DEMO_DOCTOR_ID),
            "name": payload["name"],
            "age": payload.get("age"),
            "sex": payload.get("sex"),
            "summary": payload.get("summary", ""),
            "created_at": now,
            "updated_at": now,
        }
        self.data["patients"].append(patient)
        return deepcopy(patient)

    def create_session(self, patient_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        session = {
            "id": _new_id(),
            "patient_id": patient_id,
            "title": payload["title"],
            "status": payload.get("status", "active"),
            "summary": payload.get("summary", "Awaiting first recording."),
            "created_at": now,
            "updated_at": now,
        }
        self.data["sessions"].append(session)
        self._touch_patient(patient_id)
        return deepcopy(session)

    def create_recording(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        recording = {
            "id": _new_id(),
            "session_id": session_id,
            "transcript": payload["transcript"],
            "duration_seconds": payload.get("duration_seconds", 0),
            "created_at": utc_now(),
        }
        self.data["recordings"].append(recording)
        self._touch_session(session_id)
        return deepcopy(recording)

    def create_analysis(self, payload: dict[str, Any]) -> dict[str, Any]:
        analysis = {"id": _new_id(), "created_at": utc_now(), **payload}
        self.data["analyses"].append(analysis)
        return deepcopy(analysis)

    def replace_follow_up_questions(
        self,
        session_id: str,
        recording_id: str,
        questions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        self.data["follow_up_questions"] = [
            question
            for question in self.data["follow_up_questions"]
            if question["session_id"] != session_id
        ]
        created = []
        for question in questions:
            row = {
                "id": _new_id(),
                "session_id": session_id,
                "recording_id": recording_id,
                "question": question["question"],
                "reason": question.get("reason", ""),
                "priority": question.get("priority", "medium"),
                "answered": question.get("answered", False),
                "created_at": utc_now(),
            }
            self.data["follow_up_questions"].append(row)
            created.append(deepcopy(row))
        return created

    def update_question(self, question_id: str, answered: bool) -> dict[str, Any] | None:
        question = self._find("follow_up_questions", question_id)
        if not question:
            return None
        question["answered"] = answered
        return deepcopy(question)

    def update_session_summary(self, session_id: str, summary: str) -> dict[str, Any] | None:
        session = self._find("sessions", session_id)
        if not session:
            return None
        session["summary"] = summary
        self._touch_session(session_id)
        return deepcopy(session)

    def _find(self, table: str, row_id: str) -> dict[str, Any] | None:
        return next((row for row in self.data[table] if row["id"] == row_id), None)

    def _by_field(self, table: str, field: str, value: str) -> list[dict[str, Any]]:
        rows = [deepcopy(row) for row in self.data[table] if row[field] == value]
        rows.sort(key=lambda item: item.get("created_at", ""))
        return rows

    def _touch_patient(self, patient_id: str) -> None:
        patient = self._find("patients", patient_id)
        if patient:
            patient["updated_at"] = utc_now()

    def _touch_session(self, session_id: str) -> None:
        session = self._find("sessions", session_id)
        if session:
            session["updated_at"] = utc_now()
            self._touch_patient(session["patient_id"])


class SupabaseWorkspaceStore:
    def __init__(self, url: str, service_role_key: str) -> None:
        cleaned_url = url.rstrip("/")
        self.base_url = cleaned_url if cleaned_url.endswith("/rest/v1") else f"{cleaned_url}/rest/v1"
        self.headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
        }

    def workspace(self) -> dict[str, Any]:
        doctor = self._select_one("doctors", {"id": f"eq.{DEMO_DOCTOR_ID}"})
        patients = self._select("patients", {"doctor_id": f"eq.{DEMO_DOCTOR_ID}", "order": "updated_at.desc"})
        for patient in patients:
            patient["sessions"] = self._select(
                "sessions",
                {"patient_id": f"eq.{patient['id']}", "order": "updated_at.desc"},
            )
        return {"doctor": doctor, "patients": patients}

    def patient(self, patient_id: str) -> dict[str, Any] | None:
        patient = self._select_one("patients", {"id": f"eq.{patient_id}"})
        if not patient:
            return None
        patient["sessions"] = self._select(
            "sessions",
            {"patient_id": f"eq.{patient_id}", "order": "updated_at.desc"},
        )
        return patient

    def session_detail(self, session_id: str) -> dict[str, Any] | None:
        session = self._select_one("sessions", {"id": f"eq.{session_id}"})
        if not session:
            return None
        return {
            "session": session,
            "recordings": self._select("recordings", {"session_id": f"eq.{session_id}", "order": "created_at.asc"}),
            "analyses": self._select("analyses", {"session_id": f"eq.{session_id}", "order": "created_at.asc"}),
            "follow_up_questions": self._select(
                "follow_up_questions",
                {"session_id": f"eq.{session_id}", "order": "created_at.asc"},
            ),
        }

    def create_patient(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._insert("patients", {**payload, "doctor_id": payload.get("doctor_id", DEMO_DOCTOR_ID)})

    def create_session(self, patient_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._insert("sessions", {**payload, "patient_id": patient_id})

    def create_recording(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._insert("recordings", {**payload, "session_id": session_id})

    def create_analysis(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._insert("analyses", payload)

    def replace_follow_up_questions(
        self,
        session_id: str,
        recording_id: str,
        questions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        self._delete("follow_up_questions", {"session_id": f"eq.{session_id}"})
        return [
            self._insert(
                "follow_up_questions",
                {
                    "session_id": session_id,
                    "recording_id": recording_id,
                    "question": question["question"],
                    "reason": question.get("reason", ""),
                    "priority": question.get("priority", "medium"),
                    "answered": question.get("answered", False),
                },
            )
            for question in questions
        ]

    def update_question(self, question_id: str, answered: bool) -> dict[str, Any] | None:
        return self._patch("follow_up_questions", {"id": f"eq.{question_id}"}, {"answered": answered})

    def update_session_summary(self, session_id: str, summary: str) -> dict[str, Any] | None:
        return self._patch(
            "sessions",
            {"id": f"eq.{session_id}"},
            {"summary": summary, "updated_at": utc_now()},
        )

    def _request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        prefer: str | None = None,
    ) -> list[dict[str, Any]]:
        headers = dict(self.headers)
        if prefer:
            headers["Prefer"] = prefer
        with httpx.Client(timeout=12.0) as client:
            response = client.request(
                method,
                f"{self.base_url}/{table}",
                params=params,
                json=json_body,
                headers=headers,
            )
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return []
            return response.json()

    def _select(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        return self._request("GET", table, params=params)

    def _select_one(self, table: str, params: dict[str, str]) -> dict[str, Any] | None:
        rows = self._select(table, {**params, "limit": "1"})
        return rows[0] if rows else None

    def _insert(self, table: str, payload: dict[str, Any]) -> dict[str, Any]:
        rows = self._request("POST", table, json_body=payload, prefer="return=representation")
        return rows[0]

    def _patch(
        self,
        table: str,
        params: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        rows = self._request("PATCH", table, params=params, json_body=payload, prefer="return=representation")
        return rows[0] if rows else None

    def _delete(self, table: str, params: dict[str, str]) -> None:
        self._request("DELETE", table, params=params)


_store: InMemoryWorkspaceStore | SupabaseWorkspaceStore | None = None


def get_store() -> InMemoryWorkspaceStore | SupabaseWorkspaceStore:
    global _store
    if _store is not None:
        return _store

    supabase_url = os.getenv("SUPABASE_URL")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if _configured(supabase_url) and _configured(service_role_key):
        _store = SupabaseWorkspaceStore(supabase_url or "", service_role_key or "")
    else:
        _store = InMemoryWorkspaceStore()
    return _store
