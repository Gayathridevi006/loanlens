# LoanLens

LoanLens is a local-first, full-stack agentic RAG system for loan intake, document investigation, fraud detection, and explainable decision support. FastAPI orchestrates specialist agents and deterministic scoring tools, React provides the officer workspace, and PostgreSQL with pgvector stores the evidence index. Recommendations remain advisory; an authorized loan officer owns the final lending decision.

## Capabilities

- CSV, Excel, JSON, text-PDF, and OCR image intake with document classification and field extraction
- Agent planner, hybrid retriever, document specialist, fraud investigator, compliance agent, answer writer, and grounding verifier
- Hybrid BM25 + 384-dimensional local embeddings, reciprocal-rank reranking, metadata filters, and pgvector HNSW search
- Page/section/source citations, policy retrieval, prompt-injection defence, and approval grounding guardrails
- Explainable credit risk, rule fraud, live Isolation Forest anomaly detection, and local sentiment scoring
- Required/expired/inconsistent document checks and versioned adverse-action reason codes
- Human decision overrides with recorded reasons, encrypted audit history, drift monitoring, and disparate-impact reports
- Scrypt password storage, signed JWT access tokens, optional authentication enforcement, and role checks
- Background document jobs, model registry, retention controls, and integration readiness endpoints
- Searchable and paginated application portfolio
- Dashboard, analytics, CSV reports, JSON logs, and Prometheus metrics
- Encrypted raw applicant payloads at rest
- RAG evaluation covering Hit/Recall@K, MRR, groundedness, citation accuracy, contradiction, hallucination, latency, and decision errors
- Alembic database migrations and CI verification

The Docker stack uses the `pgvector/pgvector:pg17` image. SQLite remains supported for local development and tests; it uses the same embeddings with an in-process cosine-search fallback.

## Docker Compose

The complete stack runs as four containers: the Nginx/React frontend, FastAPI backend, one-shot Alembic migration service, and PostgreSQL 17 with pgvector. Nginx serves the SPA and proxies `/api` to FastAPI, so the application has a single browser-facing origin.

```bash
cp .env.docker.example .env
# Fill DATA_ENCRYPTION_KEY, JWT_SECRET, POSTGRES_PASSWORD and optionally AUTH_BOOTSTRAP_SECRET.
docker compose up --build -d
docker compose ps
```

Open `http://localhost:3000`. Direct API documentation is bound to the local machine at `http://127.0.0.1:8000/docs`. PostgreSQL is isolated on an internal Docker network and persists in the `loanlens_postgres` named volume.

Useful operations:

```bash
docker compose logs -f backend frontend
docker compose run --rm migrate
docker compose down
# Explicitly removes the database volume as well:
docker compose down --volumes
```

For production, set `AUTH_REQUIRED=true`, use secrets from the deployment platform rather than committing `.env`, terminate TLS at the ingress/load balancer, and remove the backend host-port mapping if direct API access is unnecessary. The containers run with read-only filesystems, writable temporary memory only, non-root application users, health checks, and migration-gated startup.

## Local setup

Prerequisites: Python 3.12+, Node.js 22+, and npm.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
python -m alembic upgrade head
cd frontend && npm ci && cd ..
./run_loanlens.sh
```

Frontend: `http://localhost:5173`  
API docs: `http://localhost:8000/docs`  
Metrics: `http://localhost:8000/metrics`

For optional SHAP explanations after training a governed supervised model, install `backend/requirements-ml.txt`. Before production, set stable `DATA_ENCRYPTION_KEY` and `JWT_SECRET` values, turn on `AUTH_REQUIRED`, bootstrap the first administrator, and configure TLS at the ingress.

## Phase 2 model workflow

LoanLens does not invent labels or promote an unvalidated model. Prepare a governed dataset and train the calibrated baseline explicitly:

```bash
python models/prepare_governed_dataset.py --input labelled.csv --target approved --protected gender age_band
python models/train_credit_model.py --target approved
```

Protected attributes remain evaluation-only and are excluded from model features. The model registry reports the supervised model as blocked until this workflow produces an artifact. The explainability endpoint then exposes scorecard reasons beside SHAP attributions.

## Tests and evaluation

```bash
python -m pytest -q
cd frontend && npm run build
```

`POST /evaluation/backtest` accepts historical cases containing a query, evidence corpus, expected evidence IDs, required answer terms, and optional expected/actual decisions. It records:

- Hit and Recall at K
- Mean reciprocal rank
- Mean groundedness
- Citation accuracy, hallucination and contradiction rates
- Retrieval latency and decision-error rate
- Verification pass rate
- Decision accuracy

Failed retrieval or grounding cases are persisted in `evaluation_runs` for regression analysis. This evaluator is deterministic and intended as a baseline; semantic/LLM judging should be added only with a versioned dataset and human-reviewed rubric.

## Database migrations

Apply migrations with `python -m alembic upgrade head`. For an existing prototype database that was created before Alembic, back it up and use `alembic stamp 0001_initial` once before future upgrades.

## Security notes

Applicant payloads, evidence text, agent traces, overrides, and audit details are encrypted through application-level encrypted SQLAlchemy types. Logs contain request metadata rather than applicant content. Local username/password login issues signed JWTs; OIDC/SSO, credit-bureau verification, and an optional narrative-only LLM expose configuration adapters and remain disabled until credentials are supplied.

See [Phase 2 implementation coverage](docs/PHASE2_IMPLEMENTATION.md) for the requirement-by-requirement status and API map.
