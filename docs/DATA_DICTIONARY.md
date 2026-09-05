# ClearLedger Data Dictionary

## Conventions

- Authoritative money is a signed or unsigned integer number of paise. No financial comparison
  uses binary floating point.
- Timestamps are parsed as timezone-aware values and normalized to UTC. Date-only bank values
  remain calendar dates.
- Missing values remain `null`; they are never converted to zero.
- Identifiers are trimmed, uppercased, and stripped of characters other than `A-Z`, `0-9`, `_`,
  and `-`. Raw values remain available beside normalized values.
- Currency defaults to `INR` in synthetic sources but must agree within every verified case.
- Uploaded rows and narration are untrusted. A malformed row is retained with `INVALID` quality
  and structured issues.

## Source Files

### `orders.csv`

| Field | Type | Required | Meaning and normalization |
|---|---|---:|---|
| `order_id` | string | Yes | Merchant order identifier; normalized identifier rules apply. |
| `merchant_id` | string | Yes | Merchant ownership boundary; normalized identifier rules apply. |
| `order_created_at` | UTC datetime | Yes | Order creation instant; naive values use `Asia/Kolkata` before UTC conversion. |
| `order_amount_paise` | integer paise | Yes | Gross order amount; decimal strings are rejected. |
| `currency` | ISO-like string | Yes | Defaults to `INR`; uppercased during canonical normalization. |
| `expected_payment_status` | string | Yes | Expected lifecycle state, default `captured`; uppercased canonically. |

### `payments.csv`

| Field | Type | Required | Meaning and normalization |
|---|---|---:|---|
| `payment_id` | string | Yes | Gateway payment identifier. |
| `merchant_id` | string | Yes | Merchant ownership boundary. |
| `order_id` | string | Yes | Source link to the originating order. |
| `payment_status` | enum-like string | Yes | `authorized`, `captured`, `failed`, or `refunded`; normalized uppercase. |
| `amount_paise` | integer paise | Yes | Captured or attempted payment amount. |
| `currency` | ISO-like string | Yes | Defaults to `INR`; must match linked records. |
| `captured_at` | UTC datetime or null | No | Capture instant; missing for non-captured lifecycle states. |
| `payment_method` | string | Yes | Payment rail, default `upi`. |
| `gateway_reference` | string | Yes | External processor reference; empty string is allowed. |

### `settlements.csv`

| Field | Type | Required | Meaning and normalization |
|---|---|---:|---|
| `settlement_id` | string | Yes | Settlement batch identifier. |
| `merchant_id` | string | Yes | Merchant ownership boundary. |
| `settlement_status` | enum-like string | Yes | `initiated`, `processed`, or `failed`; normalized uppercase. |
| `currency` | ISO-like string | Yes | Defaults to `INR`. |
| `net_amount_paise` | integer paise | Yes | Reported settlement net; must equal signed components exactly. |
| `initiated_at` | UTC datetime | Yes | Settlement initiation instant. |
| `processed_at` | UTC datetime or null | No | Provider processing instant. |
| `expected_bank_date` | date | Yes | Declared bank-arrival date, checked against bound policy. |
| `utr` | string or null | No | Bank transfer reference; normalized identifier rules apply. |

### `settlement_components.csv`

| Field | Type | Required | Meaning and normalization |
|---|---|---:|---|
| `component_id` | string | Yes | Unique component identifier. |
| `settlement_id` | string | Yes | Parent settlement identifier. |
| `component_type` | enum | Yes | `PAYMENT`, `GATEWAY_FEE`, `TAX_ON_FEE`, `REFUND`, `CHARGEBACK`, `CHARGEBACK_REVERSAL`, `RESERVE_HOLD`, `RESERVE_RELEASE`, or `OTHER_DECLARED_ADJUSTMENT`. |
| `source_event_id` | string | Yes | Payment/refund/dispute event that generated the component. |
| `amount_paise` | integer paise | Yes | Absolute component amount. |
| `direction` | enum | Yes | `CREDIT` adds and `DEBIT` subtracts from settlement net. |

### `bank_transactions.csv`

| Field | Type | Required | Meaning and normalization |
|---|---|---:|---|
| `bank_transaction_id` | string | Yes | Unique bank statement row identifier. |
| `merchant_id` | string | Yes | Merchant ownership boundary. |
| `account_id` | string | Yes | Receiving bank-account identifier. |
| `posted_at` | UTC datetime | Yes | Posting instant. |
| `value_date` | date | Yes | Effective bank date used for settlement policy windows. |
| `direction` | enum | Yes | `CREDIT` or `DEBIT`; creates canonical signed amount. |
| `amount_paise` | integer paise | Yes | Absolute bank movement amount. |
| `currency` | ISO-like string | Yes | Defaults to `INR`; must match settlement. |
| `narration` | untrusted string | Yes | Preserved raw; regex extracts order/payment/settlement/UTR tokens only. |
| `utr` | string or null | No | Structured transfer reference when supplied by the bank. |

## Canonical Entities

| Entity | Identity and principal constraints |
|---|---|
| `PolicyVersion` | Immutable policy ID/version pair with effective dates and checksum-backed JSON. |
| `ReconciliationRun` | Immutable execution UUID; binds owner, parent execution, as-of time, source manifest, complete policy/calendar snapshot, rule/app/AI versions, durable stage progress, baseline metrics, and result checksum. |
| `SourceFile` | One source type per run; SHA-256 checksum, byte size, row count, and quality are retained. |
| `RawSourceRow` | Append-only uploaded values, row number, source record ID, quality, and file provenance. |
| `IngestionIssue` | Field/value/reason/code attached to a raw row; invalid rows remain queryable. |
| `Order` | Canonical order keyed by merchant/order identity; amount is `BIGINT` paise. |
| `Payment` | Canonical payment linked to order and merchant with lifecycle status and capture time. |
| `Settlement` | Canonical settlement net, currency, lifecycle dates, expected bank date, and optional UTR. |
| `SettlementComponent` | Signed-by-direction component linked to settlement and source event. |
| `BankTransaction` | Canonical bank movement with account, dates, direction, amount, raw narration, and extracted IDs. |
| `ReconciliationCase` | Economic lifecycle group with state, decision level, gross/net/residual, exception, cash bucket, owner, and immutable record snapshot. |
| `CandidateRelationship` | Bounded precomputed source/target pair with rule, score, evidence fields, amount, and decision level. |
| `EvidenceEdge` | Accepted typed relationship with exact allocation, rule/version, actor, checks, and run provenance. |
| `InvariantResult` | Expected versus actual value for a named deterministic check; scoped to a case and run. |
| `ExceptionRecord` | Structured code, severity, amount at risk, summary, missing evidence, owner, and next action. |
| `AIAnalysis` | Bounded packet, raw/validated response, model/prompt/provider metadata, tokens, latency, cost, attempts, and rejection detail. |
| `HumanDecision` | Append-only approve/reject/defer/assign action with server-derived actor, previous/new state, execution/review revisions, reason, note, and invariant outcome. |
| `FollowUpTask` | Run-and-case-scoped action code, required evidence, owner/status, amount at risk, and deadline. |
| `AuditEvent` | Append-only run/case/source event with stage, severity, actor, duration, and structured details. |
| `CashPositionSnapshot` | Five confidence buckets, known deductions, safe cash, currency, run, and calculation time. |
| `IdempotencyRecord` | Unique operation scope/key, request hash, and exact replay response. |

## Evidence Graph

| Edge type | Source -> target | Allocation meaning | Acceptance evidence |
|---|---|---|---|
| `order_payment` | Order -> Payment | Captured gross amount | Exact order ID, equal amount/currency/merchant, valid lifecycle. |
| `payment_settlement` | Payment -> Settlement | Payment net represented by components | Explicit component membership and exact signed component arithmetic. |
| `settlement_bank` | Settlement -> Bank transaction | Settlement cash allocated to bank movement | Exact UTR, verified narration reference, or unique exact amount/date candidate plus invariants. |

Verified edges cannot allocate more than the registered amount on either endpoint. Duplicate or
conflicting allocations are rejected before insertion. AI suggestions are not evidence edges at
the `VERIFIED` decision level.

## Derived Amounts

| Term | Definition |
|---|---|
| Gross | Sum of order amounts in the economic case. |
| Settlement net | Sum of settlement header net amounts; each header must equal signed components. |
| Residual | Absolute settlement net minus accepted bank allocation, or scenario-specific unresolved amount. |
| Bank confirmed | Net amount of cases with verified bank receipt. |
| Settlement confirmed in transit | Processed settlement still within policy bank-arrival SLA. |
| Expected settlement | Captured amount not yet processed into settlement. |
| At risk | Overdue, invalid, or materially inconsistent amount. |
| Unresolved | Ambiguous or insufficiently evidenced amount that cannot be safely classified. |
| Safe cash | Bank-confirmed net batch movements only. Settlement components already included in net amounts are not deducted again; this is not a complete bank balance. |
