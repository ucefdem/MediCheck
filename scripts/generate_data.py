"""Generate synthetic medical transcripts for benchmarking.

Usage:
    cd scripts
    ../backend/venv/bin/python generate_data.py --count 25

The script prefers OpenAI when OPENAI_API_KEY is configured, but falls back to
curated synthetic examples so the benchmark can always run.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
OUTPUT_PATH = BACKEND_DIR / "data" / "synthetic_dataset.json"

sys.path.append(str(BACKEND_DIR))

from dotenv import load_dotenv

load_dotenv(BACKEND_DIR / ".env")

LABELS = [
    "Symptom",
    "Medication",
    "Dosage",
    "Medical History",
    "Anatomical Site",
    "Duration",
    "Frequency",
]

CURATED_CASES = [
    {
        "transcript": "Um, I've had chest pain for three days, mostly on the left side. I take 50 milligrams of Lisinopril every morning and ibuprofen when it gets bad. I had bypass surgery in 2019.",
        "ground_truth": {
            "Symptom": ["chest pain"],
            "Medication": ["Lisinopril", "ibuprofen"],
            "Dosage": ["50 milligrams"],
            "Medical History": ["bypass surgery"],
            "Anatomical Site": ["left side"],
            "Duration": ["three days"],
            "Frequency": ["every morning"],
        },
    },
    {
        "transcript": "So I feel dizzy and nauseous after lunch, maybe for about two weeks. I'm on Metformin 500mg twice daily, and I had my gallbladder removed years ago.",
        "ground_truth": {
            "Symptom": ["dizzy", "nauseous"],
            "Medication": ["Metformin"],
            "Dosage": ["500mg"],
            "Medical History": ["gallbladder removed"],
            "Anatomical Site": [],
            "Duration": ["two weeks"],
            "Frequency": ["twice daily"],
        },
    },
    {
        "transcript": "I've been coughing all night and wheezing in my chest since Monday. I use Albuterol two puffs as needed, and I have asthma from childhood.",
        "ground_truth": {
            "Symptom": ["coughing", "wheezing"],
            "Medication": ["Albuterol"],
            "Dosage": ["two puffs"],
            "Medical History": ["asthma"],
            "Anatomical Site": ["chest"],
            "Duration": ["since Monday"],
            "Frequency": ["as needed"],
        },
    },
    {
        "transcript": "My right leg has been swollen for a week, and it hurts when I walk. I take Warfarin 5 mg nightly because I had a blood clot last year.",
        "ground_truth": {
            "Symptom": ["swollen", "hurts"],
            "Medication": ["Warfarin"],
            "Dosage": ["5 mg"],
            "Medical History": ["blood clot"],
            "Anatomical Site": ["right leg"],
            "Duration": ["a week", "last year"],
            "Frequency": ["nightly"],
        },
    },
    {
        "transcript": "I keep getting headaches and blurred vision in the morning. I take Atorvastatin 20mg daily and aspirin 81mg, and I had a stroke in 2020.",
        "ground_truth": {
            "Symptom": ["headaches", "blurred vision"],
            "Medication": ["Atorvastatin", "aspirin"],
            "Dosage": ["20mg", "81mg"],
            "Medical History": ["stroke"],
            "Anatomical Site": [],
            "Duration": [],
            "Frequency": ["daily", "in the morning"],
        },
    },
]

SYMPTOMS = [
    ("chest pressure", "chest"),
    ("shortness of breath", "chest"),
    ("sharp stomach pain", "stomach"),
    ("lower back pain", "back"),
    ("fever and chills", ""),
    ("dizziness", "head"),
    ("numbness in my left arm", "left arm"),
    ("bad headache", "head"),
]

MEDICATIONS = [
    ("Lisinopril", "10mg", "every morning"),
    ("Metformin", "500mg", "twice daily"),
    ("Warfarin", "5 mg", "nightly"),
    ("Ibuprofen", "400mg", "as needed"),
    ("Atorvastatin", "20mg", "daily"),
    ("Amoxicillin", "875mg", "twice daily"),
]

HISTORIES = [
    "bypass surgery in 2019",
    "asthma since childhood",
    "type 2 diabetes",
    "a stroke in 2020",
    "kidney disease",
    "appendix surgery years ago",
]


def empty_ground_truth() -> dict[str, list[str]]:
    return {label: [] for label in LABELS}


def configured(value: str | None) -> bool:
    return bool(value and value.strip() and "your_key_here" not in value)


def curated_dataset(count: int) -> list[dict]:
    dataset = []
    for index in range(count):
        if index < len(CURATED_CASES):
            item = CURATED_CASES[index]
        else:
            symptom_a, site_a = random.choice(SYMPTOMS)
            symptom_b, site_b = random.choice(SYMPTOMS)
            med_a, dose_a, freq_a = random.choice(MEDICATIONS)
            med_b, dose_b, freq_b = random.choice(MEDICATIONS)
            history = random.choice(HISTORIES)
            duration = random.choice(["three days", "about a week", "two months", "since yesterday"])
            transcript = (
                f"Uh, I guess I've had {symptom_a} and also {symptom_b} for {duration}. "
                f"I take {dose_a} of {med_a} {freq_a}, and sometimes {dose_b} {med_b} {freq_b}. "
                f"I should mention I had {history}."
            )
            item = {
                "transcript": transcript,
                "ground_truth": {
                    "Symptom": [symptom_a, symptom_b],
                    "Medication": [med_a, med_b],
                    "Dosage": [dose_a, dose_b],
                    "Medical History": [history],
                    "Anatomical Site": [site for site in [site_a, site_b] if site],
                    "Duration": [duration],
                    "Frequency": [freq_a, freq_b],
                },
            }
        dataset.append({"id": index + 1, **item})
    return dataset


async def openai_dataset(count: int) -> list[dict]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    prompt = f"""Generate {count} synthetic, privacy-safe patient transcripts.
Each transcript should be messy and conversational, with symptoms, medications,
dosages, medical history, body parts, durations, and frequencies when natural.

Return ONLY a JSON array. Each item must be:
{{
  "transcript": "...",
  "ground_truth": {{
    "Symptom": [],
    "Medication": [],
    "Dosage": [],
    "Medical History": [],
    "Anatomical Site": [],
    "Duration": [],
    "Frequency": []
  }}
}}
"""

    response = await client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.8,
    )
    content = response.choices[0].message.content or "{}"
    parsed = json.loads(content)
    items = parsed.get("items", parsed.get("dataset", parsed if isinstance(parsed, list) else []))
    dataset = []
    for index, item in enumerate(items[:count], start=1):
        ground_truth = empty_ground_truth()
        ground_truth.update(item.get("ground_truth", {}))
        dataset.append({"id": index, "transcript": item["transcript"], "ground_truth": ground_truth})
    return dataset


def save_dataset(dataset: list[dict]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as file:
        json.dump(dataset, file, indent=2)
        file.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=25)
    parser.add_argument("--no-openai", action="store_true")
    args = parser.parse_args()

    dataset = []
    if configured(os.getenv("OPENAI_API_KEY")) and not args.no_openai:
        try:
            import asyncio

            dataset = asyncio.run(openai_dataset(args.count))
        except Exception as exc:
            print(f"OpenAI generation failed, using curated fallback: {exc}")

    if not dataset:
        dataset = curated_dataset(args.count)

    save_dataset(dataset)
    print(f"Saved {len(dataset)} synthetic transcripts to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
