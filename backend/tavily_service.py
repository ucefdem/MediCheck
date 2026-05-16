"""Tavily medication verification service."""

from __future__ import annotations

import asyncio
import os
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

TAVILY_URL = "https://api.tavily.com/search"

_FALLBACK_DRUGS = {
    "lisinopril": {
        "indication": "ACE inhibitor commonly used for hypertension and heart failure.",
        "contraindications": "Use caution with pregnancy, angioedema history, kidney impairment, and potassium-sparing drugs.",
        "source": "demo-fallback",
    },
    "ibuprofen": {
        "indication": "NSAID used for pain, fever, and inflammation.",
        "contraindications": "Use caution with kidney disease, bleeding risk, anticoagulants, heart disease, and some blood pressure medicines.",
        "source": "demo-fallback",
    },
    "metformin": {
        "indication": "Medication commonly used to manage type 2 diabetes.",
        "contraindications": "Use caution with severe kidney impairment or conditions increasing lactic acidosis risk.",
        "source": "demo-fallback",
    },
    "warfarin": {
        "indication": "Anticoagulant used to prevent or treat blood clots.",
        "contraindications": "High bleeding risk; many drug and food interactions require monitoring.",
        "source": "demo-fallback",
    },
}


def _configured(value: str | None) -> bool:
    return bool(value and value.strip() and "your_key_here" not in value)


def _fallback_card(drug_name: str) -> dict:
    known = _FALLBACK_DRUGS.get(drug_name.lower(), {})
    return {
        "drug": drug_name,
        "indication": known.get("indication", f"Medication safety context for {drug_name}."),
        "contraindications": known.get("contraindications", "Verify contraindications with a clinician or trusted medication database."),
        "source": known.get("source", "demo-fallback"),
    }


async def search_drug(drug_name: str) -> dict:
    api_key = os.getenv("TAVILY_API_KEY")
    if not _configured(api_key):
        return _fallback_card(drug_name)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                TAVILY_URL,
                json={
                    "api_key": api_key,
                    "query": f"What is {drug_name} used for? Include primary indications and common contraindications.",
                    "search_depth": "basic",
                    "max_results": 3,
                    "include_answer": True,
                },
            )
            response.raise_for_status()
    except Exception:
        return _fallback_card(drug_name)

    data = response.json()
    answer = (data.get("answer") or "").strip()
    results = data.get("results") or []
    first_result = results[0] if results else {}
    content = answer or (first_result.get("content") or "").strip()

    if not content:
        return _fallback_card(drug_name)

    return {
        "drug": drug_name,
        "indication": content[:220],
        "contraindications": "",
        "source": first_result.get("url", ""),
    }


def detect_mismatch(
    drug: str,
    symptoms: list[str],
    medical_history: Optional[list[str]] = None,
) -> Optional[str]:
    symptoms_lower = " ".join(symptoms).lower()
    history_lower = " ".join(medical_history or []).lower()
    context = f"{symptoms_lower} {history_lower}"
    drug_lower = drug.lower()

    if drug_lower == "lisinopril" and any(word in symptoms_lower for word in ["headache", "pain", "fever"]):
        return "Lisinopril is typically used for blood pressure or heart failure, not pain symptoms. Verify the patient history."

    if drug_lower == "ibuprofen" and any(word in context for word in ["chest pain", "heart", "bypass"]):
        return "Ibuprofen can be risky in some cardiovascular histories and may interact with blood pressure treatment. Review before use."

    if drug_lower == "warfarin" and any(word in symptoms_lower for word in ["bleeding", "bruise", "fall"]):
        return "Warfarin increases bleeding risk. Escalate medication reconciliation."

    return None


async def verify_medications(
    medications: list[str],
    symptoms: list[str],
    medical_history: Optional[list[str]] = None,
) -> list[dict]:
    async def process_one(drug: str) -> dict:
        card = await search_drug(drug)
        warning = detect_mismatch(drug, symptoms, medical_history)
        return {
            "drug": card.get("drug", drug),
            "indication": card.get("indication", ""),
            "contraindications": card.get("contraindications", ""),
            "warning": warning,
            "source": card.get("source", ""),
        }

    unique_medications = []
    seen = set()
    for medication in medications:
        key = medication.lower().strip()
        if key and key not in seen:
            unique_medications.append(medication.strip())
            seen.add(key)

    return list(await asyncio.gather(*(process_one(drug) for drug in unique_medications)))
