"""Tavily medication verification service."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

KNOWN_DRUGS = {
    "lisinopril": {
        "indication": "ACE inhibitor commonly used for high blood pressure and heart failure.",
        "contraindications": "Monitor potassium, kidney function, pregnancy risk, and low blood pressure.",
    },
    "ibuprofen": {
        "indication": "NSAID used for pain, fever, and inflammation.",
        "contraindications": "Use caution with kidney disease, anticoagulants, stomach ulcers, and some cardiac histories.",
    },
    "metformin": {
        "indication": "Medication used to help control blood sugar in type 2 diabetes.",
        "contraindications": "Use caution with significant kidney disease or risk of lactic acidosis.",
    },
    "warfarin": {
        "indication": "Anticoagulant used to prevent or treat harmful blood clots.",
        "contraindications": "High interaction and bleeding risk; INR monitoring is required.",
    },
}

KNOWN_MISMATCHES = {
    "lisinopril": {
        "treats": ["hypertension", "blood pressure", "heart failure"],
        "not_for": ["headache", "fever", "cold", "flu"],
    },
    "metformin": {
        "treats": ["diabetes", "blood sugar", "glucose"],
        "not_for": ["pain", "headache", "fever", "infection"],
    },
    "warfarin": {
        "treats": ["blood clots", "atrial fibrillation"],
        "not_for": ["headache", "pain", "fever"],
    },
}


async def search_drug(drug_name: str) -> dict[str, str]:
    """Search Tavily for drug information, with local fallback cards."""
    fallback = KNOWN_DRUGS.get(
        drug_name.lower(),
        {
            "indication": "No local medication summary is available.",
            "contraindications": "",
        },
    )

    if not TAVILY_API_KEY:
        return {
            "drug": drug_name,
            "indication": fallback["indication"],
            "contraindications": fallback["contraindications"],
            "source": "",
        }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": TAVILY_API_KEY,
                    "query": (
                        f"What is {drug_name} used for? Include primary "
                        "indications and key contraindications."
                    ),
                    "search_depth": "basic",
                    "max_results": 3,
                    "include_answer": True,
                },
            )
            response.raise_for_status()
    except Exception:
        return {
            "drug": drug_name,
            "indication": fallback["indication"],
            "contraindications": fallback["contraindications"],
            "source": "",
        }

    data: dict[str, Any] = response.json()
    results = data.get("results", [])
    answer = str(data.get("answer") or "").strip()
    content = answer or (str(results[0].get("content", "")).strip() if results else "")
    source = str(results[0].get("url", "")) if results else ""

    return {
        "drug": drug_name,
        "indication": content[:220] or fallback["indication"],
        "contraindications": fallback["contraindications"],
        "source": source,
    }


def detect_mismatch(
    drug: str, symptoms: list[str], medical_history: list[str] | None = None
) -> str | None:
    drug_lower = drug.lower()
    symptoms_lower = [symptom.lower() for symptom in symptoms]
    history_lower = [item.lower() for item in medical_history or []]

    if drug_lower == "ibuprofen" and any("bypass" in item for item in history_lower):
        return (
            "Ibuprofen may increase cardiovascular or kidney risk in some "
            "post-bypass patients. Verify this medication history with the patient."
        )

    if drug_lower not in KNOWN_MISMATCHES:
        return None

    rules = KNOWN_MISMATCHES[drug_lower]
    for symptom in symptoms_lower:
        for not_for in rules["not_for"]:
            if not_for in symptom:
                treats = ", ".join(rules["treats"][:2])
                return (
                    f"{drug} is typically used for {treats}, not {symptom}. "
                    "Verify this medication history with the patient."
                )
    return None


async def verify_medications(
    medications: list[str], symptoms: list[str], medical_history: list[str] | None = None
) -> list[dict[str, str | None]]:
    """Verify all medications concurrently."""

    async def process_one(drug: str) -> dict[str, str | None]:
        result = await search_drug(drug)
        return {
            "drug": drug,
            "indication": result["indication"],
            "contraindications": result["contraindications"],
            "warning": detect_mismatch(drug, symptoms, medical_history),
            "source": result["source"],
        }

    return list(await asyncio.gather(*(process_one(drug) for drug in medications)))
