import { z } from "zod";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

const nullableString = z.string().nullable();
const dateString = z.string();
const unknownRecord = z.record(z.string(), z.unknown());

export const sourceFileSchema = z.object({
  id: z.string(),
  filename: z.string(),
  source_type: z.string(),
  file_checksum: z.string(),
  file_size_bytes: z.number().nullable(),
  row_count: z.number().nullable(),
  ingestion_quality: z.string(),
  created_at: dateString,
});

export const runSchema = z.object({
  id: z.string(),
  status: z.string(),
  policy_version_id: nullableString,
  dataset_checksum: nullableString,
  rule_set_version: nullableString,
  app_version: nullableString,
  ai_model: nullableString,
  ai_prompt_version: nullableString,
  policy_id: nullableString.optional().default(null),
  policy_version: nullableString.optional().default(null),
  started_at: dateString.nullable(),
  completed_at: dateString.nullable(),
  duration_ms: z.number().nullable(),
  total_source_rows: z.number().nullable(),
  total_cases: z.number().nullable(),
  result_checksum: nullableString,
  failure_reason: nullableString,
  created_at: dateString,
  files: z.array(sourceFileSchema),
});

export const fileValidationSchema = z.object({
  source_type: z.string(),
  filename: z.string(),
  quality: z.string(),
  row_count: z.number(),
  accepted_count: z.number(),
  rejected_count: z.number(),
  control_total_paise: z.number().default(0),
  errors: z.array(unknownRecord),
});

export const validationSchema = z.object({
  run_id: z.string(),
  valid: z.boolean(),
  missing_source_types: z.array(z.string()),
  files: z.array(fileValidationSchema),
  total_rows: z.number(),
  invalid_rows: z.number(),
});

export const demoRunSchema = z.object({
  run: runSchema,
  validation: validationSchema,
});

export const reconciliationSchema = z.object({
  run_id: z.string(),
  status: z.string(),
  total_source_records: z.number(),
  total_cases: z.number(),
  evidence_edges: z.number(),
  exceptions: z.number(),
  result_checksum: z.string(),
});

export const metricsSchema = z.object({
  run_id: z.string(),
  status: z.string(),
  metrics: unknownRecord,
});

export const runStatusSchema = z.object({
  run_id: z.string(),
  status: z.string(),
  failure_reason: nullableString,
  started_at: dateString.nullable(),
  completed_at: dateString.nullable(),
});

export const caseSummarySchema = z.object({
  case_id: z.string(),
  reconciliation_run_id: z.string(),
  case_state: z.string(),
  decision_level: nullableString,
  gross_amount_paise: z.number(),
  net_amount_paise: z.number(),
  residual_paise: z.number(),
  currency: z.string(),
  exception_code: nullableString,
  exception_severity: nullableString,
  amount_at_risk_paise: z.number(),
  cash_bucket: nullableString,
  settlement_id: nullableString,
  bank_receipt_state: nullableString,
  owner_role: nullableString,
  next_action: nullableString,
  ai_assisted: z.boolean(),
  human_reviewed: z.boolean(),
  created_at: dateString,
  updated_at: dateString,
});

export const caseDetailSchema = caseSummarySchema.extend({
  source_entity_ids: z.array(z.string()),
  records: z.array(unknownRecord),
});

export const paginatedCasesSchema = z.object({
  items: z.array(caseSummarySchema),
  page: z.number(),
  page_size: z.number(),
  total: z.number(),
  pages: z.number(),
});

export const evidenceEdgeSchema = z.object({
  source_entity_id: z.string(),
  target_entity_id: z.string(),
  relationship_type: z.string(),
  allocated_amount_paise: z.number(),
  currency: z.string(),
  rule_id: z.string(),
  rule_version: z.string(),
  evidence_fields: z.array(z.string()),
  decision_level: z.string(),
  actor_type: z.string(),
  verification_checks: z.array(unknownRecord).nullable(),
  created_at: dateString,
});

export const evidenceGraphSchema = z.object({
  case_id: z.string(),
  nodes: z.array(z.string()),
  edges: z.array(evidenceEdgeSchema),
});

export const invariantSchema = z.object({
  invariant_id: z.string(),
  passed: z.boolean(),
  expected_value: z.union([z.string(), z.number()]).nullable(),
  actual_value: z.union([z.string(), z.number()]).nullable(),
  affected_entities: z.array(z.string()).nullable(),
  message: nullableString,
});

export const receiptSchema = z.object({
  case_id: z.string(),
  case_state: z.string(),
  residual_paise: z.number(),
  all_invariants_passed: z.boolean(),
  invariants: z.array(invariantSchema),
  evidence_edge_count: z.number(),
  result_checksum: nullableString,
});

export const candidateSchema = z.object({
  source_entity_id: z.string(),
  target_entity_id: z.string(),
  relationship_type: z.string(),
  match_score: z.number().nullable(),
  decision_level: z.string(),
  rejection_reason: nullableString,
  evidence_fields: z.array(z.string()),
  allocated_amount_paise: z.number(),
  currency: z.string(),
  rule_id: nullableString,
  actor_type: z.string(),
});

export const candidatesSchema = z.object({
  case_id: z.string(),
  items: z.array(candidateSchema),
});

const cashBucketSchema = z.object({
  bucket: z.string(),
  amount_paise: z.number(),
  case_ids: z.array(z.string()),
});

export const cashPositionSchema = z.object({
  run_id: z.string(),
  currency: z.string(),
  bank_confirmed_paise: z.number(),
  settlement_confirmed_in_transit_paise: z.number(),
  expected_settlement_paise: z.number(),
  at_risk_paise: z.number(),
  unresolved_paise: z.number(),
  scheduled_refunds_paise: z.number(),
  known_disputes_paise: z.number(),
  known_reserve_holds_paise: z.number(),
  safe_cash_paise: z.number(),
  buckets: z.record(z.string(), cashBucketSchema),
});

export const cashForecastDaySchema = z.object({
  day_offset: z.number(),
  label: z.string(),
  date: z.string(),
  is_banking_day: z.boolean(),
  opening_cash_paise: z.number(),
  expected_inflow_paise: z.number(),
  scheduled_deductions_paise: z.number(),
  closing_cash_paise: z.number(),
  confidence_score: z.number(),
  case_count: z.number(),
  case_ids: z.array(z.string()),
  settlement_ids: z.array(z.string()),
});

export const cashForecastResponseSchema = z.object({
  run_id: z.string(),
  as_of_date: z.string(),
  currency: z.string(),
  days: z.array(cashForecastDaySchema),
  total_projected_inflow_paise: z.number(),
  baseline_safe_cash_paise: z.number(),
  projected_final_cash_paise: z.number(),
});

export const taxDiscrepancyItemSchema = z.object({
  case_id: z.string(),
  payment_id: z.string(),
  settlement_id: nullableString,
  gross_amount_paise: z.number(),
  actual_fee_paise: z.number(),
  expected_fee_paise: z.number(),
  fee_variance_paise: z.number(),
  actual_tax_paise: z.number(),
  expected_tax_paise: z.number(),
  tax_variance_paise: z.number(),
  exception_code: nullableString,
});

export const taxAuditResponseSchema = z.object({
  run_id: z.string(),
  currency: z.string(),
  total_cases_audited: z.number(),
  gross_payment_volume_paise: z.number(),
  total_gateway_fee_paise: z.number(),
  expected_gateway_fee_paise: z.number(),
  fee_variance_paise: z.number(),
  total_tax_paise: z.number(),
  expected_tax_paise: z.number(),
  tax_variance_paise: z.number(),
  claimable_itc_paise: z.number(),
  disputed_tax_paise: z.number(),
  tax_policy_pass_rate: z.number(),
  fee_policy_pass_rate: z.number(),
  discrepant_case_count: z.number(),
  discrepancies: z.array(taxDiscrepancyItemSchema),
  itc_status: z.string(),
});

export const auditEventSchema = z.object({
  id: z.string(),
  reconciliation_run_id: nullableString,
  case_id: nullableString,
  source_file_id: nullableString,
  event_type: z.string(),
  stage: nullableString,
  rule_id: nullableString,
  severity: nullableString,
  details: unknownRecord.nullable(),
  actor: nullableString,
  duration_ms: z.number().nullable(),
  created_at: dateString,
});

export const auditSchema = z.object({
  items: z.array(auditEventSchema),
  page: z.number(),
  page_size: z.number(),
  total: z.number(),
  pages: z.number(),
});

export const evaluationSchema = z.object({
  run_id: z.string(),
  dataset_id: z.string(),
  aggregate: unknownRecord,
  scenario_breakdown: z.record(z.string(), unknownRecord),
});

export const aiAnalysisSchema = z.object({
  id: z.string(),
  reconciliation_run_id: z.string(),
  case_id: z.string(),
  evidence_packet: unknownRecord,
  ai_response: unknownRecord.nullable(),
  ai_model: nullableString,
  ai_prompt_version: nullableString,
  provider: nullableString,
  status: z.string(),
  tokens_prompt: z.number().nullable(),
  tokens_completion: z.number().nullable(),
  latency_ms: z.number().nullable(),
  estimated_cost: z.number(),
  attempts: z.number(),
  validation_passed: z.boolean().nullable(),
  validation_errors: z.array(unknownRecord).nullable(),
  deterministic_checks: z.array(unknownRecord).nullable(),
  error_type: nullableString,
  created_at: dateString,
});

export const reviewActionSchema = z.object({
  case_id: z.string(),
  action: z.string(),
  previous_state: z.string(),
  new_state: z.string(),
  invariant_passed: z.boolean().nullable(),
  human_reviewed: z.boolean(),
  created_at: dateString,
});

export type Run = z.infer<typeof runSchema>;
export type FileValidation = z.infer<typeof fileValidationSchema>;
export type Validation = z.infer<typeof validationSchema>;
export type CaseSummary = z.infer<typeof caseSummarySchema>;
export type PaginatedCases = z.infer<typeof paginatedCasesSchema>;
export type CaseDetail = z.infer<typeof caseDetailSchema>;
export type EvidenceGraphData = z.infer<typeof evidenceGraphSchema>;
export type VerificationReceipt = z.infer<typeof receiptSchema>;
export type CandidateList = z.infer<typeof candidatesSchema>;
export type CashPosition = z.infer<typeof cashPositionSchema>;
export type CashForecastDay = z.infer<typeof cashForecastDaySchema>;
export type CashForecastResponse = z.infer<typeof cashForecastResponseSchema>;
export type TaxDiscrepancyItem = z.infer<typeof taxDiscrepancyItemSchema>;
export type TaxAuditResponse = z.infer<typeof taxAuditResponseSchema>;
export type AuditEvent = z.infer<typeof auditEventSchema>;
export type Evaluation = z.infer<typeof evaluationSchema>;
export type AIAnalysis = z.infer<typeof aiAnalysisSchema>;
export type ReviewAction = "approve" | "reject" | "defer" | "assign";

const errorEnvelopeSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    request_id: z.string().optional(),
    details: unknownRecord.optional(),
  }),
});

export class APIError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "APIError";
  }
}

function idempotencyKey(scope: string): string {
  const suffix =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `web-${scope}-${suffix}`;
}

async function apiRequest<T>(
  path: string,
  schema: z.ZodType<T>,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...init.headers,
    },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const parsed = errorEnvelopeSchema.safeParse(payload);
    if (parsed.success) {
      throw new APIError(
        response.status,
        parsed.data.error.code,
        parsed.data.error.message,
        parsed.data.error.details,
      );
    }
    throw new APIError(response.status, "REQUEST_FAILED", `Request failed (${response.status}).`);
  }
  return schema.parse(payload);
}

function mutationHeaders(scope: string, json = false): HeadersInit {
  return {
    "Idempotency-Key": idempotencyKey(scope),
    ...(json ? { "Content-Type": "application/json" } : {}),
  };
}

export function loadDemoRun() {
  return apiRequest("/runs/demo", demoRunSchema, {
    method: "POST",
    headers: mutationHeaders("demo"),
  });
}

export function createRun() {
  return apiRequest("/runs", runSchema, {
    method: "POST",
    headers: mutationHeaders("create-run", true),
    body: JSON.stringify({}),
  });
}

export async function uploadRunFiles(runId: string, files: Record<string, File>) {
  const form = new FormData();
  Object.entries(files).forEach(([sourceType, file]) => form.append(sourceType, file));
  return apiRequest(`/runs/${runId}/files`, z.array(sourceFileSchema), {
    method: "POST",
    headers: mutationHeaders(`upload-${runId}`),
    body: form,
  });
}

export function validateRun(runId: string) {
  return apiRequest(`/runs/${runId}/validate`, validationSchema, {
    method: "POST",
    headers: mutationHeaders(`validate-${runId}`),
  });
}

export function reconcileRun(runId: string) {
  return apiRequest(`/runs/${runId}/reconcile`, reconciliationSchema, {
    method: "POST",
    headers: mutationHeaders(`reconcile-${runId}`),
  });
}

export function evaluateRun(runId: string) {
  return apiRequest(`/runs/${runId}/evaluate`, evaluationSchema, {
    method: "POST",
    headers: mutationHeaders(`evaluate-${runId}`),
  });
}

export function getRun(runId: string) {
  return apiRequest(`/runs/${runId}`, runSchema);
}

export function getMetrics(runId: string) {
  return apiRequest(`/runs/${runId}/metrics`, metricsSchema);
}

export function getRunStatus(runId: string) {
  return apiRequest(`/runs/${runId}/status`, runStatusSchema);
}

function getCasesPage(runId: string, page: number) {
  return apiRequest(
    `/runs/${runId}/cases?page=${page}&page_size=200`,
    paginatedCasesSchema,
  );
}

export async function getCases(runId: string): Promise<PaginatedCases> {
  const firstPage = await getCasesPage(runId, 1);
  if (firstPage.pages <= 1) return firstPage;

  const remainingPages = await Promise.all(
    Array.from({ length: firstPage.pages - 1 }, (_, index) => getCasesPage(runId, index + 2)),
  );
  return {
    ...firstPage,
    items: [firstPage, ...remainingPages].flatMap((result) => result.items),
  };
}

export function getCase(caseId: string) {
  return apiRequest(`/cases/${encodeURIComponent(caseId)}`, caseDetailSchema);
}

export function getEvidence(caseId: string) {
  return apiRequest(`/cases/${encodeURIComponent(caseId)}/evidence`, evidenceGraphSchema);
}

export function getReceipt(caseId: string) {
  return apiRequest(`/cases/${encodeURIComponent(caseId)}/receipt`, receiptSchema);
}

export function getCandidates(caseId: string) {
  return apiRequest(`/cases/${encodeURIComponent(caseId)}/candidates`, candidatesSchema);
}

export async function getAIAnalysis(caseId: string): Promise<AIAnalysis | null> {
  try {
    return await apiRequest(
      `/cases/${encodeURIComponent(caseId)}/ai-analysis`,
      aiAnalysisSchema,
    );
  } catch (error) {
    if (error instanceof APIError && error.status === 404) return null;
    throw error;
  }
}

export function getCashPosition(runId: string) {
  return apiRequest(`/runs/${runId}/cash-position`, cashPositionSchema);
}

export function getAudit(runId: string) {
  return apiRequest(`/runs/${runId}/audit?page_size=500`, auditSchema);
}

export async function getEvaluation(runId: string): Promise<Evaluation | null> {
  try {
    return await apiRequest(`/runs/${runId}/evaluation`, evaluationSchema);
  } catch (error) {
    if (error instanceof APIError && error.status === 404) return null;
    throw error;
  }
}

export function submitReview(
  caseId: string,
  action: ReviewAction,
  values: { reason?: string; note?: string; until?: string; owner_role?: string },
) {
  return apiRequest(`/cases/${encodeURIComponent(caseId)}/${action}`, reviewActionSchema, {
    method: "POST",
    headers: mutationHeaders(`${action}-${caseId}`, true),
    body: JSON.stringify({ actor: "demo.finance.operator", ...values }),
  });
}

export function exportUrl(runId: string, artifact: string) {
  return `${API_BASE_URL}/runs/${runId}/exports/${artifact}`;
}

export const questionResponseSchema = z.object({
  run_id: z.string(),
  question: z.string(),
  answer: z.string(),
  cited_case_ids: z.array(z.string()).default([]),
  provider: z.string(),
  model: z.string(),
  grounded: z.boolean().default(true),
});

export type QuestionResponse = z.infer<typeof questionResponseSchema>;

export function askRunQuestion(runId: string, question: string) {
  return apiRequest(`/runs/${runId}/questions`, questionResponseSchema, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
}

export function getCashForecast(runId: string, anchorDate?: string) {
  const query = anchorDate ? `?anchor_date=${encodeURIComponent(anchorDate)}` : "";
  return apiRequest(`/runs/${runId}/cash-forecast${query}`, cashForecastResponseSchema);
}

export function getTaxAudit(runId: string) {
  return apiRequest(`/runs/${runId}/tax-audit`, taxAuditResponseSchema);
}

