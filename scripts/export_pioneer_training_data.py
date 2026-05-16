"""Export synthetic transcripts into GLiNER/Pioneer-style labeled JSONL.

The API-hosted fine-tuning path can use Pioneer synthetic datasets directly,
but this export is useful for the README, dashboard upload, and proof that we
have a fine-tuning-ready medical NER dataset.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "backend" / "data" / "synthetic_dataset.json"
TRAIN_PATH = ROOT / "backend" / "data" / "pioneer_med_train.jsonl"
EVAL_PATH = ROOT / "backend" / "data" / "pioneer_med_eval.jsonl"


def find_span(text: str, value: str) -> tuple[int, int] | None:
    normalized_text = text.lower()
    normalized_value = value.lower().strip()
    start = normalized_text.find(normalized_value)
    if start == -1:
        return None
    return start, start + len(value)


def convert_item(item: dict) -> dict:
    text = item["transcript"]
    entities = []
    for label, values in item.get("ground_truth", {}).items():
        for value in values:
            span = find_span(text, str(value))
            if not span:
                continue
            start, end = span
            entities.append(
                {
                    "start": start,
                    "end": end,
                    "text": text[start:end],
                    "label": label,
                }
            )
    return {"id": item["id"], "text": text, "entities": entities}


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row) + "\n")


def main() -> None:
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    converted = [convert_item(item) for item in dataset]
    split = max(1, round(len(converted) * 0.8))
    train_rows = converted[:split]
    eval_rows = converted[split:]

    write_jsonl(TRAIN_PATH, train_rows)
    write_jsonl(EVAL_PATH, eval_rows)

    print(f"Exported {len(train_rows)} training examples to {TRAIN_PATH}")
    print(f"Exported {len(eval_rows)} eval examples to {EVAL_PATH}")


if __name__ == "__main__":
    main()
