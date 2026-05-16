# Pioneer-Med: Privacy-First Medical Triage AI

Real-time medical entity extraction benchmark comparing Pioneer GLiNER2 against
OpenAI GPT, with Tavily medication verification.

## Benchmark Results

Evaluated on 25 synthetic, privacy-safe patient transcripts.

| Metric | Pioneer GLiNER2 | OpenAI GPT-4o-mini |
|---|---:|---:|
| Avg Latency | 689ms | 2,225ms |
| Precision | 99.0% | 100.0% |
| Recall | 82.8% | 86.1% |
| F1 | 89.9% | 92.3% |
| Speed Advantage | 3.2x faster | baseline |

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

## Why Pioneer

Pioneer GLiNER2 performs adaptive, zero-shot entity extraction: we can define
medical labels like `Medication`, `Dosage`, `Duration`, and `Medical History`
at runtime without retraining. In our latest 25-sample benchmark it delivered
near-parity extraction quality while running 3.2x faster than GPT-4o-mini.
This is ideal for clinical workflows where the target schema changes quickly.

The privacy narrative is the core of Pioneer-Med: medical transcripts should
not need to be sent wholesale to large general-purpose LLMs when a specialized,
edge-ready extraction model can structure the same information faster.
