# ClearLedger Security and Financial Controls

## Scope and Boundary

ClearLedger is a demo settlement controller, not a money-movement or accounting-posting system.
Its most important security property is fail-closed financial classification: untrusted input,
model output, or a human click cannot create a verified allocation unless deterministic evidence
and exact arithmetic pass.

Shared mode authenticates configured high-entropy bearer identities, derives audit actors on the
server, applies role permissions, and scopes every run resource to its owner. Local demo mode is
explicit, synthetic, and loopback-only. Enterprise SSO, MFA, organization-level tenancy,
maker/checker separation, token expiry, and managed key lifecycle remain deployment work.

## Threat Model

| Threat | Attack path | Implemented mitigation | Residual risk |
|---|---|---|---|
| Prompt injection in bank narration | Narration says to ignore rules, reveal data, or mark a case reconciled. | Narration remains quoted untrusted evidence. Regex extracts only bounded identifiers. AI receives a case-scoped packet and has no tools. Output is schema/evidence validated and cannot set verified state. | A model may produce a poor non-authoritative explanation; the UI labels it AI-assisted and invariants remain authoritative. |
| Duplicate or replayed upload | Reuse bytes or repeat a mutation to duplicate source rows or decisions. | SHA-256 file checksums, one source type per run, explicit `DUPLICATE_UPLOAD` response, immutable replacement rule, and operation-scoped idempotency records. | Identical data can be intentionally loaded into a new run for comparison; run and dataset checksums expose it. |
| Double allocation | Allocate one settlement or bank movement more than once. | `EvidenceGraph` tracks absolute allocation by relationship/entity and rejects any proposed verified edge beyond registered availability. Property tests cover arbitrary amounts. | Non-authoritative candidates may overlap; only verified edges consume availability. |
| Fabricated AI evidence | Model cites an ID, amount, invariant, or candidate not present in its packet. | Closed Pydantic schema, evidence-ID allowlist, candidate-ID allowlist, identifier-value validation, one retry, then fail closed. | Provider raw output is retained for audit but never trusted as a fact. |
| CSV formula injection | Exported text begins with `=`, `+`, `-`, `@`, tab, or carriage return. | Every CSV cell passes `_safe_cell`; dangerous prefixes receive a leading apostrophe. Tests cover formula and command prefixes. | Consumers that deliberately strip the apostrophe can reintroduce risk. |
| Unauthorized accounting action | Caller attempts another subject's run or a mutation outside their role. | Shared mode requires a configured bearer identity, derives actors server-side, enforces viewer/operator/reviewer/admin permissions, and scopes run resources to `owner_subject`. Approval reruns invariants and cannot override a residual. | Pilot tokens have operator-managed rotation and no automatic expiry; organization tenancy and maker/checker separation are not implemented. |
| Database outage during mutation | Connection loss could create partial or ambiguous state. | Request sessions commit only after successful completion and roll back on exception. Database errors return `503 DATABASE_UNAVAILABLE` with `Retry-After`; run failures are explicit. Readiness reports database state. | Filesystem upload bytes may require operational cleanup after host failure; database registration remains transactional. |
| AI provider outage or malformed output | Timeout, invalid JSON, or provider error blocks the batch. | AI runs after deterministic persistence, has a bounded timeout, retries invalid structured output once, records warnings, and leaves cases unresolved. The UI displays degraded AI state. | Live triage suggestions are absent until a provider succeeds. |

## Implemented Controls

1. **Untrusted text cannot execute instructions.** CSV fields are parsed as data; narration only
   enters deterministic token extraction and bounded evidence packets.
2. **AI tools are read-only.** The model client receives JSON and has no function, database,
   filesystem, network-browsing, shell, or publication tool surface.
3. **AI has no arbitrary database or shell access.** Provider calls are made by a narrow client;
   persistence is performed by deterministic application code after validation.
4. **Every cited evidence ID is validated.** Fabricated evidence/candidate IDs reject the entire
   response. Invalid JSON is retried once and then rejected.
5. **Human actors are server-derived.** Actor, action, prior/new state, reason, note, execution
   revision, review revision, and invariant result are written to decisions and audit events.
6. **No autonomous ledger or payout write exists.** `ALLOW_EXTERNAL_WRITES` defaults false and no
   external-write implementation or route exists.
7. **Export formulas are escaped.** All reconciliation/exception CSV cells use centralized prefix
   escaping before serialization.
8. **File size/type limits exist.** Uploads must have a `.csv` filename, UTF-8 encoding, a supported
   source type, and be no larger than `MAX_UPLOAD_BYTES` (10 MiB by default).
9. **Secrets are externalized.** `.env` is ignored; `.env.example` contains names and empty/default
   values only. AI credentials are Pydantic `SecretStr` values and are not logged.
10. **Raw evidence and decisions are database-enforced append-only.** PostgreSQL triggers reject
    update, delete, and truncate for raw rows, policy versions, human decisions, and audit events.
    Original source bytes are checksum-verified again when a control package is exported.
11. **Money is exact.** Authoritative values use Python integers and PostgreSQL `BIGINT`; a
    reconciled case requires zero paise residual.
12. **Ground truth is outside reconciliation.** Only the standalone evaluator accepts a truth
    path; engine APIs accept source data and policy only.

## Failure-Injection Coverage

| Failure | Expected behavior | Automated coverage |
|---|---|---|
| Database unavailable | HTTP 503, recoverable envelope, rollback, no success response | `apps/api/tests/test_failure_injection.py` |
| AI provider timeout | Deterministic batch completes; eligible cases remain unresolved; warning metric | `tests/integration/test_ai_fallback.py` |
| Invalid AI JSON | One corrective retry, then rejection | `tests/unit/test_ai_contract.py` |
| Fabricated evidence ID | Full AI response rejected | `tests/unit/test_ai_contract.py` |
| Malformed CSV row | Row retained as `INVALID` with raw value and issue | `tests/integration/test_failure_injection.py` |
| Duplicate upload | HTTP 409 `DUPLICATE_UPLOAD`; one source record remains | `apps/api/tests/test_runs.py` |
| Defer a reconciled case | HTTP 409 `INVALID_STATE_TRANSITION` | `apps/api/tests/test_review.py` |

## Security Scans

Run all scans with:

```bash
make security-scan
```

| Scan | Command | Release policy |
|---|---|---|
| Frontend dependency advisories | `pnpm --dir apps/web audit --audit-level=high` | No unresolved high/critical production finding. |
| Backend dependency advisories | `uv export ...` then `uv tool run pip-audit -r ... --no-deps --disable-pip` | No unresolved critical finding; document any upstream advisory. |
| Repository secret scan | `python -m scripts.scan_secrets` | No credential/private-key match. |

Release scan on 2026-09-05:

- `pnpm audit`: **no known vulnerabilities** after overriding transitive PostCSS to `8.5.23`.
  The first scan found two high and two moderate source-map disclosure advisories; all were fixed.
- `pip-audit`: **no known vulnerabilities** across the fully pinned production `uv` export.
- repository secret scan: **passed**, with no matching credential or private-key material.

Scanner output is operational evidence; it is not a substitute for enterprise identity,
network policy, TLS, managed secrets, or periodic dependency updates.

## Reporting

Do not include raw credentials, full provider exceptions, or unbounded bank narration in logs or
issues. Security findings should identify the affected control, reproduction steps, financial
impact, and whether any verified allocation or exported artifact was affected.
