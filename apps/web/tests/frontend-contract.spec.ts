import { expect, test, type Page } from "@playwright/test";

const runId = "11111111-1111-4111-8111-111111111111";
const timestamp = "2026-09-05T10:00:00Z";
const sourceTypes = ["orders", "payments", "settlements", "settlement_components", "bank_transactions"];
const run = {
  id: runId, status: "COMPLETED", policy_version_id: null, dataset_checksum: "synthetic-checksum",
  rule_set_version: "1", app_version: "test", ai_model: "configured-but-disabled", ai_prompt_version: null,
  policy_id: "demo", policy_version: "1", started_at: timestamp, completed_at: timestamp,
  duration_ms: 25, total_source_rows: 75, total_cases: 3, result_checksum: "result-checksum",
  failure_reason: null, created_at: timestamp, files: [], execution_revision: 1, review_revision: 0,
};
const makeCase = (id: string, code: string | null = null) => ({
  case_id: id, reconciliation_run_id: runId, case_state: code ? "ACTIONABLE_EXCEPTION" : "PENDING_WITHIN_SLA",
  decision_level: "DETERMINISTIC", gross_amount_paise: 50000, net_amount_paise: 47518, residual_paise: 0,
  currency: "INR", exception_code: code, exception_severity: code ? "HIGH" : null, amount_at_risk_paise: code ? 123 : 0,
  cash_bucket: code ? "AT_RISK" : "SETTLEMENT_CONFIRMED_IN_TRANSIT", cash_bucket_contribution_paise: code ? 123 : 47518,
  cash_contribution_basis: code ? "unexplained_residual" : "net_settlement", settlement_id: "SET_1", bank_receipt_state: "PENDING",
  owner_role: "settlement_operations", next_action: "Obtain bank evidence", ai_assisted: false, human_reviewed: false,
  created_at: timestamp, updated_at: timestamp, event_at: "2026-08-31T10:00:00Z", age_days: 5,
  sla_due_at: "2026-09-04T10:00:00Z", days_past_sla: 1, review_due_at: "2026-09-07T10:00:00Z",
});
const cases = [makeCase("CASE_FEE", "FEE_VARIANCE"), makeCase("CASE_PENDING"), makeCase("CASE_OTHER", "BANK_CREDIT_MISSING")];
const cash = {
  run_id: runId, currency: "INR", bank_confirmed_paise: 0, settlement_confirmed_in_transit_paise: 47518,
  expected_settlement_paise: 0, at_risk_paise: 246, unresolved_paise: 0, scheduled_refunds_paise: 0,
  known_disputes_paise: 0, known_reserve_holds_paise: 0, safe_cash_paise: 0,
  as_of_at: timestamp, execution_revision: 1, review_revision: 0,
  buckets: {
    AT_RISK: { bucket: "AT_RISK", amount_paise: 246, case_ids: ["CASE_FEE", "CASE_OTHER"] },
    SETTLEMENT_CONFIRMED_IN_TRANSIT: { bucket: "SETTLEMENT_CONFIRMED_IN_TRANSIT", amount_paise: 47518, case_ids: ["CASE_PENDING"] },
  },
};

async function mockAPI(page: Page, options: { evaluation?: "failed" | "missing"; shared?: boolean; receiptError?: boolean; heldProgress?: boolean; reconciliationFailureOnce?: boolean; validationInvalid?: boolean } = {}) {
  const calls: Array<{ path: string; method: string; authorization: string | undefined; idempotencyKey: string | undefined; body: string | null }> = [];
  let receiptError = options.receiptError ?? false;
  let reconciliationFailureServed = false;
  let reconciliationFailed = false;
  let reviewRevision = 0;
  let reviewDone = false;
  let waiting = false;
  let release: (() => void) | undefined;
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace(/^\/api/, "");
    calls.push({ path, method: request.method(), authorization: request.headers().authorization, idempotencyKey: request.headers()["idempotency-key"], body: request.postData() });
    const json = (value: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(value) });
    if (path === "/auth/config") return json({ mode: options.shared ? "shared" : "local_demo", authentication_required: Boolean(options.shared) });
    if (path === "/auth/me") {
      if (options.shared && request.headers().authorization !== "Bearer contract-test-token") return json({ error: { code: "UNAUTHENTICATED", message: "Access token invalid", request_id: "req-auth" } }, 401);
      return json({ subject: options.shared ? "finance.reviewer" : "demo.finance.operator", role: "admin", is_demo: !options.shared, permissions: ["read", "create", "review"] });
    }
    if (path === "/runs" && request.method() === "POST") return json(run, 201);
    if (path === `/runs/${runId}/files`) return json([]);
    if (path === `/runs/${runId}/validate`) return json({ run_id: runId, valid: !options.validationInvalid, required_sources_present: true, processing_permitted: !options.validationInvalid, missing_source_types: [], files: sourceTypes.map((source_type, index) => ({ source_type, filename: `${source_type}.csv`, quality: options.validationInvalid && index === 0 ? "INVALID" : "VALID", row_count: 15, accepted_count: options.validationInvalid && index === 0 ? 14 : 15, rejected_count: options.validationInvalid && index === 0 ? 1 : 0, control_total_paise: 50000, errors: options.validationInvalid && index === 0 ? [{ issue_type: "INVALID_AMOUNT" }] : [] })), total_rows: 75, invalid_rows: options.validationInvalid ? 1 : 0 });
    if (path === `/runs/${runId}/reconcile`) {
      if (options.reconciliationFailureOnce && !reconciliationFailureServed) {
        reconciliationFailureServed = true;
        reconciliationFailed = true;
        return json({ error: { code: "SERVICE_UNAVAILABLE", message: "Reconciliation worker temporarily unavailable", request_id: "req-reconcile-retry" } }, 503);
      }
      reconciliationFailed = false;
      if (options.heldProgress) { waiting = true; await new Promise<void>((resolve) => { release = resolve; }); waiting = false; }
      return json({ run_id: runId, status: "COMPLETED", total_source_records: 75, total_cases: 3, evidence_edges: 0, exceptions: 2, result_checksum: "result-checksum" });
    }
    if (path === `/runs/${runId}`) return json({ ...run, review_revision: reviewRevision });
    if (path === `/runs/${runId}/status`) return json({ run_id: runId, status: reconciliationFailed ? "READY" : waiting ? "RECONCILING" : "COMPLETED", stage: reconciliationFailed ? "READY" : waiting ? "MATCHING" : "COMPLETE", processed_records: reconciliationFailed ? 0 : waiting ? 19 : 75, progress_percent: reconciliationFailed ? 0 : waiting ? 37 : 100, started_at: timestamp, completed_at: reconciliationFailed ? null : timestamp, failure_reason: null });
    if (path === `/runs/${runId}/metrics`) return json({ run_id: runId, status: "COMPLETED", metrics: { total_predicted_cases: 3, total_source_records: 75, ai: { enabled: false, calls: 0, eligible_cases: 2, warnings: [] } } });
    if (path === `/runs/${runId}/cases`) return json({ items: cases.map((item) => reviewDone && item.case_id === "CASE_FEE" ? { ...item, case_state: "REJECTED_SUGGESTION", human_reviewed: true } : item), page: 1, page_size: 200, total: 3, pages: 1 });
    if (path === `/runs/${runId}/cash-position`) return json(cash);
    if (path === `/runs/${runId}/cash-forecast`) return json({ run_id: runId, as_of_date: "2026-09-05", currency: "INR", days: [], total_projected_inflow_paise: 0, baseline_safe_cash_paise: 0, projected_final_cash_paise: 0 });
    if (path === `/runs/${runId}/tax-audit`) return json({ run_id: runId, currency: "INR", total_cases_audited: 3, gross_payment_volume_paise: 150000, total_gateway_fee_paise: 100, expected_gateway_fee_paise: 100, fee_variance_paise: 0, total_tax_paise: 18, expected_tax_paise: 18, tax_variance_paise: 0, claimable_itc_paise: null, disputed_tax_paise: 0, tax_policy_pass_rate: null, fee_policy_pass_rate: null, discrepant_case_count: 0, unmatched_component_count: 0, discrepancies: [], itc_status: "UNAVAILABLE" });
    if (path === `/runs/${runId}/audit`) return json({ items: [], page: 1, page_size: 500, total: 0, pages: 1 });
    if (path === `/runs/${runId}/evaluation`) return options.evaluation === "failed" ? json({ run_id: runId, dataset_id: "adversarial", execution_revision: 1, evaluated_review_revision: 0, current_review_revision: reviewRevision, evaluation_scope: "IMMUTABLE_ENGINE_BASELINE", baseline_result_checksum: "result-checksum", aggregate: { relationship_precision: .5, relationship_recall: .4, relationship_true_positive_count: 2, relationship_predicted_count: 4, relationship_expected_count: 5, false_positive_count: 1, missing_case_count: 1, unexplained_residual_paise: 7 }, scenario_breakdown: {} }) : json({ error: { code: "NOT_EVALUATED", message: "No evaluation", request_id: "req-eval" } }, 404);
    const match = path.match(/^\/runs\/[^/]+\/cases\/([^/]+)(?:\/(.*))?$/);
    if (match) {
      const base = cases.find((c) => c.case_id === match[1])!;
      const item = reviewDone && base.case_id === "CASE_FEE" ? { ...base, case_state: "REJECTED_SUGGESTION", human_reviewed: true } : base;
      if (match[2] === "reject") { reviewDone = true; reviewRevision++; return json({ run_id: runId, case_id: item.case_id, action: "reject", previous_state: item.case_state, new_state: "REJECTED_SUGGESTION", invariant_passed: null, human_reviewed: true, created_at: timestamp, execution_revision: 1, review_revision: reviewRevision }); }
      if (!match[2]) return json({ ...item, source_entity_ids: [], records: [] });
      if (match[2] === "evidence") return json({ case_id: item.case_id, nodes: [], edges: [] });
      if (match[2] === "receipt") return receiptError ? json({ error: { code: "PROOF_UNAVAILABLE", message: "Receipt temporarily unavailable", request_id: "req-proof-123" } }, 503) : json({ case_id: item.case_id, case_state: item.case_state, residual_paise: 0, all_invariants_passed: false, invariants: [], evidence_edge_count: 0, result_checksum: "result-checksum" });
      if (match[2] === "candidates") return json({ case_id: item.case_id, items: [] });
    }
    return json({ error: { code: "UNEXPECTED_REQUEST", message: `Unexpected ${path}`, request_id: "req-unexpected" } }, 500);
  });
  return { calls, restoreReceipt: () => { receiptError = false; }, finishReconciliation: () => release?.() };
}

test("custom upload finishes without attempting demo ground-truth evaluation", async ({ page }) => {
  const api = await mockAPI(page);
  await page.goto("/");
  for (let index = 0; index < sourceTypes.length; index++) await page.locator('input[type="file"]').nth(index).setInputFiles({ name: `${sourceTypes[index]}.csv`, mimeType: "text/csv", buffer: Buffer.from("id,amount\nexample,100\n") });
  await page.getByRole("button", { name: "Upload and validate" }).click();
  await expect(page.getByText("All required source files are present.", { exact: false })).toBeVisible();
  await page.getByTestId("start-reconciliation").click();
  await expect(page).toHaveURL(`/runs/${runId}`);
  await expect(page.getByTestId("control-room")).toBeVisible();
  expect(api.calls.some((call) => call.path.endsWith("/evaluate"))).toBe(false);
  await expect(page.getByText("Not evaluated", { exact: true })).toHaveCount(2);
  await expect(page.getByText("AI Ready", { exact: true })).toHaveCount(0);
});

test("source presence stays 100 percent when row validation blocks processing", async ({ page }) => {
  await mockAPI(page, { validationInvalid: true });
  await page.goto("/");
  for (let index = 0; index < sourceTypes.length; index++) {
    await page.locator('input[type="file"]').nth(index).setInputFiles({
      name: `${sourceTypes[index]}.csv`,
      mimeType: "text/csv",
      buffer: Buffer.from("id,amount\nexample,100\n"),
    });
  }
  await page.getByRole("button", { name: "Upload and validate" }).click();
  const readiness = page.getByText("Required source readiness").locator("..");
  await expect(readiness).toContainText("100%");
  await expect(page.getByRole("heading", { name: "Sources present · validation blocked" })).toBeVisible();
  await expect(page.getByText("Blocked by validation", { exact: true })).toBeVisible();
  await expect(page.getByTestId("start-reconciliation")).toBeDisabled();
});

test("retryable reconciliation reuses the exact idempotency key", async ({ page }) => {
  const api = await mockAPI(page, { reconciliationFailureOnce: true });
  await page.goto("/");
  for (let index = 0; index < sourceTypes.length; index++) {
    await page.locator('input[type="file"]').nth(index).setInputFiles({
      name: `${sourceTypes[index]}.csv`,
      mimeType: "text/csv",
      buffer: Buffer.from("id,amount\nexample,100\n"),
    });
  }
  await page.getByRole("button", { name: "Upload and validate" }).click();
  const start = page.getByTestId("start-reconciliation");
  await start.click();
  await expect(page.locator('p[role="alert"]')).toContainText("req-reconcile-retry");
  await expect(start).toBeEnabled();
  await start.click();
  await expect(page).toHaveURL(`/runs/${runId}`);

  const attempts = api.calls.filter(
    (call) => call.path === `/runs/${runId}/reconcile` && call.method === "POST",
  );
  expect(attempts).toHaveLength(2);
  expect(attempts[0].idempotencyKey).toBeTruthy();
  expect(attempts[1].idempotencyKey).toBe(attempts[0].idempotencyKey);
});

test("claims show failed thresholds and no static verified badge", async ({ page }) => {
  await mockAPI(page, { evaluation: "failed" });
  await page.goto(`/runs/${runId}`);
  await page.getByTitle("Open Claims Ledger").click();
  const modal = page.getByTestId("claims-ledger-modal");
  await expect(modal.getByText("FAIL", { exact: true })).toHaveCount(5);
  await expect(modal.getByText(/0 of 5 measured checks passed/)).toBeVisible();
  await expect(page.getByText(/10\/10 Verified/)).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(modal).toBeHidden();
  await expect(page.getByTitle("Open Claims Ledger")).toBeFocused();
});

test("missing evaluation remains unverified", async ({ page }) => {
  await mockAPI(page);
  await page.goto(`/runs/${runId}`);
  await page.getByTitle("Open Claims Ledger").click();
  const modal = page.getByTestId("claims-ledger-modal");
  await expect(modal.getByText(/Not evaluated. This run has no matching/)).toBeVisible();
  await expect(modal.getByText("PASS", { exact: true })).toHaveCount(0);
});

test("URL code/search/case filters select exact evidence and survive reload", async ({ page }) => {
  const api = await mockAPI(page);
  await page.goto(`/runs/${runId}/cases?code=FEE_VARIANCE&search=CASE_FEE`);
  const table = page.getByTestId("cases-table");
  await expect(table.locator("tbody tr")).toHaveCount(1);
  await expect(table.getByTestId("pagination-status")).toHaveText("All 1 matching records");
  await table.locator("tbody").getByRole("button", { name: "Inspect CASE_FEE" }).click();
  await expect(page).toHaveURL(/case=CASE_FEE/);
  await expect(page.getByTestId("evidence-drawer")).toBeVisible();
  await page.reload();
  await expect(page.getByTestId("evidence-drawer")).toBeVisible();
  expect(api.calls.some((call) => call.path === `/runs/${runId}/cases/CASE_FEE/receipt`)).toBe(true);
  expect(api.calls.some((call) => call.path.startsWith("/cases/"))).toBe(false);
});

test("pending evidence does not mark an absent bank receipt matched; compact keyboard action works", async ({ page }) => {
  await mockAPI(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/runs/${runId}/cases?search=CASE_PENDING`);
  const inspect = page.getByLabel("Compact records").getByRole("button", { name: "Inspect CASE_PENDING" });
  await inspect.focus(); await page.keyboard.press("Enter");
  const drawer = page.getByTestId("evidence-drawer");
  await expect(drawer.getByText("No verified bank receipt")).toBeVisible();
  await expect(drawer.getByLabel("Matched", { exact: true })).toHaveCount(0);
  await page.keyboard.press("Tab");
  expect(await drawer.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("proof failure presents request ID and recovers through retry", async ({ page }) => {
  const api = await mockAPI(page, { receiptError: true });
  await page.goto(`/runs/${runId}/cases?case=CASE_PENDING`);
  const drawer = page.getByTestId("evidence-drawer");
  await expect(drawer.getByText("Case evidence unavailable")).toBeVisible();
  await expect(drawer.getByText(/req-proof-123/)).toBeVisible();
  api.restoreReceipt();
  await drawer.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(drawer.getByText("No verified bank receipt")).toBeVisible();
});

test("cash drilldown shows exact bucket contribution instead of case net", async ({ page }) => {
  await mockAPI(page);
  await page.goto(`/runs/${runId}/cash?bucket=AT_RISK`);
  const row = page.locator('[data-row-key="CASE_FEE"]');
  await expect(row).toContainText("₹1.23");
  await expect(row).not.toContainText("₹475.18");
  await expect(page.getByText("Confirmed batch receipts", { exact: true })).toBeVisible();
  await expect(page.getByText("Claimable GSTR-2B ITC", { exact: true })).toHaveCount(0);
});

test("shared sign-in sends bearer token without persisting it", async ({ page }) => {
  const api = await mockAPI(page, { shared: true });
  await page.goto(`/runs/${runId}/cases`);
  await expect(page.getByRole("heading", { name: "Sign in to ClearLedger" })).toBeVisible();
  await page.getByLabel("Access token").fill("contract-test-token");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByTestId("cases-table")).toBeVisible();
  expect(api.calls.filter((call) => call.path.startsWith("/runs/")).every((call) => call.authorization === "Bearer contract-test-token")).toBe(true);
  expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))).not.toContain("contract-test-token");
  await page.reload();
  await expect(page.getByRole("heading", { name: "Sign in to ClearLedger" })).toBeVisible();
});


test("progress reports persisted backend stage and record count", async ({ page }) => {
  const api = await mockAPI(page, { heldProgress: true });
  await page.goto("/");
  for (let index = 0; index < sourceTypes.length; index++) await page.locator('input[type="file"]').nth(index).setInputFiles({ name: `${sourceTypes[index]}.csv`, mimeType: "text/csv", buffer: Buffer.from("id,amount\nexample,100\n") });
  await page.getByRole("button", { name: "Upload and validate" }).click();
  await page.getByTestId("start-reconciliation").click();
  const progress = page.getByTestId("reconciliation-progress");
  await expect(progress).toContainText("Matching · 19 records processed");
  await expect(progress.getByRole("progressbar")).toHaveAttribute("value", "37");
  api.finishReconciliation();
  await expect(page).toHaveURL(`/runs/${runId}`);
});

test("review mutation uses revision and refreshes forecast, tax, receipt and current run", async ({ page }) => {
  const api = await mockAPI(page);
  await page.goto(`/runs/${runId}/cash?bucket=AT_RISK`);
  await page.locator('[data-row-key="CASE_FEE"]').click();
  await expect(page.getByTestId("evidence-drawer").getByText("Settlement equation")).toBeVisible();
  const before = api.calls.length;
  await page.getByTestId("reject-case").click();
  await page.getByLabel("Reason (required)").fill("Missing bank evidence needs correction.");
  await page.getByTestId("confirm-review-action").click();
  await expect(page.getByTestId("evidence-drawer").getByText("Rejected suggestion", { exact: true })).toBeVisible();
  const review = api.calls.find((call) => call.path.endsWith("/CASE_FEE/reject"));
  expect(review).toBeDefined();
  expect(JSON.parse(review!.body!)).toMatchObject({ expected_review_revision: 0 });
  expect(JSON.parse(review!.body!)).not.toHaveProperty("actor");
  await expect.poll(() => ["cash-forecast", "tax-audit", "receipt"].every((suffix) => api.calls.slice(before).some((call) => call.path.endsWith(`/${suffix}`)))).toBe(true);
});
