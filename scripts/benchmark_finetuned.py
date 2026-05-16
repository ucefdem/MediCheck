"""Benchmark OpenAI vs Pioneer zero-shot vs Pioneer fine-tuned GLiNER2."""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
DATASET_PATH = BACKEND_DIR / "data" / "synthetic_dataset.json"
RESULTS_PATH = ROOT / "benchmark_finetuned_results.json"

sys.path.append(str(BACKEND_DIR))

from dotenv import load_dotenv

load_dotenv(BACKEND_DIR / ".env")

import openai_service
import pioneer_service
from benchmark import score


def average(values: list[float]) -> float:
    return statistics.mean(values) if values else 0.0


async def run() -> dict:
    model_id = os.getenv("PIONEER_FINETUNED_MODEL_ID")
    if not model_id:
        raise RuntimeError("Set PIONEER_FINETUNED_MODEL_ID in backend/.env before running this benchmark.")

    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    rows = []

    for item in dataset:
        transcript = item["transcript"]
        truth = item.get("ground_truth", {})
        zero_shot, fine_tuned, openai = await asyncio.gather(
            asyncio.to_thread(pioneer_service.extract_entities, transcript),
            asyncio.to_thread(pioneer_service.extract_entities, transcript, model_id),
            openai_service.extract_entities(transcript),
        )
        rows.append(
            {
                "id": item["id"],
                "pioneer_zero_shot": {
                    "latency_ms": zero_shot["latency_ms"],
                    **score(zero_shot["entities"], truth),
                },
                "pioneer_finetuned": {
                    "latency_ms": fine_tuned["latency_ms"],
                    **score(fine_tuned["entities"], truth),
                },
                "openai": {
                    "latency_ms": openai["latency_ms"],
                    **score(openai["entities"], truth),
                },
            }
        )
        print(
            f"{item['id']:>2}/{len(dataset)} "
            f"zero={zero_shot['latency_ms']:>5}ms "
            f"ft={fine_tuned['latency_ms']:>5}ms "
            f"gpt={openai['latency_ms']:>5}ms"
        )

    summary = {"n_samples": len(rows), "model_id": model_id, "rows": rows}
    for key in ["pioneer_zero_shot", "pioneer_finetuned", "openai"]:
        summary[key] = {
            "avg_latency_ms": round(average([row[key]["latency_ms"] for row in rows])),
            "precision": round(average([row[key]["precision"] for row in rows]) * 100, 1),
            "recall": round(average([row[key]["recall"] for row in rows]) * 100, 1),
            "f1": round(average([row[key]["f1"] for row in rows]) * 100, 1),
        }

    RESULTS_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def print_summary(summary: dict) -> None:
    print("\nFine-tuned Replacement Benchmark")
    print("=" * 88)
    print(f"{'Metric':<20}{'Pioneer Zero-shot':>22}{'Pioneer Fine-tuned':>24}{'OpenAI GPT':>18}")
    print("-" * 88)
    for metric, suffix in [
        ("avg_latency_ms", "ms"),
        ("precision", "%"),
        ("recall", "%"),
        ("f1", "%"),
    ]:
        label = "Avg Latency" if metric == "avg_latency_ms" else metric.title()
        print(
            f"{label:<20}"
            f"{summary['pioneer_zero_shot'][metric]:>21}{suffix}"
            f"{summary['pioneer_finetuned'][metric]:>23}{suffix}"
            f"{summary['openai'][metric]:>17}{suffix}"
        )
    print("=" * 88)
    print(f"Saved {RESULTS_PATH}")


if __name__ == "__main__":
    print_summary(asyncio.run(run()))
