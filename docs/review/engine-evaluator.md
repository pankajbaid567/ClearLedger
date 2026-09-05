# ClearLedger engine, synthetic benchmark and evaluator review

Review date: 2026-09-05. Read-only review of reconciliation, normalization, ingestion, cash position, generator, evaluator and benchmark scripts. No implementation or repository data was edited. All adversarial fixtures and outputs were written under `/tmp/clearledger-adversarial`. Primary review owns official test/benchmark results and other subsystems.

## Executive assessment

The project exceeds the minimum batch size and has the right evidence-first architecture: a multi-source pipeline, integer paise, explicit invariants, relationship provenance, visible exceptions, reproducible synthetic fixtures, and separately reported throughput/accuracy. The current 75-case, 693-row demo achieves 257/257 expected relationship identities, 53 reconciled cases, 7 pending cases, and 15 exceptions. That is 70.67% straight-through case reconciliation, with 100% fixture edge precision and recall; these are different denominators and should remain separately visible.

The current 100% fixture result is not evidence of financial correctness on unseen data. Scenario prefixes drive SLA outcomes, a reconciled batch can contain an unmatched order with a monetary discrepancy, component credits can exceed captured payment amounts, failed settlements can be signed off, and evaluator correctness ignores monetary allocations. These are submission-blocking correctness/credibility gaps. Correcting them and publishing the resulting less-perfect benchmark would be a much stronger Track 04 entry than adding additional finance tools.

## Reproduction artifacts

- `docs/review/reproduce_financial_findings.py`: generates isolated fixtures from the repository constructors, changes a single field or a bounded set of financial amounts, runs the real engine and evaluator, writes results. Run with the repo `.venv/bin/python` and `PYTHONPATH` pointing at repo root.
- `docs/review/financial-reproduction-results.json`: full observed case states, invariant outcomes, cash position, and corrupted-report metrics.
- `docs/review/reproduce_cli_findings.py`: empty/mismatched prediction CLI safety-gate reproduction.
- `docs/review/empty-evaluation-result.json` and `empty_eval.md`: actual CLI output.

The findings below distinguish executed reproductions from inspection-only improvements. P0 means fix before presenting the correctness claim; P1 means material correctness or credibility gap; P2 means valuable depth and scalability work.

## P0 — Scenario identifiers determine SLA status and cash eligibility

Evidence: `services/reconciliation/exceptions.py:82` checks whether every settlement ID starts with `SET_T`. `classify_case` discards its `policy` argument at line 134 and returns `PENDING_WITHIN_SLA` using that prefix at line 139, before checking the required invariants. `services/reconciliation/orchestrator.py:238` repeats the prefix check; line 263 sets the residual to zero for that synthetic prefix, and line 275 suppresses missing-bank evidence. The engine receives no explicit reconciliation `as_of` instant.

Executed reproduction: timing scenario 31 with settlement `SET_T0031` is pending, has residual 0, and contributes 47,518 paise to in-transit/safe cash. Consistently rename only the settlement ID and component references to `OPAQUE_SETTLEMENT_31`; keep amounts, dates, UTR and all other facts identical. The same case becomes `ACTIONABLE_EXCEPTION / BANK_CREDIT_MISSING`, residual 47,518, and safe cash falls to zero. The benchmark ground truth is therefore partly recoverable from identifiers.

Related coupling: `orchestrator.py:133` derives evaluator case IDs with a table of scenario-specific patterns (MAL, MS, MN, FV, SP, CB, R, H, T, BATCH, AMB). This is not itself evidence of amount fraud, but it prevents a truly identifier-independent benchmark and can conceal case grouping errors when multiple records share synthetic pattern fragments.

Required correction: inject one explicit `as_of` timestamp into the run, bind policy/calendar and timezone, derive capture/settlement/bank deadlines from financial timestamps, and compute pending/overdue solely from deadlines and status. Remove synthetic prefixes from production logic. Use opaque randomized source IDs and evaluator-side source-entity alignment rather than importing scenario naming conventions into the engine.

Acceptance: consistently renaming IDs never changes states, cash buckets or amounts. At `deadline−1s` missing receipt is pending, at `deadline+1s` it is overdue; test holiday, weekend, cutoff, timezone boundaries and late arrival. Failed fee/currency/lifecycle invariants must not disappear merely because a bank event remains within SLA.

## P0 — Batch completeness is tested by relationship type, allowing false sign-off

Evidence: `services/reconciliation/exceptions.py:43` asks only whether at least one order-payment, payment-settlement and settlement-bank edge exists in a case. `services/reconciliation/invariants.py:125` checks amounts only on accepted order-payment edges; rejected/missing edges are skipped. Candidate grouping at `orchestrator.py:116` unions order/payment and payment/settlement candidates even when candidate prechecks rejected them. No required invariant checks every monetary source's allocation coverage, and there is no case-wide merchant invariant.

Executed reproduction: baseline generated batch 21 has four orders, nine evidence edges and 475,505 paise confirmed bank cash. Increase the first order amount by 1,000 paise. Its exact order/payment edge is rejected, so evidence count falls from nine to eight. The whole batch still returns `RECONCILED`, residual zero, **all twelve invariant results passing**, no exception. Independently changing that order's merchant to `ANOTHER_MERCHANT` has the same result.

Impact: the state claims the economic case is closed even though one underlying order is not reconciled and can belong to another merchant. The happy-path unit tests do not protect the central Track 04 accuracy claim.

Required correction: verify per-record completeness, cardinality, merchant/account/currency scope and aggregate gross conservation. Every material unmatched/rejected source relationship must remain a visible open obligation or subcase; a single accepted edge cannot prove the remaining records. Separate case grouping from acceptance decisions, and carry rejection reasons into classification.

Acceptance: change one amount or merchant in each position of batches of 2, 5 and 50 payments; none can be signed off, the affected row is identified, and the exact residual is explained. Missing and duplicated obligations fail similarly. Unrelated clean cases remain reconciled.

## P0 — Settlement payment components are never reconciled back to capture amounts

Evidence: `services/reconciliation/candidates.py:191` sums signed components per payment/settlement; candidate validation explicitly sets `amount=True` at line 214. `invariants.py:149` checks only that component sum equals settlement net, and `invariants.py:190` checks settlement net against bank allocation. There is no invariant equating payment-type component credits to the captured amount, or capping net adjustments by the available lifecycle amounts. `rules.py:287` only registers monetary allocation availability for settlement-bank relationships.

Executed reproduction: on clean case 1, add 1,000 paise to its payment component, settlement net and bank amount. Leave order and captured payment unchanged. Engine still emits `RECONCILED`, all invariants pass, and confirmed cash rises from 236,481 to 237,481 paise. The extra 1,000 paise is not tied to a captured payment or an explicit adjustment.

Required correction: enforce a per-payment conservation equation with separately typed gross capture, fees, tax, refunds, reversals and reserve movements. Validate source references, signs, lifecycle state, allocation amount and balance across all relationships. Explicit unknown credits can be observed in bank but cannot complete the payment lifecycle without a distinct explanation.

Acceptance: independently perturb gross component, refund, tax, fee, direction and source-event linkage by one paise; unexplained combinations must be rejected. Balanced-but-wrong intermediary amounts cannot pass simply because settlement and bank agree.

## P0 — Evaluator scores edge identities, not financial allocations or cash amounts

Evidence: `evaluator/metrics.py:15` omits `allocated_amount_paise` from the edge key. `monetary_reconciliation_rate` at line 140 looks only at predicted/expected `RECONCILED` state and then adds **ground-truth** gross amounts. Neither predicted gross nor predicted net is compared to truth. Cash bucket accuracy compares only bucket labels, not bucket amounts. Residual metrics at lines 205 and 214 trust the predicted residual rather than comparing to expected residual.

Executed reproduction: take the full demo prediction, set every edge's allocation to zero, every predicted gross to −999,999,999 and every predicted net to +999,999,999. Precision, recall, F1, state accuracy, exception accuracy, cash bucket accuracy and monetary reconciliation rate remain identical to the original report, with false-positive count zero. The original monetary rate is 0.7642; that is gross-weighted state coverage, not an amount-correctness measure.

Required correction: retain identity precision/recall but add exact allocated-paise precision/recall, per-case amount/residual error, total cash error, direction correctness, and coverage of all required obligations. A fully reconciled true positive should require the correct state **and** complete/correct required allocations **and** zero unexplained residual. Publish amount-weighted false-positive exposure separately.

Acceptance: corrupt any amount by one paise and the relevant money metric must fail; move an edge to the wrong case and grouping coverage must fail; remove an edge from a reconciled case and exact-case accuracy must fall. Report numerators and denominators for all metrics, including invalid and pending records.

## P1 — Evaluator accepts duplicate/unknown predictions and a false safety pass

Evidence: `evaluator/metrics.py:83` iterates the prediction list but divides by unique truth IDs. The same bug exists in bucket accuracy and monetary reconciliation rate. `false_positive_count` at line 163 ignores unknown predicted IDs (`and tc`). `hidden_row_count` at line 197 actually counts missing **cases**, not source rows. `evaluator/schemas.py:32` does not validate unique case IDs, nonnegative record counts or positive finite durations. `evaluator/cli.py:76` parses `--manifest` but never uses it. CLI lines 125–135 compute metrics without checking dataset identity, checksums, input counts or run provenance. Its only gate at line 163 is false-positive count. API evaluation does have a dataset ID check (`services/evaluation/service.py:49`); the CLI weakness should not be incorrectly attributed to that API path.

Executed reproductions:

- Duplicate every predicted case: case-state accuracy becomes 2.0 and monetary rate 1.5284 (152.84%).
- Append an unknown case marked reconciled: false-positive count remains zero.
- CLI receives zero predictions with a completely wrong dataset ID, 1 billion self-reported rows and duration 1 microsecond: exit code 0, “All safety checks passed,” recall 0, hidden case count 75, throughput 10^15 rows/sec.

`make verify-claims` has stronger recall/residual thresholds than the standalone CLI, but consumes the same amount-blind metrics and does not establish uniqueness, unknown-ID handling or true row coverage. Do not present the CLI's safety string as comprehensive verification.

Required correction: validate report and manifest integrity before scoring; reject duplicate case/edge IDs, unknown entities/cases and mismatched source checksums; use a single aligned universe; derive source counts from ingested/manifest records; separate unmeasured throughput from measured throughput. Gate missing records, unknown signoffs, financial false positives and unexplained residuals. Report empty precision as N/A alongside zero coverage, not a visually perfect score.

Acceptance: every reproduction above must fail validation or the safety gate. No rate may exceed [0,1]. Every source row must be accounted for as accepted, rejected, duplicate, or unresolved with provenance. CLI/API scoring contracts must agree.

## P1 — Cash calculation double-deducts refunds, chargebacks and reserve holds

Evidence: `generator/scenarios.py:659` already computes refund settlement net as gross minus fee minus tax minus refund. Reserve net similarly subtracts reserve at line 963. `services/cash_position/service.py:20` uses net settlement amount for bank-confirmed/in-transit cases, then lines 66–78 subtract every historical refund, chargeback and reserve component again as if each were a future obligation. These records have no scheduled/open/settled lifecycle filter.

Executed reproduction: generated full-refund case R0042 has gross/refund 366,199 paise and already-netted bank amount −8,641 paise. It is reconciled; `bank_confirmed_paise` is −8,641 but `safe_cash_paise` is −374,840. The 366,199-paise refund was deducted twice. In the 75-case demo, the second deductions total 2,220,185 paise (refunds 1,271,184 + disputes 824,128 + reserves 124,873).

Required correction: distinguish historical netted movements from outstanding future obligations. Define observed bank movement, reconciled receipts, in-transit receivables, restricted cash and upcoming obligations separately. Calculate available cash from an opening balance plus signed bank movements, subtract only obligations that have not already affected the bank/net settlement. If opening balance and outflows are absent, label the result as modeled settlement proceeds rather than the merchant's complete bank cash position. Primary review reviews forecasting separately.

Acceptance: a fully settled refund is counted once; a newly scheduled refund affects forecast once until settlement, then changes representation without a second deduction. Apply equivalent tests to chargebacks, reserve holds and reserve releases. Reconcile closing cash exactly to opening plus signed movements.

## P1 — Lifecycle validation ignores settlement status; amount fallback ignores known reference conflicts

Evidence: `services/reconciliation/invariants.py:257` checks payment status only, despite settlement status being parsed. No settlement lifecycle consistency check exists in the full invariant list at line 360.

Executed reproduction: changing clean case 1 settlement status from `processed` to `failed` while preserving financial amounts still yields `RECONCILED` with all checks passed. At minimum this is contradictory source evidence requiring a visible exception, even if the bank movement itself is observed.

Evidence for reference conflict: `services/reconciliation/candidates.py:220` checks exact UTR positively, but lines 272 onward generate an amount/date candidate even when both UTRs are present and disagree. The fallback contains no explicit identifier-conflict rejection.

Executed reproduction: change clean case 1 bank UTR to `DIFFERENT_VALID_UTR`, remove matching reference narration and keep amount/date. It is fully reconciled through unique-amount fallback. Whether the true bank credit belongs elsewhere is unobserved in this probe, but the definite source-reference contradiction is currently discarded.

Required correction: model settlement status/timestamp consistency and explicit negative evidence. A missing reference can permit a conservative fallback; a conflicting trusted reference should block automatic sign-off or require independently stronger evidence with recorded rationale.

Acceptance: all failed/initiated-with-invalid-processed-at combinations remain visible. Add equal-amount unrelated credits with conflicting UTRs and correct credits arriving late. Manual review must be able to see why a candidate was blocked.

## P1/P2 — Synthetic breadth and source validation overstate some supported cases

Inspection-supported findings:

- “Split settlement” is actually one settlement with a reserve hold (`generator/scenarios.py:949`), not one settlement paid through multiple bank credits. `services/reconciliation/rules.py:257` is an explicit no-op for one-to-many payout splitting. `many_to_one_aggregation` at line 247 is also a no-op and explains that existing membership handles many payments to one settlement; it does not implement several settlement payouts aggregating into one bank receipt. Describe supported cardinalities precisely.
- Full-refund and chargeback scenarios can generate negative `amount_paise` with direction `CREDIT` (`generator/scenarios.py:740`, `:898`). The source models in `generator/schemas.py` accept unrestricted signed integers, so invalid magnitude/direction combinations reach the engine. A robust canonical statement model should use positive magnitude plus direction, or one signed amount consistently, with distinct allowed negative settlement-net semantics.
- The stress distribution intentionally contains only clean and batched cases. That scope is documented and honest, but it establishes throughput only on easy/common paths, not throughput at a representative exception rate.
- Generator seeds vary amounts/dates but preserve scenario grammar, identifiers, provider/account, fee policy and available evidence. Reproducibility is useful; repeated scores on this family are not an independent holdout.
- Narration parsing assumes synthetic prefixes `PAY_`, `SET_`, `ORD_` (`services/normalization/identifiers.py:10`); real provider format support is not demonstrated. Track 04 needs synthetic records, so live connector breadth is optional and lower priority than correctness.
- The “control totals” invariant (`invariants.py:295`) only checks `invalid_reasons`; it does not compare statement count/totals or opening/closing balances. Control-total wording should match this narrower implementation until those checks exist.

Acceptance additions: opaque IDs; two merchants/two accounts; legitimate identical amounts; conflicting/missing UTRs; separate capture/refund/reversal events; multi-credit settlements; several settlements per bank credit; partial capture; missing/unexpected component; normalized identifier collision; late bank arrival; duplicate retransmission and conflicting duplicate; header-only/corrupt files; negative bank magnitude; balanced-but-wrong component totals; amount threshold boundaries; mixed valid/invalid rows; explicit as-of. Assign every fixture an expected exception or exact closure; do not force-match hard cases merely to increase STP.

## P2 — Scalability and latency reporting need more precise scope

Inspection evidence: candidate generation loops over every settlement and every bank row (`candidates.py:220`), so it performs O(S×B) pair checks before filtering. Case construction scans all candidates per group (`orchestrator.py:160`, `:297`); per-case invariants repeatedly scan global edge lists (`invariants.py:20`, `orchestrator.py:229`). Evidence allocation checks scan existing edges (`evidence.py:99`). These structures can become quadratic even when accepted matches are nearly one-to-one. No scaling measurements were run by this reviewer; the integrated review contains the official stress result.

`case_latency_ms` begins only after candidate generation and matching (`orchestrator.py:374`) and ends after case verification/classification (`:396`). `scripts/stress_test.py:48` labels percentiles “case latency.” These are verification-stage service times, not end-to-end individual case latency. Whole-run throughput is independently measured around `run_reconciliation`, which is the valid measurement for the stated engine scope. Database persistence and AI calls are excluded from that benchmark and should have separate end-to-end numbers.

Improvements: index exact references by `(merchant, account, currency, reference)`, use amount/date windows for residual candidates, build adjacency indexes once, memoize case entity sets, cap candidate fanout and record overflow exceptions. Benchmark 100/1,000/10,000 cases across clean and mixed-exception distributions; report wall time, rows/sec, cases/sec, candidate pair count, peak memory, environment and median/p95 over repeated fresh runs. Rename current case latency to “case verification latency.”

## Strengths worth preserving

- Integer paise and deterministic arithmetic avoid floating-point reconciliation drift.
- Stronger-to-weaker candidate rules, ambiguous candidates and evidence edges create a reviewable architecture.
- Evidence provenance includes rule/version, source fields, decision level, actor and run identity.
- Verification-first classification is directionally correct; adding missing obligations/invariants is a focused improvement rather than a rewrite.
- Rejected rows remain visible in normalized records and invalid cases rather than being silently dropped from a clean dataset.
- Structured exceptions contain reason, amount, severity, owner, missing evidence and suggested next action.
- Separate pending/at-risk/unresolved buckets communicate more than a binary “matched” flag, once derived from actual facts.
- Scenario breakdowns, baseline ablation and reproducibility scripts are good submission artifacts once the evaluator is independently robust.
- AI suggestions are constrained to precomputed candidates and distinguish suggested evidence from verified financial allocation; keep deterministic sign-off authority.
- Property tests cover allocation overrun, reproducibility and row order. Extend them with identity-renaming, one-paise mutation, duplicate and conservation properties rather than only increasing test count.

## Track 04 differentiators with best return

1. **A tamper-resistant evaluation bundle.** Fresh judge-selectable seed, opaque IDs, independent oracle, input/policy/code checksums, exact denominator disclosure, blind cases, financial false-positive amount, unresolved exception CSV and reproducible command. Let the judge rename IDs or change one paise and watch controls catch it.
2. **An actual closing loop.** Load 500+ rows, reconcile, explain every remainder, add late bank evidence or correct one disputed fee, rerun only affected cases, verify changed cash, and export final reconciliation workpaper plus a persistent honest exception queue. Never make “approve” mean “ignore a failed monetary invariant.”
3. **Cash roll-forward and evidence lineage.** Opening balance + signed cash movements = closing balance; explain each bucket and show precisely how a refund moved through capture, settlement, bank and cash forecast without double counting.
4. **Risk-ranked review productivity.** Rank unresolved cases by amount, age and owner/action; batch-review safe homogeneous exceptions; show operator minutes/decisions saved alongside exact verified accuracy. Optimize verified closure under a zero-financial-false-positive constraint, not headline STP alone.
5. **Replayable failure demonstration.** A short deterministic demo in which provider IDs, amount conflicts, bank delay, duplicates and AI failure each produce a correct conservative outcome; then resolve one with new evidence. This directly answers “verification capacity is the bottleneck.”

Finish P0/P1 financial and evaluator fixes before expanding forecasting, chat, tax or provider integrations. Preserve an honest known-limitations section. The strongest submission is one a skeptical reviewer can actively challenge and still trust.
