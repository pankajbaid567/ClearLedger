import { mkdir, stat } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test } from "@playwright/test";

const API_BASE_URL = "http://127.0.0.1:18100/api";

test.describe.configure({ mode: "serial" });

test.describe("ClearLedger demo operations loop", () => {
  let runId = "";
  let reviewCaseId = "";
  let unresolvedBeforeReview = 0;

  test("loads the demo, reconciles it, and shows control metrics", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("load-demo").click();
    await expect(page.getByText("Demo dataset loaded and validated.")).toBeVisible();
    await expect(page.getByTestId("start-reconciliation")).toBeEnabled();

    await page.getByTestId("start-reconciliation").click();
    await expect(page).toHaveURL(/\/runs\/[0-9a-f-]{36}$/, { timeout: 120_000 });
    runId = page.url().split("/").pop() ?? "";

    await expect(page.getByTestId("control-room")).toBeVisible();
    await expect(page.getByTestId("metric-total-cases")).toContainText("75");
    await expect(page.getByText("Precision", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Cash by confidence", { exact: true })).toBeVisible();
  });

  test("paginates the complete queue and explains scoped one-page results", async ({ page }) => {
    await page.goto(`/runs/${runId}/cases`);
    const table = page.getByTestId("cases-table");
    const firstPageRow = await table.locator("tbody tr").first().getAttribute("data-row-key");

    await expect(table.getByTestId("pagination-range")).toHaveText("1–15 of 75");
    await expect(table.getByTestId("pagination-status")).toHaveText("Page 1 of 5");
    await table.getByRole("button", { name: "Next page" }).click();
    await expect(table.getByTestId("pagination-range")).toHaveText("16–30 of 75");
    await expect(table.getByTestId("pagination-status")).toHaveText("Page 2 of 5");
    expect(await table.locator("tbody tr").first().getAttribute("data-row-key")).not.toBe(
      firstPageRow,
    );

    await page.goto(`/runs/${runId}/cases?bucket=AT_RISK`);
    await expect(
      page.getByRole("button", { name: "Remove Cash bucket: At Risk filter" }),
    ).toBeVisible();
    const recordLabel = await table.getByText(/^\d+ records$/).textContent();
    const filteredCount = Number(recordLabel?.match(/\d+/)?.[0] ?? 0);
    expect(filteredCount).toBeGreaterThan(5);
    expect(filteredCount).toBeLessThanOrEqual(15);
    await expect(table.getByTestId("pagination-status")).toHaveText(
      `All ${filteredCount} matching records`,
    );

    await table.getByLabel("Rows per page").selectOption("5");
    await expect(table.getByTestId("pagination-status")).toHaveText(
      `Page 1 of ${Math.ceil(filteredCount / 5)}`,
    );
    await table.getByRole("button", { name: "Next page" }).click();
    await expect(table.getByTestId("pagination-range")).toHaveText(
      `6–${Math.min(10, filteredCount)} of ${filteredCount}`,
    );

    await page.getByRole("button", { name: "Remove Cash bucket: At Risk filter" }).click();
    await expect(page).not.toHaveURL(/bucket=AT_RISK/);
    await expect(table.getByTestId("pagination-range")).toHaveText("1–5 of 75");
    await expect(table.getByTestId("pagination-status")).toHaveText("Page 1 of 15");
  });

  test("filters the queue to actionable exceptions", async ({ page }) => {
    await page.goto(`/runs/${runId}/cases`);
    await page.getByText("State", { exact: true }).click();
    await page.getByLabel("Actionable Exception").check({ force: true });

    const rows = page.getByTestId("cases-table").locator("tbody tr");
    await expect(rows.first()).toBeVisible();
    const count = await rows.count();
    expect(count).toBeGreaterThan(0);
    for (let index = 0; index < count; index += 1) {
      await expect(rows.nth(index)).toContainText("Actionable");
    }
  });

  test("renders reconciled and exception evidence drawers", async ({ page, request }) => {
    await page.goto(`/runs/${runId}/cases?state=RECONCILED`);
    await page.getByTestId("cases-table").locator("tbody tr").first().click();
    const drawer = page.getByTestId("evidence-drawer");
    await expect(drawer).toBeVisible();
    await expect(drawer.getByText("Source records", { exact: true })).toBeVisible();
    await expect(drawer.getByText("Evidence graph", { exact: true })).toBeVisible();
    await expect(drawer.getByText("Settlement equation", { exact: true })).toBeVisible();
    await expect(drawer.getByText("Invariant results", { exact: true })).toBeVisible();
    await expect(drawer.getByText("Candidate matches", { exact: true })).toBeVisible();
    await expect(drawer.getByText("Audit timeline", { exact: true })).toBeVisible();
    await expect(drawer.getByTestId("equation-card").getByText("₹0.00").last()).toBeVisible();
    await drawer.getByRole("button", { name: "Close evidence drawer" }).click();

    const casesResponse = await request.get(
      `${API_BASE_URL}/runs/${runId}/cases?page_size=200`,
    );
    const casesPayload = (await casesResponse.json()) as {
      items: Array<{ case_id: string; case_state: string; cash_bucket: string }>;
    };
    reviewCaseId =
      casesPayload.items.find(
        (item) => item.case_state === "ACTIONABLE_EXCEPTION" && item.cash_bucket === "AT_RISK",
      )?.case_id ?? "";
    expect(reviewCaseId).not.toBe("");
    const cashBefore = await request.get(`${API_BASE_URL}/runs/${runId}/cash-position`);
    unresolvedBeforeReview = ((await cashBefore.json()) as { unresolved_paise: number }).unresolved_paise;

    await page.goto(`/runs/${runId}/cases?state=ACTIONABLE_EXCEPTION`);
    await page.locator(`[data-row-key="${reviewCaseId}"]`).click();
    await expect(page.getByTestId("evidence-drawer").getByText("Amount at risk", { exact: true })).toBeVisible();
    await expect(page.getByText("Human decision", { exact: true })).toBeVisible();
  });

  test("records controlled approval and keeps unverified cash locked", async ({ page }) => {
    await page.goto(`/runs/${runId}/cases?state=ACTIONABLE_EXCEPTION`);
    await page.locator(`[data-row-key="${reviewCaseId}"]`).click();

    await page.getByTestId("approve-case").click();
    await page.getByTestId("confirm-review-action").click();
    await expect(page.getByText("Approved pending verification", { exact: true }).first()).toBeVisible();
    await expect(page.getByText(/Approve recorded. Case is Approved Pending Verification/)).toBeVisible();
    await expect(page.getByTestId("approve-case")).toBeDisabled();

    await page.getByTestId("reject-case").click();
    await page.getByLabel("Reason (required)").fill("Candidate evidence is insufficient for verification.");
    await page.getByTestId("confirm-review-action").click();
    await expect(page.getByText("Rejected suggestion", { exact: true }).first()).toBeVisible();
    await expect(page.getByText(/Reject recorded/)).toBeVisible();
  });

  test("updates the unresolved cash bucket after review", async ({ page, request }) => {
    const cashAfter = await request.get(`${API_BASE_URL}/runs/${runId}/cash-position`);
    const cashPayload = (await cashAfter.json()) as {
      unresolved_paise: number;
      buckets: Record<string, { case_ids: string[] }>;
    };
    expect(cashPayload.unresolved_paise).toBeGreaterThan(unresolvedBeforeReview);
    expect(cashPayload.buckets.UNRESOLVED.case_ids).toContain(reviewCaseId);

    await page.goto(`/runs/${runId}/cash?bucket=UNRESOLVED`);
    await expect(page.getByTestId("cash-bucket-UNRESOLVED")).toBeVisible();
    await expect(page.locator(`[data-row-key="${reviewCaseId}"]`)).toBeVisible();
  });

  test("downloads a non-empty reconciliation export", async ({ page }) => {
    await page.goto(`/runs/${runId}`);
    const downloadPromise = page.waitForEvent("download");
    await page.getByTestId("download-reconciliation").click();
    const download = await downloadPromise;
    const path = await download.path();
    expect(path).not.toBeNull();
    expect((await stat(path as string)).size).toBeGreaterThan(0);
  });

  test("keeps cash and case workflows usable at compact widths", async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto(`/runs/${runId}/cash`);
    await expect(page.getByText("Safe Cash Now", { exact: true })).toBeVisible();
    await expect(page.getByText("Near-Term Controlled", { exact: true })).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    await page.screenshot({ path: testInfo.outputPath("cash-1024.png"), fullPage: true });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`/runs/${runId}/cases?state=RECONCILED`);
    await expect(page.getByRole("heading", { name: "Economic cases" })).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    await page.getByTestId("cases-table").locator("tbody tr").first().click();
    await expect(page.getByTestId("evidence-drawer")).toBeVisible();
    await expect(page.getByRole("button", { name: "Close evidence drawer" })).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("case-mobile.png"), fullPage: true });
  });

  test("captures pitch-deck backup screens", async ({ page }) => {
    const screenshotDir = resolve(process.cwd(), "../../out/demo_backup/screenshots");
    await mkdir(screenshotDir, { recursive: true });
    await page.setViewportSize({ width: 1440, height: 1000 });

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Create a reconciliation run" })).toBeVisible();
    await page.screenshot({ path: resolve(screenshotDir, "01-setup.png"), fullPage: true });

    await page.goto(`/runs/${runId}`);
    await expect(page.getByTestId("control-room")).toBeVisible();
    await page.screenshot({ path: resolve(screenshotDir, "02-control-room.png"), fullPage: true });

    await page.goto(`/runs/${runId}/cases?state=ACTIONABLE_EXCEPTION`);
    await expect(page.getByTestId("cases-table")).toBeVisible();
    await page.screenshot({ path: resolve(screenshotDir, "03-cases.png"), fullPage: true });
    await page.getByTestId("cases-table").locator("tbody tr").first().click();
    await expect(page.getByTestId("evidence-drawer")).toBeVisible();
    await page.screenshot({ path: resolve(screenshotDir, "04-evidence.png") });

    await page.goto(`/runs/${runId}/cash`);
    await expect(page.getByText("Safe Cash Now", { exact: true })).toBeVisible();
    await page.screenshot({ path: resolve(screenshotDir, "05-cash.png"), fullPage: true });

    await page.goto(`/runs/${runId}/audit`);
    await expect(page.getByRole("heading", { name: "Run provenance" })).toBeVisible();
    await page.screenshot({ path: resolve(screenshotDir, "06-audit.png"), fullPage: true });
  });
});
