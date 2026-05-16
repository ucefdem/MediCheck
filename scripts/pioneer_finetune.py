"""Create a Pioneer synthetic NER dataset and start a GLiNER2 fine-tune.

This uses the documented Pioneer hosted flow:
1. POST /generate to create a labeled NER dataset.
2. Poll /generate/jobs/:id until ready.
3. POST /felix/training-jobs using fastino/gliner2-base-v1.
4. Poll /felix/training-jobs/:id until complete.

The resulting training job ID can be saved as PIONEER_FINETUNED_MODEL_ID.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
STATE_PATH = BACKEND_DIR / "data" / "pioneer_finetune_state.json"
API_BASE = "https://api.pioneer.ai"
MAX_GENERATE_EXAMPLES = 5000

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

DOMAIN_DESCRIPTION = (
    "Messy conversational medical triage transcripts. Patients mention symptoms, "
    "medications, dosages, durations, frequencies, anatomical sites, and past "
    "medical history such as surgery, diabetes, asthma, heart disease, or stroke. "
    "Transcripts should sound realistic, rambling, privacy-safe, and synthetic."
)


def api_key() -> str:
    key = os.getenv("PIONEER_API_KEY")
    if not key or "your_key_here" in key:
        raise RuntimeError("PIONEER_API_KEY is not configured in backend/.env")
    return key


def request(method: str, path: str, **kwargs) -> dict[str, Any]:
    response = requests.request(
        method,
        f"{API_BASE}{path}",
        headers={
            "X-API-Key": api_key(),
            "Content-Type": "application/json",
        },
        timeout=30,
        **kwargs,
    )
    try:
        body = response.json()
    except ValueError:
        body = {"text": response.text}
    if not response.ok:
        raise RuntimeError(f"{method} {path} failed ({response.status_code}): {body}")
    return body


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def load_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def start_generation(dataset_name: str, num_examples: int) -> dict[str, Any]:
    return request(
        "POST",
        "/generate",
        json={
            "task_type": "ner",
            "dataset_name": dataset_name,
            "labels": LABELS,
            "num_examples": num_examples,
            "domain_description": DOMAIN_DESCRIPTION,
        },
    )


def poll_generation(job_id: str, interval: int, timeout: int) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = request("GET", f"/generate/jobs/{job_id}")
        print(f"Generation status: {status.get('status')} count={status.get('count')}")
        if status.get("status") in {"ready", "failed"}:
            return status
        time.sleep(interval)
    raise TimeoutError(f"Generation job {job_id} did not finish within {timeout}s")


def chunk_requests(dataset_name: str, num_examples: int) -> list[dict[str, Any]]:
    if num_examples <= MAX_GENERATE_EXAMPLES:
        return [{"dataset_name": dataset_name, "num_examples": num_examples}]

    chunks = []
    remaining = num_examples
    index = 1
    while remaining > 0:
        chunk_size = min(remaining, MAX_GENERATE_EXAMPLES)
        chunks.append(
            {
                "dataset_name": f"{dataset_name}-part-{index}",
                "num_examples": chunk_size,
            }
        )
        remaining -= chunk_size
        index += 1
    return chunks


def start_training(dataset_names: list[str], model_name: str, epochs: int, learning_rate: float) -> dict[str, Any]:
    return request(
        "POST",
        "/felix/training-jobs",
        json={
            "model_name": model_name,
            "base_model": "fastino/gliner2-base-v1",
            "datasets": [{"name": dataset_name} for dataset_name in dataset_names],
            "training_type": "lora",
            "nr_epochs": epochs,
            "learning_rate": learning_rate,
        },
    )


def poll_training(job_id: str, interval: int, timeout: int) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = request("GET", f"/felix/training-jobs/{job_id}")
        print(f"Training status: {status.get('status')} metrics={status.get('metrics')}")
        if status.get("status") in {"complete", "failed", "cancelled", "deployed"}:
            return status
        time.sleep(interval)
    raise TimeoutError(f"Training job {job_id} did not finish within {timeout}s")


def main() -> None:
    global STATE_PATH

    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-name", default=f"pioneer-med-ner-{datetime.utcnow().strftime('%Y%m%d%H%M')}")
    parser.add_argument("--model-name", default="pioneer-med-finetuned-gliner2")
    parser.add_argument("--num-examples", type=int, default=60)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--learning-rate", type=float, default=5e-5)
    parser.add_argument("--poll", action="store_true", help="Poll generation and training until terminal status.")
    parser.add_argument("--interval", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument(
        "--state-path",
        type=Path,
        default=STATE_PATH,
        help="Where to store generation/training job state.",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore any existing state file and start a new generation/training flow.",
    )
    args = parser.parse_args()

    STATE_PATH = args.state_path if args.state_path.is_absolute() else ROOT / args.state_path

    state = {} if args.fresh else load_state()
    existing_dataset = state.get("dataset_name")
    if existing_dataset and existing_dataset != args.dataset_name and state.get("generation_job_id"):
        raise RuntimeError(
            f"State file {STATE_PATH} already tracks dataset {existing_dataset!r}. "
            "Use --fresh or a different --state-path for a new dataset."
        )

    state.update(
        {
            "dataset_name": args.dataset_name,
            "model_name": args.model_name,
            "num_examples": args.num_examples,
            "epochs": args.epochs,
            "learning_rate": args.learning_rate,
            "generation_chunks": chunk_requests(args.dataset_name, args.num_examples),
            "labels": LABELS,
            "base_model": "fastino/gliner2-base-v1",
        }
    )

    chunks = state["generation_chunks"]
    if not state.get("generation_jobs"):
        state["generation_jobs"] = []
        for chunk in chunks:
            generation = start_generation(chunk["dataset_name"], chunk["num_examples"])
            job_id = generation.get("job_id") or generation.get("id")
            state["generation_jobs"].append(
                {
                    "dataset_name": chunk["dataset_name"],
                    "num_examples": chunk["num_examples"],
                    "job_id": job_id,
                    "generation": generation,
                }
            )
            save_state(state)
            print(f"Started generation job: {job_id} for {chunk['dataset_name']}")

        if len(state["generation_jobs"]) == 1:
            state["generation"] = state["generation_jobs"][0]["generation"]
            state["generation_job_id"] = state["generation_jobs"][0]["job_id"]
            save_state(state)

    generation_ready = False
    if args.poll and state.get("generation_jobs"):
        generation_statuses = []
        for generation_job in state["generation_jobs"]:
            generation_status = poll_generation(generation_job["job_id"], args.interval, args.timeout)
            generation_statuses.append(
                {
                    "dataset_name": generation_job["dataset_name"],
                    "job_id": generation_job["job_id"],
                    "status": generation_status,
                }
            )
            state["generation_statuses"] = generation_statuses
            if len(generation_statuses) == 1:
                state["generation_status"] = generation_status
            save_state(state)
            if generation_status.get("status") != "ready":
                raise RuntimeError(f"Generation did not finish ready: {generation_status}")
        generation_ready = True
    else:
        generation_ready = all(
            item.get("status", {}).get("status") == "ready"
            for item in state.get("generation_statuses", [])
        )

    if not generation_ready:
        print("Dataset generation is not ready yet. Re-run with --poll to continue to training.")
        print(f"State saved to {STATE_PATH}")
        return

    if not state.get("training_job_id"):
        dataset_names = [chunk["dataset_name"] for chunk in chunks]
        training = start_training(dataset_names, args.model_name, args.epochs, args.learning_rate)
        state["training"] = training
        state["training_job_id"] = training.get("id") or training.get("job_id")
        save_state(state)
        print(f"Started training job: {state['training_job_id']}")

    if args.poll and state.get("training_job_id"):
        training_status = poll_training(state["training_job_id"], args.interval, args.timeout)
        state["training_status"] = training_status
        save_state(state)
        if training_status.get("status") not in {"complete", "deployed"} and training_status.get("normalized_status") != "complete":
            raise RuntimeError(f"Training did not complete: {training_status}")

    print("\nNext step:")
    print(f"Set PIONEER_FINETUNED_MODEL_ID={state.get('training_job_id')} in backend/.env")
    print(f"State saved to {STATE_PATH}")


if __name__ == "__main__":
    main()
