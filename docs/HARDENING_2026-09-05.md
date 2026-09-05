# Hardening acceptance map — 5 September 2026

This document maps the 15 findings from the 5 September review to the behavior now present in
ClearLedger. “Implemented” means the control exists in code and has automated coverage. “Bounded”
means the stated hackathon/pilot control exists, while the listed production capability remains
outside the product claim.

| Priority | Review finding | Current implementation | Automated evidence and boundary |
|---|---|---|---|
| P1 | Rerun replaced cases and reset review/ownership | **Controlled; selective carry-forward remains.** A completed execution is frozen. Repeating reconcile replays its result without changing cases, ownership, decisions, or review revision. Reprocessing creates a linked `parent_run_id` successor with a higher execution revision. | `apps/api/tests/test_execution_integrity.py::test_completed_replay_preserves_review_and_successor_lineage`. Prior decisions remain on the immutable parent; a successor deliberately starts with no files and review revision zero. Selectively carrying still-valid assignments or decisions into a successor, with explicit revalidation, is not implemented. |
| P1 | Concurrent same-key run creation returned mixed 201/503 responses | **Implemented.** Idempotency is scoped by authenticated subject, route, and key; a PostgreSQL advisory lock serializes the claim and the response is stored with the business result. A separate run lock prevents duplicate execution. | `test_concurrent_idempotency_returns_one_run` sends 20 simultaneous identical requests and requires one run ID with 20 HTTP 201 responses. Reusing the key with a different body returns 409. `test_progress_is_committed_while_execution_is_running` covers the execution lock. |
| P1 | No authenticated actor or tenant boundary | **Implemented within a pilot boundary.** Shared mode requires a bearer identity, derives audit actors server-side, applies viewer/operator/reviewer/admin permissions, and returns 404 for another subject’s run. Local demo mode is explicit and loopback constrained. | `tests/unit/test_auth.py` and `test_other_subject_cannot_read_or_review_run`. This is per-person ownership with operator-managed bearer rotation. Enterprise SSO/MFA, automatic token expiry, organization tenancy, shared team membership, and maker/checker separation are not implemented. |
| P1 | Tax title and ITC claim had no GSTR-2B input | **Scope corrected.** The product presents gateway fee and tax policy arithmetic, uses the recorded policy snapshot, and exposes invoice/return evidence and ITC eligibility as unavailable. | `tests/unit/test_tax_audit.py` covers fee/tax arithmetic. ClearLedger does not ingest GSTR-2B, supplier invoices, GSTINs, or return-period evidence; it therefore does not claim tax-line matching or eligible ITC. A full tax matcher needs those independent inputs and its own evaluation set. |
| P1 | Custom reconciliation awaited demo evaluation before navigation | **Implemented.** Operational completion opens the run even when no compatible truth set exists. The accuracy surface reports “not evaluated”; optional evaluation failure cannot hide the reconciliation result. | `apps/web/tests/frontend-contract.spec.ts`: `custom upload finishes without attempting demo ground-truth evaluation` and `missing evaluation remains unverified`. |
| P1 | Evidence links used URL parameters the cases page ignored | **Implemented.** Case links use run-scoped canonical URLs; `state`, `severity`, `code`, `owner`, age, amount, AI/human, bucket, sort, `search`, and exact `case` values initialize from the URL and survive reload. | `frontend-contract.spec.ts::URL code/search/case filters select exact evidence and survive reload`. Run scope also prevents a repeated synthetic case ID from mutating another run (`test_repeated_case_ids_require_run_and_never_cross_mutate`). |
| P1 | Review mutations left dependent caches stale | **Implemented.** Mutations carry `expected_review_revision`; the server locks the run, increments the revision, recalculates aggregates, and rejects stale writes. The browser invalidates run, cases, metrics, evaluation, forecast, tax, cash, receipts, claims, and audit data; run shells also react to execution/review revision changes. | `test_concurrent_review_aggregates_match_current_cases` and `frontend-contract.spec.ts::review mutation uses revision and refreshes forecast, tax, receipt and current run`. Receipts expose immutable baseline and current-review checksums (`test_receipt_hash_distinguishes_baseline_and_current_review`). |
| P1 | Exception rows displayed net while the aggregate used residual-based amounts | **Implemented.** Every case response includes a server-computed `cash_bucket_contribution_paise` and `cash_contribution_basis`; cash drilldowns display that value. Bucket totals use the same function. | `tests/integration/test_reconciliation.py::test_cash_position_buckets_sum_to_case_contributions`, `tests/unit/test_case_presentation.py`, and `frontend-contract.spec.ts::cash drilldown shows exact bucket contribution instead of case net`. |
| P1 | Policy and audit immutability were weaker than product language | **Implemented for the pilot evidence boundary.** Each execution snapshots policy/calendar data and input checksums. PostgreSQL rejects update, delete, and truncate on raw rows, policy versions, decisions, and audit events. The exported control package includes source bytes, row dispositions, policy, cases, cash, audit, decisions, and a digest. | `apps/api/tests/test_integrity_migration.py`, `test_source_hash_mismatch_fails_before_results_are_persisted`, `apps/api/tests/test_exports.py::test_rejected_rows_and_control_package_are_independently_verifiable`, and `tests/unit/test_control_package.py`. The offline verifier checks package integrity, row coverage, exact arithmetic, and run scoping. It does not prove that bank data is authentic, establish tax eligibility, or replace independent source/oracle attestation. |
| P2 | Setup readiness mixed source presence with row validity | **Implemented.** The percentage is labelled “Required source readiness.” Required-source presence, processing permission, accepted rows, partial files, and rejected rows have separate fields and counts. Invalid raw rows remain recorded and can be downloaded as CSV. | Setup UI plus `apps/api/tests/test_exports.py::test_rejected_rows_and_control_package_are_independently_verifiable`, which checks eight synthetic rejected rows include issue and raw-value evidence. |
| P2 | Browser pagination contract was stale and most tests were skipped | **Implemented.** Page state, record counts, page-size controls, keyboard actions, and compact records are visible browser semantics. The checked-in Playwright configuration runs contract and live API flows. | `apps/web/tests/frontend-contract.spec.ts` and `apps/web/tests/demo-flow.spec.ts`. The local run reported below executed all 19 tests; CI runs `pnpm --dir apps/web test:e2e`. |
| P2 | Exception age used run/case creation time | **Implemented.** Responses separate source `event_at`, event `age_days` at the run cutoff, settlement `sla_due_at`/`days_past_sla`, and human `review_due_at`. Unknown source dates remain unknown. | `tests/unit/test_case_presentation.py::test_event_age_and_sla_use_source_and_run_cutoff_not_insert_time` and `test_unknown_event_is_not_substituted_with_case_creation_time`. |
| P2 | Important exception context required horizontal travel | **Implemented.** Case, state, amount at risk, and next action are the leading desktop columns and the compact mobile fields. Secondary identifiers remain available in the evidence drawer. Rows and actions are keyboard reachable. | `frontend-contract.spec.ts::pending evidence does not mark an absent bank receipt matched; compact keyboard action works` plus live desktop/mobile checks in `demo-flow.spec.ts`. |
| P2 | No CI workflow | **Implemented.** CI uses frozen installs and a fresh PostgreSQL service; checks lint/core typing, migrations and schema drift, all Python tests, adversarial evaluation/auth controls, claims reproduction, browser flows, secret/dependency scans, and separate shared/demo image boundaries. Outputs and browser failure evidence are retained for 14 days. | `.github/workflows/ci.yml`. Actions are pinned to commit SHAs; the runtime image check rejects bundled demo/oracle data. `make typecheck-core` is intentionally a named strict subset, not a claim that the whole service layer passes strict mypy. |
| P2 | API errors and progress hid operational state | **Implemented.** Reconciliation persists stage, processed-record count, percent, start/completion times, and failure reason; clients poll the persisted status. Error envelopes and response headers carry a request ID, database outages return retryable 503 with `Retry-After`, and the UI shows retry guidance. | `test_progress_is_committed_while_execution_is_running`, `apps/api/tests/test_failure_injection.py`, `frontend-contract.spec.ts::progress reports persisted backend stage and record count`, and `proof failure presents request ID and recovers through retry`. |

## Reproduce the verification

From the repository root:

```bash
docker compose up -d db
uv run --frozen alembic upgrade head
uv run --frozen alembic check
uv run --frozen pytest
make lint typecheck-core
pnpm --dir apps/web lint
pnpm --dir apps/web typecheck
pnpm --dir apps/web test:e2e
make verify-claims
make security-scan
```

Local verification on 2026-09-05 observed **190 passing pytest tests** and **19 passing Playwright
tests** across the contract and live-demo browser groups. Those counts describe that local run,
not an external certification; the GitHub Actions run is the durable clean-clone record.
`make security-scan` contacts dependency advisory services and therefore requires network access.

`make verify-claims` regenerates the synthetic dataset, evaluation, ablation, stress, and final
metrics with optional AI disabled. Throughput depends on the machine and runtime conditions; no
fixed records-per-second result is guaranteed. Review match quality, exception counts, exact
monetary reconciliation, seed, checksums, and scenario breakdowns from the newly generated
artifacts instead of copying a prior headline number.

An exported control package can be checked without the application runtime:

```bash
python -m services.reporting.verify control-package.json \
  --expected-sha256 <digest-recorded-separately-at-export>
```

The separately recorded digest is needed to detect replacement of the whole package. Passing this
command establishes the documented integrity and arithmetic checks only; it does not authenticate
the bank or gateway that supplied the original CSV files.
