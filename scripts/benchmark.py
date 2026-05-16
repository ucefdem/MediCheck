"""Benchmark Pioneer GLiNER2 against OpenAI extraction.

Usage:
    cd scripts
    ../backend/venv/bin/python benchmark.py
"""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
DATASET_PATH = BACKEND_DIR / "data" / "synthetic_dataset.json"
RESULTS_PATH = ROOT / "benchmark_results.json"

sys.path.append(str(BACKEND_DIR))

import openai_service
import pioneer_service


def normalize(value: str) -> str:
    return " ".join(value.lower().replace("-", " ").split()).strip(" .,;:!?")


def flatten(entities: dict[str, list[str]]) -> set[str]:
    values = set()
    for items in entities.values():
        for item in items:
            cleaned = normalize(str(item))
            if cleaned:
                values.add(cleaned)
    return values


def score(predicted: dict[str, list[str]], ground_truth: dict[str, list[str]]) -> dict[str, float]:
    pred = flatten(predicted)
    truth = flatten(ground_truth)

    if not pred and not truth:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}

    correct_predictions = set()
    matched_truth = set()
    for pred_item in pred:
        for truth_item in truth:
            if pred_item in truth_item or truth_item in pred_item:
                correct_predictions.add(pred_item)
                matched_truth.add(truth_item)
                break

    precision = len(correct_predictions) / len(pred) if pred else 0.0
    recall = len(matched_truth) / len(truth) if truth else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def average(items: list[float]) -> float:
    return statistics.mean(items) if items else 0.0


def most_common_provider(rows: list[dict], key: str) -> str:
    providers = [row[key]["provider"] for row in rows if row[key].get("provider")]
    return Counter(providers).most_common(1)[0][0] if providers else ""


async def run_benchmark() -> dict:
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Dataset missing: {DATASET_PATH}. Run generate_data.py first.")

    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    rows = []

    for item in dataset:
        transcript = item["transcript"]
        ground_truth = item.get("ground_truth", {})
        pioneer_result, openai_result = await asyncio.gather(
            asyncio.to_thread(pioneer_service.extract_entities, transcript),
            openai_service.extract_entities(transcript),
        )

        pioneer_score = score(pioneer_result["entities"], ground_truth)
        openai_score = score(openai_result["entities"], ground_truth)

        rows.append(
            {
                "id": item["id"],
                "pioneer": {
                    "latency_ms": pioneer_result["latency_ms"],
                    "provider": pioneer_result.get("provider", ""),
                    **pioneer_score,
                },
                "openai": {
                    "latency_ms": openai_result["latency_ms"],
                    "provider": openai_result.get("provider", ""),
                    **openai_score,
                },
            }
        )
        print(
            f"{item['id']:>2}/{len(dataset)} "
            f"Pioneer {pioneer_result['latency_ms']:>5}ms "
            f"OpenAI {openai_result['latency_ms']:>5}ms"
        )

    summary = {
        "n_samples": len(rows),
        "pioneer": {
            "avg_latency_ms": round(average([row["pioneer"]["latency_ms"] for row in rows])),
            "precision": round(average([row["pioneer"]["precision"] for row in rows]) * 100, 1),
            "recall": round(average([row["pioneer"]["recall"] for row in rows]) * 100, 1),
            "f1": round(average([row["pioneer"]["f1"] for row in rows]) * 100, 1),
            "provider": most_common_provider(rows, "pioneer"),
        },
        "openai": {
            "avg_latency_ms": round(average([row["openai"]["latency_ms"] for row in rows])),
            "precision": round(average([row["openai"]["precision"] for row in rows]) * 100, 1),
            "recall": round(average([row["openai"]["recall"] for row in rows]) * 100, 1),
            "f1": round(average([row["openai"]["f1"] for row in rows]) * 100, 1),
            "provider": most_common_provider(rows, "openai"),
        },
        "rows": rows,
    }

    RESULTS_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def print_summary(summary: dict) -> None:
    pioneer = summary["pioneer"]
    openai = summary["openai"]
    speedup = openai["avg_latency_ms"] / pioneer["avg_latency_ms"] if pioneer["avg_latency_ms"] else 0

    print("\nBenchmark Results")
    print("=" * 72)
    print(f"{'Metric':<22}{'Pioneer GLiNER2':>22}{'OpenAI GPT':>22}")
    print("-" * 72)
    print(f"{'Avg Latency':<22}{pioneer['avg_latency_ms']:>21}ms{openai['avg_latency_ms']:>21}ms")
    print(f"{'Precision':<22}{pioneer['precision']:>21.1f}%{openai['precision']:>21.1f}%")
    print(f"{'Recall':<22}{pioneer['recall']:>21.1f}%{openai['recall']:>21.1f}%")
    print(f"{'F1':<22}{pioneer['f1']:>21.1f}%{openai['f1']:>21.1f}%")
    print("=" * 72)
    print(f"Speed advantage: Pioneer is {speedup:.1f}x faster")
    print(f"Saved detailed results to {RESULTS_PATH}")


if __name__ == "__main__":
    print_summary(asyncio.run(run_benchmark()))
