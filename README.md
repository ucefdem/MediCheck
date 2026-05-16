# MediCheck: Privacy-First Medical Triage AI

Real-time medical entity extraction benchmark comparing Pioneer GLiNER2 against
OpenAI GPT, with Tavily medication verification.

## Benchmark Results

Evaluated on 25 synthetic, privacy-safe patient transcripts.

| Metric | Pioneer Zero-shot | Pioneer Fine-tuned | OpenAI GPT-4o-mini |
|---|---:|---:|---:|
| Avg Latency | 1,136ms | 1,080ms | 2,776ms |
| Precision | 98.9% | 97.7% | 100.0% |
| Recall | 78.8% | 84.2% | 85.6% |
| F1 | 87.4% | 90.2% | 92.1% |
| Replacement Claim | 2.4x faster than GPT | 2.6x faster than GPT | baseline |

The active fine-tuned GLiNER2 model was trained on a larger Pioneer-generated
synthetic NER dataset for medical triage labels. The recommended run requested
1,000 examples and produced 946 usable labeled examples for LoRA training.
It is fast enough to replace the
general-purpose GPT extraction call in the product flow while keeping the same
structured schema.

We also completed a larger 10,000-request training run, split into two Pioneer
generation jobs because the API caps a single generation request at 5,000
examples. Pioneer produced 9,403 usable labeled examples, and the resulting
model is saved as `5ed1fb7c-17a6-443f-b3ca-dc0acc507735`. Its benchmark is
preserved in `benchmark_finetuned_10000_results.json`; for the live demo we keep
the faster 1,000-request model active because it gives nearly the same quality
with lower latency.

## Backend Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `backend/.env`:

```env
OPENAI_API_KEY=your_key_here
TAVILY_API_KEY=your_key_here
PIONEER_API_KEY=your_key_here
PIONEER_FINETUNED_MODEL_ID=optional_training_job_id
GRADIUM_API_KEY=your_key_here
```

Run the backend:

```bash
uvicorn main:app --port 8000
```

Open FastAPI docs:

```txt
http://127.0.0.1:8000/docs
```

## Frontend Setup

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev -- --port 3000
```

Open the dashboard:

```txt
http://localhost:3000
```

The frontend calls `NEXT_PUBLIC_BACKEND_URL`, which defaults to
`http://localhost:8000`. Voice input streams microphone audio through the
backend Gradium proxy at `/gradium/stt`, keeping `GRADIUM_API_KEY` server-side.

## API Test

```bash
curl -X POST http://127.0.0.1:8000/triage \
  -H "Content-Type: application/json" \
  -d '{"text":"Um, hi doctor, I have chest pain for three days on the left side. I take 50 milligrams of Lisinopril every morning and sometimes ibuprofen. I had bypass surgery in 2019."}'
```

## Benchmark

Generate synthetic data:

```bash
cd scripts
../backend/venv/bin/python generate_data.py --count 25
```

Run the benchmark:

```bash
../backend/venv/bin/python benchmark.py
```

The benchmark writes `benchmark_results.json`.

## Pioneer Fine-Tuning

Export the local synthetic dataset into GLiNER-style JSONL:

```bash
python scripts/export_pioneer_training_data.py
```

Start the hosted Pioneer synthetic dataset and GLiNER2 LoRA fine-tune:

```bash
python scripts/pioneer_finetune.py \
  --dataset-name pioneer-med-ner-1000 \
  --model-name pioneer-med-medical-gliner2-1000 \
  --num-examples 1000 \
  --epochs 3 \
  --state-path backend/data/pioneer_finetune_1000_state.json \
  --fresh \
  --poll
```

The completed training job ID is the fine-tuned model ID. Add it to
`backend/.env`:

```env
PIONEER_FINETUNED_MODEL_ID=6695fcbc-8158-469f-9585-09c7c8925fbb
```

Run the three-way replacement benchmark:

```bash
cd scripts
../backend/venv/bin/python benchmark_finetuned.py
```

This writes `benchmark_finetuned_results.json`.

## Why Pioneer

Pioneer GLiNER2 performs adaptive, zero-shot entity extraction: we can define
medical labels like `Medication`, `Dosage`, `Duration`, and `Medical History`
at runtime without retraining. In our latest 25-sample benchmark it delivered
near-parity extraction quality while running 2.6x faster than GPT-4o-mini.
This is ideal for clinical workflows where the target schema changes quickly.

For the Fastino/Pioneer prize track, MediCheck also includes a completed
fine-tuning path: synthetic NER data generation on Pioneer, a LoRA fine-tuned
GLiNER2 medical extraction model, and evaluation against GPT-4o-mini. The
fine-tuned model replaces the frontier LLM extraction call for the narrow
clinical structuring task.

The privacy narrative is the core of MediCheck: medical transcripts should
not need to be sent wholesale to large general-purpose LLMs when a specialized,
edge-ready extraction model can structure the same information faster.
