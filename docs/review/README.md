# Review evidence and reproductions

Start with the [integrated review](../REVIEW_2026-09-05.md). These artifacts record findings against baseline commit `36794ac3262c651a93da17a1fabf13449d2bee1e`; they are historical observations, not current release certification. Finding severity is consolidated in the integrated review; specialist reports sometimes assign a different urgency to the same issue.

The scripts are diagnostic reproductions, not passing regression tests. They print the current behavior, including failures of financial controls. After fixing a finding, convert the relevant example into a test asserting the corrected behavior. A script exiting zero means it ran, not that the product is correct.

From the repository root, prepare synthetic fixtures and dependencies:

```sh
uv sync --frozen
AI_ENABLED=false make generate-demo
```

Financial and evaluator probes do not need PostgreSQL or a provider:

```sh
AI_ENABLED=false PYTHONPATH=. uv run python docs/review/reproduce_financial_findings.py
AI_ENABLED=false PYTHONPATH=. uv run python docs/review/reproduce_cli_findings.py
```

Each creates its own temporary output directory. They reproduce identifier-dependent SLA decisions, incomplete financial proof, evaluator amount blindness, duplicate/unknown predictions, the empty-report success gate and cash double deductions. The generated truth file is for scoring synthetic fixtures only; it is not a product input.

The API/concurrency probes require the repository's local demo PostgreSQL service (`make db-up`). They use the documented local demo credentials, create a uniquely named `review_<uuid>` schema, and remove only that schema in cleanup. They do not modify existing application tables. Run them against the local synthetic development service:

```sh
AI_ENABLED=false PYTHONPATH=. uv run python docs/review/reproduce_api_findings.py
AI_ENABLED=false PYTHONPATH=. uv run python docs/review/reproduce_concurrency_findings.py
```

These demonstrate run targeting, repeated/concurrent requests, review preservation, unsupported Q&A claims and concurrent aggregate drift. Model output is mocked; no provider call is made. Barriers deliberately arrange a possible concurrent transaction schedule without replacing the financial calculations.

Observed outputs are retained alongside the reports:

- `financial-reproduction-results.json`: financial and evaluator probes.
- `empty-evaluation-result.json` / `.md`: evaluator output for an intentionally invalid empty report. Its “pass” behavior is the defect being documented.
- `api-reproduction-results.jsonl`: API and mocked Q&A probes.
- `concurrency-reproduction-result.json`: both cases reconciled while cash/count projections lose an update.
- `benchmark-evaluation.json`, `benchmark-stress.json`, `benchmark-ablation.json`: the supplied benchmark, rerun with AI disabled. These retain the evaluator limitations described in the report.
- `validation-results.json`: aggregate check outcomes and scope.

The main review also covers source-inspected issues and separate cash-forecast probes. Not every recommendation has a standalone reproduction script, and passing these examples alone would not establish production readiness.
