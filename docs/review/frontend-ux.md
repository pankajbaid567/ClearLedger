# ClearLedger frontend, UX, demo, and recruiter-readiness review

Reviewed 5 September 2026. Scope: source review of all principal pages, shared table, evidence drawer, human-review dialog, claims modal, Q&A, cash forecast and tax audit cards, frontend API client, README, demo script, Docker files, and Playwright tests. Existing backup control-room screenshot inspected; it predates the current source styling, so it is not evidence of the current rendered UI. Primary review independently ran frontend checks and a live Playwright flow; results are recorded below. No repository files changed by this review.

## Assessment

The product already has a coherent Track 04 story: five source ledgers become 75 economic cases, accepted matches have an evidence graph and arithmetic receipt, unresolved cases have an owner and next action, and human review does not automatically release cash. That is a strong foundation. The biggest obstacle to a credible top-tier submission is that several UI proof badges claim more than their underlying data actually establishes. Correctness of the presentation must be treated as part of reconciliation correctness.

The next investment should be trustworthy measurement, working evidence drilldowns, and a complete exception-resolution demonstration. Adding another broad finance feature before these fixes would weaken focus.

## Must fix before judging

### UX-01 — Claims Ledger reports success without checking the claims (P0)

Evidence: `apps/web/components/ClaimsLedgerModal.tsx:35` allows only PASS/VERIFIED statuses; lines 39–149 embed perfect demo measurements and statuses; lines 152–295 embed a perfect scenario table; lines 327–365 replace some measurement strings with live values but preserve the prewritten status. Lines 414 and 421 label this “10 of 10 Verified” and “Live mathematical proof.” Lines 594 and 632–640 render the static scenario matrix and perfect footer. `RunShell.tsx:158,216` and control-room `page.tsx:208,301` repeat the unconditional badge.

Impact: a custom upload, missing evaluation, loading state, evaluator API failure, low recall, or nonzero false positives can still be shown as 10/10 verified. The scenario view is unrelated to the active run. This directly undermines the hackathon's honest-measurement requirement.

Fix: return typed claim results from a measurement artifact/API containing claim ID, status (PASS/FAIL/NOT_RUN/UNAVAILABLE), actual value, threshold, unit, denominator, dataset checksum, engine commit/version, method, and measured timestamp. Compute badge totals from those results. Distinguish per-run evaluation from a repository benchmark. Render `evaluation.scenario_breakdown`, not `SCENARIOS_DATA`. Remove demo fallback numbers from active-run views.

Acceptance: load a run with precision 0.95, false positives >0, an unevaluated upload, and a failed evaluation request. None may retain the corresponding passing status or show fabricated numbers. Opening the modal while loading must show pending proof, not success. Changing the active dataset must change or invalidate all scenario rows.

### UX-02 — Evidence equation can mark absent bank cash as matched (P0)

Evidence: `EvidenceDrawer.tsx:180–194` derives component lines with `passed: true`, selects the first non-debit bank record, and converts a missing bank to zero. `EquationCard.tsx:23,59–65` marks Bank Credit matched whenever case residual is zero, without checking an accepted bank relationship or equality of the displayed amounts.

Concrete fixture: `out/reconciliation_report.json` contains CASE_T0031 with PENDING_WITHIN_SLA, net 47,518 paise, residual 0, and no settlement-bank relationship. The current component would show Bank Credit ₹0.00 with a “Matched” icon despite no bank confirmation.

Fix: use an authoritative typed equation receipt with bank-evidence availability, accepted relationship allocations, component-level validation status, aggregate bank amount, equation-specific residual, and case decision. Missing bank evidence must be “Not received / within SLA,” never a matched zero. A raw component is a fact, not automatically a passed verification.

Acceptance: test clean, pending-no-bank, fee variance, ambiguous bank candidates, batched deposits, and split settlements. Every displayed pass must cite a corresponding passed check; the arithmetic displayed to the user must tie exactly.

### UX-03 — Tax credit claims exceed the inputs and implementation (P0)

Evidence: `TaxAuditCard.tsx:37–57` claims GSTR-2B audit readiness and matching against claimable ITC; lines 113–126 say “Claimable GSTR-2B ITC” and “Verified eligible tax credit.” `ClaimsLedgerModal.tsx:141–148` claims statutory SGST/CGST/IGST breakdown verification. `services/cash_position/tax_audit.py:80–207` only compares payment amounts, fee components, and tax components to configured arithmetic and sets claimable amounts from that comparison. It has no GSTR-2B statement, tax invoice, supplier GSTIN, period matching, eligibility evidence, or SGST/CGST/IGST split input.

Fix: within current scope rename this to “Gateway fee and tax arithmetic checks,” label tax amounts as recorded/expected/disputed under the synthetic policy, and remove ITC eligibility and GSTR-2B certification. A real tax-line matcher would need a separate explicit input and evidence model. This finding concerns missing application evidence; it does not rely on a legal interpretation.

Acceptance: no UI or documentation may claim statutory eligibility or external statement matching unless the required external evidence is present and linked. A policy rate change must update labels as well as calculations (2% and 18% are currently hardcoded repeatedly in the card).

### UX-04 — Important evidence drilldowns do not filter anything (P1)

Evidence: `SettlementQACard.tsx:171` links cited case IDs using `?search=`; `TaxAuditCard.tsx:182` uses `?code=FEE_VARIANCE`; its discrepancy rows at line 222 use `?search=`. `cases/page.tsx:95–119` initializes only state/bucket/AI/human URL filters, initializes codes to an empty array, and never reads `search`. The DataTable search is private internal state (`DataTable.tsx:37`).

Impact: “Cited Case Evidence” and “Inspect Cases” land on all cases, breaking the core evidence promise during a demo.

Fix: make the URL the canonical state for search, exception code, state, bucket, and selected case. Support a direct `case` parameter that opens the evidence drawer. Preserve this state through back/forward navigation and shared links; local initializers alone do not synchronize with later URL changes.

Acceptance: every Q&A citation opens precisely its case; fee-variance inspect only shows fee-variance cases; reload and browser back preserve the selected view; clear filters removes every applied query filter.

### UX-05 — Review updates leave related panels stale (P1)

Evidence: `ReviewActionDialog.tsx:69–77` invalidates only cases, case, cash, and audit. Cash page subscribes separately to `cash-forecast` and `tax-audit` (`cash/page.tsx:85–92`). Metrics, evaluation, receipt, evidence, and candidate queries are also independent. `providers.tsx:12–14` sets a 15-second staleTime but disables refetch on focus; staleTime is not a timer that automatically refreshes a mounted panel. Cash page says “Updated after every decision” at line 317.

Fix: have mutation responses include the new run revision and all affected resources, or systematically invalidate relevant derived resources. Define baseline benchmark metrics versus current reviewed-state metrics explicitly. Do not silently combine an earlier STP number with new case-state denominators. Display snapshot revision/time and update-in-progress state.

Acceptance: perform approve/reject/defer/assign while the cash page and evidence drawer are open. Changed cash buckets, forecasts, row contribution, receipt, owner, and audit must agree without reload. Verify with a second tab as well. Historical baseline evaluation must remain clearly labeled as historical rather than appearing live.

### UX-06 — Cash labels and contributor totals need a single financial meaning (P1)

Evidence: `cash/page.tsx:234–252` defines “Safe Cash Now” as bank_confirmed_paise. Backend `services/cash_position/service.py:69–77` defines safe_cash_paise as bank confirmed plus transit minus refund/chargeback/reserve components. Thus UI and API use different definitions of safe cash. Bucket `_case_amount` at service lines 21–33 uses absolute residual, net, or gross for risk/unresolved; cash contributor rows at page lines 148–154 always show net amount under “Controlled Amount.” The sum of those rows need not equal the selected bucket amount.

Fix: agree on precise fields: reconciled batch bank inflows, settlement in transit, unexplained exposure, recorded deductions, projected inflows. Do not describe a sum of batch credits as a complete spendable bank balance without opening balance and other outflows. Return each case's exact bucket contribution. Clarify whether deductions are already reflected in settlement net before displaying/subtracting them. Primary review's backend review should resolve the arithmetic contract.

Acceptance: every cash headline has a documented equation and a drilldown whose contribution column sums exactly to it. Include refund and reserve examples that catch double subtraction. Export and UI use the same terms and values. The snapshot shows its as-of time, source cutoff, and currency.

### UX-07 — Aggregate cards link to incomplete subsets (P1)

Evidence: control-room `page.tsx:96–107` counts five exception/review states plus invalids; line 252 links “Open exception queue” only to ACTIONABLE_EXCEPTION. The Exceptions chart link at lines 454–461 does the same. Cash `page.tsx:277–294` shows At Risk + Unresolved but links only to AT_RISK; Near-Term Controlled shows Bank + Transit but links only to Transit. STP card links to human=pending (all non-reviewed cases), not just auto-reconciled cases.

Fix: use combined filters or explicit drilldown pages that preserve the card's exact numerator/population. A count or amount card is an accounting statement, and its linked set should reconcile to that statement.

Acceptance: for every headline, linked row count and contribution sum equal its advertised count and amount, including approved/deferred/rejected/invalid cases.

### UX-08 — Failure states can look like missing data or endless loading (P1)

Evidence: `EvidenceDrawer.tsx:303` shows skeletons whenever caseData is absent, even after a terminal case-query error; errors from evidence, receipt, candidates, and audit have no dedicated handling. Missing receipt appears as “Checks failed” rather than “Could not load checks.” Cash page lines 297–311 silently removes forecast/tax panels after request failure. `getAudit` at `lib/api.ts:520` retrieves only the first 500 events and supplies no pagination handling, so a large run's timeline is incomplete.

Fix: provide per-panel loading/empty/error/partial states and retry controls. Treat unavailable proof separately from failed proof. Page or cursor through audit events, or fetch a case-scoped audit endpoint. Show event totals and completeness. Export downloads need an explicit failure path instead of navigation to raw server errors.

Acceptance: inject 404/500/timeouts individually for case, receipt, graph, forecast, tax and audit endpoints. Each must show a useful retry state, no false pass/fail, and no infinite skeleton. A run with >500 audit events must expose all events and late case actions.

## Other significant usability and credibility improvements

1. **Use real progress and state.** Setup `page.tsx:136–139` advances the displayed pipeline stage every 520 ms, independent of backend progress; it claims AI Analysis even with AI disabled. Control room at line 190 hardcodes Complete. Use authoritative run-stage events or an honest indeterminate “Processing” display; distinguish reconciled, evaluating, completed, and failed. A refresh during a long run should reconnect to it. Manual upload currently also always invokes evaluation at setup line 145; arbitrary datasets need an unevaluated-but-completed path.

2. **Expose actionable validation.** The API already supplies file errors, accepted/rejected counts, quality, and missing sources (`lib/api.ts:42–60`), but setup mainly shows counts and a generic success/error message. Existing result cards get green file icons whenever a result exists (`app/page.tsx:242–246`), even for poor quality. Provide row number, field, original value, rejection reason, downloadable reject CSV, template downloads and a corrected-file retry. Guard concurrent demo loading/upload/file replacement to avoid UI state races; changing files remains enabled during operations.

3. **Correct SLA aging.** Overview `page.tsx:145–147` marks exceptions overdue from an exception-code substring or browser-time age of the database case creation. Cases `page.tsx:133,352–355` use the same created_at age. This is time since run creation, not payment age or contractual bank due time. Calculate business-day due status at the backend against an explicit run as-of timestamp and display both transaction age and time since review assignment if useful.

4. **Make AI status factual.** `RunShell.tsx:170–178,226–236` treats existence of ai_model as “AI Ready,” which is only configuration, not successful provider operation. Existing backup screenshot visibly combines AI ready with deterministic-only and AI-unavailable warnings. Show Disabled, Available, Partial/fallback, or Failed from measured execution metadata. Q&A `SettlementQACard.tsx:154–157` always shows Fact Verified without reading response.grounded; avoid the unconditional “Zero arithmetic hallucinations” claim at line 74. Suggested case prompts at lines 23–29 should come from current-run cases, not fixed demo IDs.

5. **Preserve state and provenance.** Q&A history is component-local, unpersisted, not versioned, and not explicitly reset when runId changes. Review dialog reason/note/owner/date states are not reset on open or case changes (`ReviewActionDialog.tsx:41–49`), so old rationale can carry into another decision. Clear case-specific state or scope it by case ID and version; show source snapshot timestamps on answers.

6. **Make modal accessibility complete.** Claims modal's comment says focus trap but effect at lines 367–380 only handles Escape and initial focus. Review dialog does the same at lines 49–62. Evidence drawer is an aside with no dialog semantics, focus entry/containment/return. Introduce a shared dialog primitive, restore trigger focus, prevent background interaction, and support nested dialogs. DataTable overrides native row semantics with role=button at line 176; use a real case link/button within the row. Give Q&A input a persistent accessible label (`SettlementQACard.tsx:104–112`). Use aria-pressed/tab semantics for view/day selectors. Test keyboard-only flow, not just mouse clicks.

7. **Improve table and mobile task design.** Every DataTable has min-width 940 px (`DataTable.tsx:122`), including simple cash contributors. Horizontal scrolling avoids viewport overflow but makes every mobile review a long lateral scan. Pin case ID/state, prioritize amount and next action, and offer compact cards at narrow widths. Current six-hundred-to-eight-hundred-line components repeat styles and labels extensively; extract common layout/status/metric contracts after correctness fixes.

8. **Make evidence complete on demand.** SourceRecord silently shows only the first eight raw fields and first eight normalized fields (`EvidenceDrawer.tsx:61,92`). Provide “show all fields” and source filename/row number/checksum/normalization rule links so a judge can inspect arbitrary supporting facts. EquationLine uses label as React key (`EquationCard.tsx:35`), so multiple identical component types need stable component IDs.

9. **Avoid silently asserting policy facts.** Forecast card lines 328–331 claims Razorpay T+1/T+2 cycles and RBI calendar awareness; show “Synthetic policy vX” and the loaded holiday file/coverage. Expose deterministic forecast assumptions, overdue inflows, known outgoing obligations, and alternative delay scenarios. An inflow schedule is useful, but “Closing Safe Cash” should not imply a full business forecast without the relevant expense and opening-balance inputs.

## Tests and demo materials

The existing serial Playwright suite is designed to cover the actual demo path, queue pagination, evidence, approval remaining unverified, rejection, cash bucket changes, CSV download, and compact viewport overflow (`apps/web/tests/demo-flow.spec.ts`). That is stronger than screenshot-only verification, but the current run did not complete the suite.

Integrated verification: frontend lint, typecheck and production build passed. On Playwright retry, the demo/reconciliation/control-metrics test passed; pagination test failed because `pagination-status` was absent, leaving seven subsequent tests skipped. The first attempt encountered `net::ERR_NETWORK_IO_SUSPENDED` while the database run was actually completed; that first failure is environmental/nonconclusive and should not be presented as a confirmed application defect. Direct API demo → reconcile → evaluate returned 201 → 200 → 200. A fresh Git archive Docker build actually failed on missing `prompts/` and `evaluator_private/`. The current Playwright screenshot also confirmed AI_ENABLED=false while the shell advertised “AI Ready” / “AI Analyst Ready” based on populated model metadata.

Gaps and drift:

- Tests at `demo-flow.spec.ts:37,40,53,58,69` require `pagination-status` with “Page 1 of 5” or “All N matching records”; current `DataTable.tsx:218–237` renders only `1 / 5` and has no such test ID. Primary review's live test run confirmed this failure.
- Test expects “Settlement equation” at line 93 while current EquationCard renders “Settlement Equation.” Exact text matching may fail depending on locator normalization. This later test was not reached; the mismatch remains an inspection finding.
- Main suite does not exercise claims failure/unavailable states, tax links, Q&A citation routing, forecast filtering/cache invalidation, manual upload/reject repair, >500 audit history, back/forward filters, keyboard focus or mixed currencies.
- `docs/DEMO_SCRIPT.md:84` expects approval to return an invariant error; current UI and tests intentionally record APPROVED_PENDING_VERIFICATION. Update the narrative and rehearse the implemented result.
- Demo script line 25 promises dataset checksum before processing, but setup does not render it. Step 1 refers to selecting a Demo dataset option that current UI does not have. Align scripts and screens.
- Existing screenshot backup predates current styling and does not include claims/Q&A/forecast/tax. Screenshots are captured immediately after visibility assertions (`demo-flow.spec.ts:183–209`), which can capture charts during animation: the inspected backup has an empty state donut and short, unfinished bars. Disable chart animation for deterministic capture or wait for chart-specific readiness before exporting.

## Clean-clone and publication readiness

The ignore/source/lockfile publication fixes below were completed and verified in commits c76a3cd and 36794ac. The Docker and missing-prompt blockers remain open:

- Generic `lib/` ignore excluded actual frontend `apps/web/lib/api.ts` and `format.ts`; change to `/lib/` or explicitly include frontend source.
- `uv.lock` and `.dockerignore` were ignored even though they are required reproducibility/build inputs.
- `.next-e2e/`, `playwright-report/`, and `*.tsbuildinfo` should be excluded as generated artifacts.
- `.env` contains a nonempty API key and must remain excluded. Existing secret scanner plus additional token-pattern checks passed for publishable text; only demonstration Docker password was additionally flagged. No secrets printed.
- `apps/api/Dockerfile:19` copies absent `prompts/`; line 22 copies ignored `evaluator_private/`. A clean clone's Docker build cannot complete as written even if local generated assets happen to make a developer checkout work. Generate safe synthetic evaluator fixtures during an explicit build/setup step, and separate runtime engine access from evaluator truth.
- README container-only command is `docker compose up --build`; verify it from a fresh clone with empty generated data and without the developer .env. A documented fresh-clone smoke test is stronger evidence than a working local screenshot.

## Recommended submission experience

1. Lead with one run summary above the fold: **693 source rows → 75 cases → 53 auto-reconciled, 7 within SLA, 15 requiring review/correction**, each number read from the active run and linked to its exact set. Show precision/recall denominators beside coverage, false positives and unexplained amount. Use the latest measured numbers if this fixture changes.
2. Offer “Run a fresh batch” with seed + dataset manifest and a second held-out/adversarial batch. A reviewer should see the system cope with a different batch, not only the supplied 75-case fixture.
3. Prove one clean lifecycle, then show an ambiguous candidate that remains unresolved with specific missing evidence. Attempt approval and demonstrate that review cannot manufacture verification.
4. Complete one repair loop: upload missing bank evidence or correct a malformed source via a new immutable version, re-run, and show the exception becoming verified only after deterministic checks pass. Preserve before/after evidence and cash impact. Assign/defer alone is useful triage but does not demonstrate closing the exception.
5. Show “what remains unresolved” as an exportable worklist with case ID, exact money at risk, reason, missing evidence, owner, due time, allowed next action and source links. Provide run-to-run diff and review history.
6. Finish with a generated proof packet: machine-readable predictions, full exceptions, measured evaluation, scenario matrix, reproducible command, dataset/engine checksums, environment and elapsed time. Add a short demo video and architecture graphic to README, sourced from the verified current build.

Suggested sequence: first fix unsupported proof claims and evidence math, then drilldowns/cache/error handling, then the repaired-source closure path and fresh-batch proof. Broader tax or cash-planning extensions should follow once the settlement loop is demonstrably correct.
