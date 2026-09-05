# ClearLedger

> Evidence-first payment-to-bank settlement controller for Razorpay Buildathon Track 04.

ClearLedger traces merchant collections through payment capture, settlement components, and bank
cash. Deterministic integer arithmetic and invariant checks are authoritative; optional AI is
restricted to bounded analysis of unresolved evidence and can never verify a case.

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- pnpm 9+
- Docker 24+ with Docker Compose v2
- `uv` 0.11+

### One-Command Setup

```bash
make install
make db-up
make migrate
make generate-demo
make dev
```

Open [http://localhost:3000](http://localhost:3000), click **Load Demo Dataset**, then click
**Start Reconciliation**.

For a container-only startup:

```bash
docker compose up --build
```

If a default port is occupied, set `WEB_PORT`, `API_PORT`, or `DB_PORT`, for example:
`WEB_PORT=3200 API_PORT=18000 docker compose up --build`.

### Optional AI

AI is disabled by default and the full deterministic batch still completes. To exercise a live
OpenAI-compatible provider, copy `.env.example` to `.env` and configure `AI_ENABLED`,
`AI_PROVIDER`, `AI_MODEL`, and `AI_API_KEY`. Provider failures leave cases unresolved with a
visible warning; they never block deterministic results.

For Hugging Face Inference Providers, use `AI_PROVIDER=huggingface`,
`AI_MODEL=openai/gpt-oss-20b:novita`, and
`AI_BASE_URL=https://router.huggingface.co/v1`. A Hugging Face token with inference-provider
permission is supplied through `AI_API_KEY`; keep `AI_MAX_CASES_PER_RUN=1` while using monthly
free-tier credits.

For Groq, use `AI_PROVIDER=groq`, `AI_MODEL=openai/gpt-oss-20b`, and
`AI_BASE_URL=https://api.groq.com/openai/v1`. Set `AI_MAX_CASES_PER_RUN=1` on Groq's free tier;
the demo evidence packet is large enough that analyzing several cases back-to-back can exceed
the provider's tokens-per-minute limit. Production accounts can raise the cap without changing
the reconciliation pipeline.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for trust zones, data flow, persistence, and the
authoritative control boundary.

## Evaluation

```bash
make evaluate
make ablation
```

The engine receives source files and versioned policy only. The standalone evaluator loads hidden
ground truth after predictions have been written. Methodology and formulas are in
[docs/EVALUATION.md](docs/EVALUATION.md).

## Stress Test

```bash
make stress-test
```

This deterministically generates 1,000 throughput cases using seed `99999`, then records wall
time, records/second, cases/second, P50/P95 case latency, and approximate peak process memory.

## Full Verification

```bash
make doctor
make test-unit
make test
make verify-claims
```

`make doctor` verifies prerequisites and checks whether Docker is available. `make test-unit` runs 114 pure offline unit, property, evaluator, and generator tests in seconds without requiring a database. `make test` runs full Python and frontend tests. `make verify-claims` regenerates all measured reports, verifies seed reproducibility, and fails if a published acceptance threshold is not met.

## What ClearLedger Does

- Traces orders through payments, fees, taxes, refunds, disputes, settlements, and bank credits.
- Verifies every accepted match with exact integer-paise arithmetic.
- Answers settlement questions using a grounded, read-only Q&A agent based on immutable computed facts.
- Turns unresolved money into an actionable exception queue.
- Produces an honest cash position separated by confidence.
- Uses AI only for bounded interpretation, never for arithmetic or authorization.
- Preserves immutable raw rows, evidence, decisions, checksums, and audit history.

## What ClearLedger Does NOT Do

- Move money.
- Post journal entries.
- Trigger payouts, refunds, or ledger writes.
- Modify source financial systems.
- Use AI-generated confidence as proof of correctness.
- Hide malformed or unresolved source records.

## Claims Ledger

Every numeric claim is generated from repository code and checked by `make verify-claims`.

| Claim | Reproducible command |
|---|---|
| Cases and source records processed | `make evaluate` |
| Match precision, recall, F1, and false positives | `make evaluate` |
| Exact-ID versus full-engine contribution | `make ablation` |
| Throughput, latency, and memory | `make stress-test` |
| AI call count and provider-estimated cost | `make ablation` |
| Amount reconciled and cash confidence buckets | `make verify-claims` |
| Zero residual among reconciled cases | `make verify-claims` |
| Same seed, same checksums, same results | `make verify-claims` |

Measured outputs are written to `out/`, including `evaluation.md`, `ablation_report.md`,
`stress_report.md`, and `final_metrics.md`.

## Submission Documents

- [Detailed technical and product review — 5 September 2026](docs/REVIEW_2026-09-05.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Data dictionary](docs/DATA_DICTIONARY.md)
- [Evaluation methodology](docs/EVALUATION.md)
- [Security and threat model](docs/SECURITY.md)
- [Demo script and fallback](docs/DEMO_SCRIPT.md)

## Product Statement

ClearLedger is an evidence-first payment-to-bank settlement controller. It traces every captured
payment through settlement components and bank cash, proves every accepted match with exact
arithmetic, and exposes every unresolved rupee with its evidence, owner, and next action.

ClearLedger does not maximize the number of matches. It maximizes the amount of money that can be
safely, reproducibly, and transparently explained.
