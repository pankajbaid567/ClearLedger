# ClearLedger architecture, API, persistence, and AI review

Reviewed 2026-09-05. Read-only repository review; all reproduction writes were confined to temporary directories and uniquely named PostgreSQL `review_<uuid>` schemas, which were dropped in `finally`. No provider requests or real financial operations were performed. Existing source files were not edited.

## Assessment

The deterministic-first design, exact paise arithmetic, explicit unresolved cases, persisted evidence, and evaluator separation are strong foundations for Track 04. The present API is not submission-ready: the normal CSV upload path is broken, multiple simultaneous runs are not isolated in case endpoints, grounded Q&A makes false accuracy assertions, and concurrent review can corrupt the displayed cash aggregate. Fixing these will improve the project more than adding another broad feature.


## Priority findings

### P0 — Standard CSV upload path raises immediately

Evidence: `apps/api/app/routes/runs.py:142` references `settings` without importing or injecting it; `:148` references unimported `APIError`, and `:149-151` supplies three positional arguments to a constructor whose signature takes code/message and keyword-only status. Primary review's full suite and Ruff reproduced this. `/api/runs/demo` bypasses this route via the service, explaining why a polished canned demo can still work.

Fix: inject `Settings` with `Depends(get_settings)` or use the service's bound configuration; import and correctly construct `APIError("FILE_TOO_LARGE", message, status_code=413)`; use bounded stream reads and reject empty uploads. Verify multipart parsing limits separately from application file-size limits.

Acceptance: fresh run + all five CSVs -> 200; just over configured size -> 413 typed error; unsupported/empty input -> documented 4xx; no filesystem/DB registration after rejected upload. Run the real upload flow, not only the demo shortcut.

### P0 — Missing prompt files break the live AI path and Docker build

Evidence: `services/ai_analyst/client.py:28,67,122` loads `prompts/exception_analyst.v1.md`; `services/ai_analyst/grounded_qa.py:31,215` loads `prompts/grounded_qa.v1.md`. Neither directory/file exists. `apps/api/Dockerfile:19` unconditionally `COPY prompts ./prompts`. The full suite confirmed prompt-dependent test failures. The integrated review also executed a clean Git archive Docker build and confirmed both missing COPY inputs.

Fix: restore version-controlled prompt assets and validate asset existence at startup/CI; make package/image asset inclusion explicit. Keep mock mode clearly labeled, with a separate tested live-provider adapter.

Acceptance: clean checkout `docker compose build` succeeds; structured-output adapter test loads the actual checked-in prompt; injected timeout/invalid JSON returns a recorded unresolved case; no paid provider call required for CI.

### P1 — Opening an older run can read or mutate a newer run's case

Evidence: deterministic IDs depend only on source identifiers (`services/reconciliation/orchestrator.py:133-157`), and DB uniqueness is `(case_id,reconciliation_run_id)` (`db/models.py:282`). However `CaseRepository.get_case` makes run optional and selects newest matching `case_id` (`db/repositories/case_repository.py:63-75`). Detail/evidence/receipt routes use `/api/cases/{case_id}` without run (`apps/api/app/routes/cases.py:29-30,84-110`); review routes do likewise (`apps/api/app/routes/review.py:39-58`); AI analysis lookup also omits run (`db/repositories/review_repository.py:26-33`). Tasks do not even store a run foreign key (`db/models.py:478-492`).

Verified reproduction: two runs containing `CASE_DUPLICATE`; bare case GET returns second run's owner; rejecting from the shared case endpoint changes only the second run, while first remains untouched. This occurs during ordinary repeated demo runs, even with a single honest user.

Fix: make all case resources `/api/runs/{run_id}/cases/{case_id}` or use globally unique case row UUIDs; require the composite key in repository signatures, AI lookups, review records, follow-up tasks, frontend query keys, and idempotency scopes. Never resolve ambiguity by “latest.”

Acceptance: create two runs with identical case IDs and different amounts/owners; reads, approvals, rejects, analysis and exports from run A must never affect or display B; concurrent creation must not change an already-open drawer's target.

### P1 — “Grounded” Q&A invents perfect accuracy and zero residual

Evidence: `services/ai_analyst/grounded_qa.py:167-171` defaults absent precision/recall/F1 to 1.0, false positives to 0, and residual to the literal `₹0.00`; `:345-351` labels this “Evaluated vs Ground Truth” and hardcodes `(100.0%)` and `(Zero false matches)` even beside nonperfect numbers. `:366` repeats zero residual in a default overview. A case-specific narrative claims prompt injection from a hardcoded ID or merely a question containing “prompt”/“injection” (`:288-295`), without inspecting evidence.

Verified: an empty unevaluated run returns precision/recall/F1=1.0 and zero false matches. Injected metrics precision=.7, recall=.5, false positives=3 render “0.7000 (100.0%)”, “0.5000 (100.0%)”, “3 (Zero false matches).” This directly conflicts with Track 04's honest measured accuracy bar.

Fix: retrieve evaluated metrics from a typed evaluation snapshot with status, dataset/result checksum, denominator, and timestamp. Render missing values as “not evaluated.” Derive percentages and residuals from the same facts; derive security narratives from actual recorded findings. Distinguish run-time match coverage from ground-truth precision.

Acceptance: unevaluated, empty, deliberately inaccurate, and nonzero-residual fixtures must yield accurate, mutually consistent sentences; every quantitative answer must have a fact reference and explicit evaluation status. Test negative cases, not only perfect synthetic metrics.

### P1 — Live Q&A text is not validated despite `grounded=true`

Evidence: `_call_llm` accepts the raw completion; it intersects extracted IDs with available IDs but leaves fabricated IDs and amounts in the answer (`services/ai_analyst/grounded_qa.py:238-240`). `answer_question` labels every successful completion grounded (`:94-103`). The user's question is substituted into the system prompt (`:216-232`). This path has none of the exception analyst's external schema/evidence/amount validation. The current missing prompt means live Q&A falls back; restoring prompts exposes this latent defect.

Verified with a mocked provider (no network): “Safe cash is ₹999999999. CASE_INVENTED is reconciled.” is returned unchanged, with an empty cited ID list. Removing an invented ID from metadata does not remove the false claim from prose.

Fix: have the model select typed intents/fact IDs and propose only constrained explanatory text; render monetary values and statuses deterministically. Reject unsupported citations and numbers in the answer itself. Keep user content out of system instructions; give `grounded` an actual validation meaning and expose a rejected/fallback status. Add token/cost limits and Q&A audit events if enabling public access.

Acceptance: fabricated cash, nonexistent case, wrong case amount, injected “ignore prior rules,” and provider outage must result in rejected output or a correct deterministic answer, never `grounded=true` on the unvalidated response.

### P1 — Concurrent approvals lose cash and case-count updates

Evidence: review fetches cases without row locking (`services/reconciliation/review_service.py:48,504-513`; `db/repositories/case_repository.py:63-75`). Aggregate recalculation reads all cases, constructs cash/state values in memory, then overwrites the snapshot and run without locking the run first (`services/reconciliation/review_service.py:433-492`). Two transactions can each read the other case before its approval commits and overwrite aggregates using stale snapshots.

Verified with a controlled, valid interleaving of two independent sessions: CASE_A=100 paise and CASE_B=200 paise both finish `RECONCILED`, yet bank-confirmed cash becomes **100 instead of 300**, and metrics report **one reconciled and one exception**. Barrier instrumentation makes the concurrent schedule deterministic; it does not change application values or queries.

Fix: serialize mutations per run by acquiring the run lock *before* reading/modifying cases, and enforce optimistic case versions for operator conflicts; recalculate within that serialized transaction. Or implement a transactional event/projector design with a monotonic projection version, but that is larger scope. Read the policy version bound to the run during approval: `_reverify_suggestion` currently calls global `load_policy()` at `:201`, which can differ from the policy originally used.

Acceptance: simultaneous approvals, approve/reject, assign/reconcile and approval/analysis tests must leave counts and cash identical to an independent recomputation; rejected stale actions return 409 with refreshed case state. A run created under policy A must still verify under A after default policy B is installed.

### P1 — Reconciliation reruns erase operator work and evidence history

Evidence: every execution calls `clear_for_run` (`services/reconciliation/run_service.py:518-521`), deleting AI analyses, evidence, invariants, exceptions, cash and cases (`db/repositories/case_repository.py:27-37`). The recreated cases reset `ai_assisted=False` and `human_reviewed=False` (`run_service.py:621-624`). Human decisions and audit events remain, but point at a replaced logical case with no execution-version boundary. Execution does not reject a completed run (`run_service.py:378-403`).

Verified: assigning `CASE_AMB0073` to “Assigned Reviewer” then rerunning resets owner to “Reconciliation Ops”, human_reviewed to false, and changes the case row UUID; the previous HumanDecision still exists. Fresh idempotency keys trigger this without special access. Source data can remain unchanged while the operator's work disappears.

Fix: make a completed execution immutable. Rerun should create a new execution/run referencing its parent, inputs, policy, rule and code version; preserve baseline versus reviewed projections separately. If reexecution in place is intentional, require an explicit reset operation and preserve fully versioned results and operator history.

Acceptance: repeat reconciliation with same inputs returns the same completed execution; changed configuration creates a linked new version; old evidence, decisions, exports and review state remain addressable and checksum-verifiable.

### P2 — Database-backed idempotency is not concurrency-safe

Evidence: `apps/api/app/idempotency.py:29-37` performs an unlocked read, business logic executes, and `:58-67` inserts only at the end. Unique `(scope,key)` (`db/models.py:546`) prevents two committed records but does not coordinate concurrent execution. SQLAlchemy uniqueness failures become misleading 503 DATABASE_UNAVAILABLE (`apps/api/app/main.py:126-134`). For provider calls or filesystem work, rollback cannot undo duplicated side effects/cost.

Verified: two simultaneous `/api/runs` calls with the same key/payload return **201 and 503**. Test barrier aligns the two initial “not found” checks. The winning response is not replayed to the concurrent loser.

Fix: reserve `(scope,key)` atomically before work, with request hash and IN_PROGRESS/COMPLETED status; lock/wait/replay for the same key and return 409 for payload mismatch. Handle transaction conflicts specifically. Include run/actor ownership in scope when identity is introduced.

Acceptance: 20 concurrent same-key calls produce one operation and identical successes (or documented in-progress responses), one provider invocation, and one audit decision; same key/different payload -> 409. Failure/retry behavior must be explicit.

### P2 — Boundaries and receipts can become inconsistent after review

Evidence: evaluation reads frozen `run.config.prediction_report` (`services/evaluation/service.py:31,47-64`) while review mutates current cases/cash (`review_service.py:90-119,433-492`); `result_checksum` covers original prediction/cash (`run_service.py:706-738`). Case receipts return current invariants plus that original checksum (`apps/api/app/routes/cases.py:109-120`). Single-case AI analysis overwrites the run's cumulative `metrics.ai` with the fresh service's single-call metrics (`apps/api/app/routes/ai.py:79-88`). Exceptions export reads every original ExceptionRecord and omits `human_review_state` (`apps/api/app/routes/exports.py:187-214`), including cases now resolved; assign changes case owner but not ExceptionRecord owner.

Impact: dashboard, exports, Q&A and verification receipt can each describe different moments in the workflow. A correct original benchmark is legitimate, but must be labeled baseline rather than presented as current state.

Fix: establish an explicit immutable execution baseline plus a versioned review projection. Label baseline evaluation, present current open exceptions using current case state/owner, version/hash review receipts separately, and aggregate AI usage from persisted analyses. Include currency, run, execution version and as-of timestamp in exports.

Acceptance: analyze -> approve -> assign -> export -> evaluate must have coherent documented semantics; resolved cases excluded from open-exception export or clearly marked resolved; AI totals are cumulative; receipt hash changes only when its represented snapshot changes.

### P2 — Q&A silently truncates larger batches to 300 cases

Evidence: `services/ai_analyst/grounded_qa.py:72` fetches 300 cases and ignores the returned total. `:162-165` takes total_cases from the full run but reconciled/exception counts and STP from those first 300. For 1,000 cases it can claim a 300-case subset is the full exception queue and refuse to find a valid later case.

Fix: compute aggregate facts in SQL across the full run; perform targeted case retrieval for mentioned IDs and bounded relevance retrieval for explanatory context. State any context sample boundary.

Acceptance: >300-case fixture with exceptions only after the first 300 gives correct full-batch counts and locates a requested late case; no hidden denominator changes.

## Deployment and integrity improvements after correctness blockers

- **Safe local default, explicit public deployment profile.** Auth absence is documented honestly in `docs/SECURITY.md:10-12,23`; do not treat an enterprise SSO build as required to pass this synthetic hackathon. However Compose exposes PostgreSQL and API to all interfaces with default demo DB credentials (`docker-compose.yml:5-12,44-45`) and compiles the browser API URL as localhost (`:67-69`), so it is unsafe/broken to present that configuration as a shared hosted service. Bind local ports to 127.0.0.1, avoid publishing DB externally, use same-origin API routing, and gate shared demo mutations with per-session run ownership and quotas.
- **Make immutability enforceable or narrow the claim.** Raw/audit tables have ordinary update/delete privileges and cascading deletes, with no migration triggers/role restrictions (`db/models.py:118-124,495-517`). The repository omits update methods, which is a convention, not a tamper-resistant audit control. Before using “immutable audit,” add append-only DB permissions/triggers for raw/audit history and separate app/migration roles; optionally hash-chain audit events/export a signed manifest. This is a product credibility improvement, not a claim of an existing external exploit.
- **Verify source checksums at execution.** Upload bytes are written to mutable paths before DB commit (`run_service.py:265-275`), and validation rereads paths without comparing to registered checksum (`:319-348`). Subsequent persistence reuses old raw rows whenever any already exist (`:763-772`). Atomic content-addressed writes plus read-time hash verification prevent byte/receipt drift and concurrent losing uploads from overwriting the winner's filesystem file. Test a changed stored file -> explicit integrity exception before reconciliation, preserving original evidence.
- **Bound full workflow latency, not only engine latency.** Run execution holds its database transaction/row lock throughout engine work and sequential AI calls (`run_service.py:378-416,445-460`; AI service `:133-135`). A default maximum of 20 cases × 20-second timeout can hold a request for many minutes. `COMPLETED`/duration fields are initially written before AI finishes and measure deterministic result duration (`run_service.py:715-732`). For the demo, expose deterministic compute, persistence, AI, and end-to-end durations separately. A later durable job worker should commit stages, support retry/cancellation, and preserve deterministic completion during AI outages.
- **Do not overclaim review verification.** Non-AI approve reads cached invariant rows and checks residual (`review_service.py:61-66`), while documentation says approval reruns invariants (`docs/SECURITY.md:23`). Either reverify the bound immutable snapshot for all approvals or clearly label cached verification, enforce the complete expected invariant set, and tie it to a checksum/version.

## Focused additions that would strengthen Track 04

1. **One verifiable close package.** Export a single run manifest containing input checksums, policy/rule/code versions, source control totals, every disposition, match numerator/denominator, measured precision/recall where truth exists, exact residuals, cash bridge, open exceptions, and execution/review versions. Include a small offline `verify-close` command that independently checks hashes, allocations, totals and exception coverage. This turns the differentiator into verification capacity rather than another dashboard.
2. **A real exception completion cycle.** Follow-up tasks are currently created as OPEN records with no status/completion routes (`db/models.py:478-492`, review routes). Support attach evidence -> linked successor run -> reverify -> close task, preserving prior state and a before/after cash explanation. Demonstrate one late bank credit arriving after the original batch, not manual force-approval.
3. **Blind batch plus failure replay.** Run an unseen seed/perturbed IDs/custom CSV upload live and let a judge inspect all exceptions and replay a chosen verification receipt. Include concurrent operator and duplicate-request cases in the published validation evidence. This aligns directly with measured accuracy over 50+ records.
4. **Typed facts shared by all surfaces.** One fact/evaluation schema should feed dashboard, Q&A, exports and close-package verifier so unknown metrics remain unknown, currencies stay explicit, and review state cannot drift from the exception list.
5. **Operator conflict handling.** When two reviewers act, show a clear “case changed; refresh evidence” state with who/when/why, instead of silent lost updates. A small correct collaboration surface is stronger than broad speculative integrations.

## Existing strengths to retain

- Monetary authoritative fields use integer paise and PostgreSQL BIGINT; comparisons do not rely on floating tolerance.
- Clean deterministic reconciliation is separate from model interpretation, and AI rankings cannot directly create final verified allocations.
- Exception analysis uses bounded packets, precomputed candidate IDs, independent allowlist validation, timeout/retry handling, and durable per-analysis records (`ai_analyst/evidence_packet.py`, `validator.py`, `service.py`). Q&A should reuse this discipline.
- Source replacements are rejected at service level; checksums and policy snapshots already provide the material needed for reproducibility.
- Correlation IDs, typed error envelopes, readiness, CSV formula escaping, explicit synthetic/demo scope and failure-injection tests are worthwhile foundations.
- External money movement is not implemented; that keeps the demonstration focused on safe finance-ops verification.

## Reproduction artifacts

Retained in this folder for review; adapt into regression tests after fixes:

- `docs/review/reproduce_api_findings.py` — creates/drops a unique DB schema; proves cross-run targeting, concurrent idempotency, rerun data loss, Q&A invented defaults/contradictions, and acceptance of mocked fabricated LLM prose. Uses only documented local demo PostgreSQL credentials; no real secrets or provider calls.
- `docs/review/api-reproduction-results.jsonl` — six exact result records.
- `docs/review/reproduce_concurrency_findings.py` — unique schema; forces a valid concurrent-review interleaving; proves final cash/count divergence.
- `docs/review/concurrency-reproduction-result.json` — exact result: both cases reconciled, expected cash 300, actual cash 100, metrics reporting only one reconciled.

Commands, from repository root:

```sh
AI_ENABLED=false PYTHONPATH=. uv run python docs/review/reproduce_api_findings.py
AI_ENABLED=false PYTHONPATH=. uv run python docs/review/reproduce_concurrency_findings.py
```

The scripts use test barriers only to deterministically schedule a concurrency race; they do not monkeypatch financial calculations. They never drop an existing application schema. Primary review owns aggregate test/benchmark reporting; this report does not claim those broader checks passed.
