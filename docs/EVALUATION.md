# ClearLedger Evaluation Methodology

## Objective

Evaluation measures whether ClearLedger can explain payment-to-bank relationships without unsafe
matches. Relationship correctness, case classification, money coverage, exceptions, residuals,
and runtime are measured separately so a high match count cannot hide financial risk.

## Ground-Truth Isolation

The generator emits source CSV files under `data/<dataset>/` and a private manifest under
`evaluator_private/`. Reconciliation receives only source paths and a versioned policy. It does
not import or read a ground-truth file. After predictions are serialized to
`out/reconciliation_report.json`, the standalone `evaluator` process loads both artifacts and
scores them. The application database contains predictions and evidence, never expected answers.

The private directory is gitignored for normal product packaging. It is copied into the demo API
container only so the submission's explicit evaluation endpoint can reproduce judge-facing
metrics; the financial engine still has no path or parameter for it.

## Dataset

The evaluation set is generated with seed `20260827` and policy `settlement_policy@1.0.0`.

| Scenario | Cases | Expected behavior |
|---|---:|---|
| Clean lifecycle | 20 | Reconciled |
| Batched settlement | 10 | Reconciled, many payments to one settlement |
| Timing delay | 7 | Pending within SLA |
| Holiday shift | 4 | Reconciled using business calendar |
| Refund | 6 | Reconciled with declared debit component |
| Chargeback | 4 | Reconciled with declared dispute component |
| Split settlement | 4 | Reconciled one-to-many lifecycle |
| Fee variance | 4 | Actionable exception |
| Messy narration | 5 | Reconciled from bounded deterministic tokens |
| Malformed input | 4 | Invalid input, row remains visible |
| Missing bank event | 4 | Actionable exception |
| Deliberately ambiguous | 3 | Actionable exception, never force matched |
| **Total** | **75** | **693 source records** |

The stress set uses seed `99999`, exactly 1,000 economic cases, and an 80% clean / 20% batched
mix. It is intentionally simpler and is not used to claim exception-scenario coverage.

## Metric Definitions

Let `T` be expected relationship edges and `P` be predicted edges.

- **Relationship precision:** `|P intersect T| / |P|`. If no edges are predicted, precision is
  defined as 1.0 and recall exposes the absence of matches.
- **Relationship recall:** `|P intersect T| / |T|`.
- **F1:** `2 * precision * recall / (precision + recall)`.
- **Case-state accuracy:** cases whose predicted state equals expected state / total truth cases.
- **Exception-code accuracy:** correct codes / truth cases with an expected exception code.
- **Cash-bucket accuracy:** correct confidence buckets / total truth cases.
- **STP rate:** cases classified `RECONCILED` without human review / all predicted cases.
- **Monetary reconciliation rate:** gross truth amount in correctly reconciled cases / total gross
  truth amount.
- **False positive:** a case declared `RECONCILED` whose truth state is not reconciled.
- **Unexplained residual:** absolute residual inside cases declared `RECONCILED`. Acceptance
  requires zero.
- **Open exception residual:** visible residual attached to non-reconciled cases. This is reported
  separately and is not relabeled as reconciled money.
- **Throughput:** source records / measured engine wall time.
- **Case latency:** time spent applying all case invariants, residual logic, classification, and
  structured exception construction. P50/P95 use nearest-rank percentiles.

## Commands

```bash
make generate-demo
make evaluate
```

Outputs:

- `out/reconciliation_report.json`: predictions only.
- `out/evaluation.json`: aggregate and scenario metrics.
- `out/evaluation.md`: human-readable evaluation.

Run ablation and stress measurements with:

```bash
make ablation
make stress-test
```

The ablation compares rules 1-3, all nine deterministic rule stages, and deterministic plus the
configured AI analyst. AI is non-authoritative, so no precision/recall lift is fabricated when it
is disabled or when it only improves review triage.

## Acceptance Checks

`make verify-claims` fails unless:

- precision is 1.0 among published verified relationships;
- recall is at least 0.95;
- false positive count is zero;
- reconciled-case unexplained residual is zero;
- deterministic demo runtime is under 10 seconds;
- the evaluation set has at least 75 cases and 150 source records;
- the stress set has at least 1,000 source records; and
- repeated generation with the same seed produces identical source checksums and case results.
