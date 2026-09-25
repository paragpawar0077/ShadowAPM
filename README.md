# ShadowAPM
### AI-Driven Chaos Engineering & Reliability Platform
*Final Year Project (B.E. Computer Engineering) — SPPU, 2026–2027*

ShadowAPM lets a team break their own backend safely by asynchronously
mirroring real API traffic into an isolated sandbox, injecting controlled
faults there, detecting abnormal behaviour with machine learning, and
generating a human-verifiable, evidence-grounded root-cause explanation —
**without ever touching the production request path.**

This repository is a full, runnable implementation of the architecture
described in the Project Review-II feasibility document, built entirely on
free / open-source technology (no paid API keys or cloud accounts required
to run it locally).

## Architecture

```
                 ┌─────────────┐
   real traffic  │             │  1. forwards & returns immediately
 ───────────────▶│    proxy    │────────────────────────────▶  sample-api
                 │ (mirroring +│                                (production)
                 │ PII sanitise)│
                 └──────┬──────┘
                        │ 2. fire-and-forget, sanitised mirror
                        ▼
                 ┌─────────────┐        ┌───────────────┐
                 │ sandbox-api │◀───────│  chaos-engine │  (configure faults)
                 │ (fault      │        └───────────────┘
                 │  injection) │
                 └──────┬──────┘
                        │ telemetry
                        ▼
                 ┌─────────────┐   ┌──────────────────┐   ┌──────────┐
                 │ TimescaleDB │──▶│ anomaly-detector  │──▶│ rca-agent│──▶ dashboard
                 │ (telemetry) │   │ (Isolation Forest)│   │ (Ollama) │
                 └─────────────┘   └──────────────────┘   └──────────┘
```

| Component | Tech | Maps to requirement |
|---|---|---|
| `sample-api/` | FastAPI | The real production service (never touched by chaos) |
| `proxy/` | FastAPI + httpx | FR-01 traffic mirroring, NFR-01/02 latency & isolation |
| `common/pii.py` | Python | FR-02 PII sanitisation |
| `sandbox-api/` | FastAPI | FR-03 isolated fault injection |
| `chaos-engine/` | FastAPI | FR-03/FR-07 chaos experiment control plane |
| `common/db.py` + TimescaleDB | SQLAlchemy + Postgres | FR-04 telemetry capture |
| `anomaly-detector/` | Scikit-learn Isolation Forest | FR-05 ML anomaly detection |
| `rca-agent/` | Ollama (local LLM) + rule-based fallback | FR-06 LLM root-cause explanation |
| `dashboard/` | React + Vite + Recharts | FR-08 reliability dashboard |

## Quick start (Docker, recommended)

Requires only Docker Desktop / Docker Engine — everything else is pulled or
built automatically, all from free images.

<!-- ```bash
docker compose up --build
```

Then:
1. Open the dashboard: **http://localhost:5173**
2. Create a chaos experiment (e.g. "latency" on `/orders`) in the
   **Chaos Experiments** tab.
3. Send some traffic through the proxy (NOT directly to sample-api):
   ```bash
   curl -X POST http://localhost:8000/orders \
     -H "Content-Type: application/json" \
     -d '{"sku":"SKU-1","amount":499}'
   ```
   Run this a few dozen times (a simple `for` loop works) so there's enough
   data to train on.
4. In the **Reliability Overview** tab, click **Retrain & Score Now**.
5. Copy a `request_id` for a request flagged as an anomaly (check the
   `sandbox-api` container logs, or query the `telemetry_events` table) and
   paste it into the **RCA Reports** tab to generate a root-cause report.

### Optional: enable the local LLM for RCA
By default `rca-agent` tries to reach Ollama and, if it can't, automatically
falls back to a deterministic rule-based explanation — so the platform works
out of the box even without pulling a model. To enable the real LLM:
```bash
docker compose exec ollama ollama pull llama3.2:1b -->
```

<!-- ## Running without Docker (for development)

Each service is a plain FastAPI app. From the repo root:
```bash
pip install -r sample-api/requirements.txt   # repeat per service, or use a single venv
export PYTHONPATH=$(pwd)
export DATABASE_URL="sqlite:////tmp/shadowapm.db"   # or a local Postgres URL

uvicorn sample-api.app.main:app --app-dir . --port 9001
uvicorn sandbox-api.app.main:app --app-dir . --port 9002
uvicorn chaos-engine.app.main:app --app-dir . --port 9003
uvicorn anomaly-detector.app.detector:app --app-dir . --port 9004
uvicorn rca-agent.app.main:app --app-dir . --port 9005
PRODUCTION_URL=http://127.0.0.1:9001 SANDBOX_URL=http://127.0.0.1:9002 \
  uvicorn proxy.app.main:app --app-dir . --port 9000
```
For the dashboard:
```bash
cd dashboard
npm install
npm run dev
``` -->

## Cost — this build is free-tier only

| Component | Cost |
|---|---|
| Docker, FastAPI, React, Scikit-learn | Free / open-source |
| PostgreSQL + TimescaleDB (self-hosted via Docker) | Free |
| Ollama (local LLM) | Free, runs on CPU |
| Hosted LLM API (e.g. Gemini) | **Not required** — only mentioned as an optional production alternative in the feasibility document |

No cloud account, API key, or paid service is needed to run or demo this
project end-to-end.

## Repository layout

```
shadowapm/
├── docker-compose.yml
├── common/            shared DB models + PII sanitiser, used by every service
├── sample-api/         production service (never receives chaos)
├── sandbox-api/        chaos-enabled replica
├── proxy/               traffic mirror + PII sanitiser + telemetry capture
├── chaos-engine/        experiment CRUD API
├── anomaly-detector/    Isolation Forest training/scoring API
├── rca-agent/            Ollama + rule-based RCA API
├── telemetry/            TimescaleDB init SQL
├── scripts/              hypertable setup helper
├── dashboard/            React + Vite frontend
└── docs/                 architecture & API reference
```

See `docs/ARCHITECTURE.md` and `docs/API.md` for details.
