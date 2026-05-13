/**
 * API client for the tender backend.
 * All fetch calls are centralized here.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const DEFAULT_REQUEST_TIMEOUT_MS = 60_000;

function getToken(): string | null {
  const stored = localStorage.getItem("tender_token");
  if (stored) return stored;
  if (import.meta.env.DEV && import.meta.env.VITE_ENABLE_DEV_AUTH === "true") {
    const devToken = import.meta.env.VITE_DEV_AUTH_TOKEN ?? "dev-token";
    localStorage.setItem("tender_token", devToken);
    return devToken;
  }
  return null;
}

async function readErrorMessage(res: Response): Promise<string> {
  const text = await res.text().catch(() => "");
  if (!text) return `HTTP ${res.status}`;
  try {
    const body = JSON.parse(text) as { detail?: unknown; message?: unknown };
    const detail = body.detail ?? body.message;
    return typeof detail === "string" ? detail : text;
  } catch {
    return text;
  }
}

function normalizeHeaders(headers?: HeadersInit): Record<string, string> {
  if (!headers) return {};
  if (headers instanceof Headers) {
    return Object.fromEntries(headers.entries());
  }
  if (Array.isArray(headers)) {
    return Object.fromEntries(headers);
  }
  return { ...headers };
}

export function buildApiUrl(path: string): string {
  if (/^(?:https?:|blob:|data:)/.test(path)) {
    return path;
  }
  if (path.startsWith("/api/")) {
    return `${BASE_URL}${path}`;
  }
  if (path.startsWith("/")) {
    return `${BASE_URL}/api${path}`;
  }
  return `${BASE_URL}/api/${path}`;
}

export function getAuthHeaders(headers?: HeadersInit): Record<string, string> {
  const normalized = normalizeHeaders(headers);
  const token = getToken();
  return token ? { ...normalized, Authorization: `Bearer ${token}` } : normalized;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = buildApiUrl(path);
  const headers = getAuthHeaders(init?.headers);
  const controller = init?.signal ? null : new AbortController();
  const timeout = controller
    ? window.setTimeout(() => controller.abort(), DEFAULT_REQUEST_TIMEOUT_MS)
    : null;

  try {
    const res = await fetch(url, { ...init, headers, signal: init?.signal ?? controller?.signal });
    if (!res.ok) {
      if (res.status === 401) {
        localStorage.removeItem("tender_token");
        throw new Error("登录已失效，请重新登录");
      }
      throw new Error(await readErrorMessage(res));
    }
    if (res.status === 204) {
      return undefined as T;
    }
    return res.json();
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError" && controller) {
      throw new Error("请求超时");
    }
    if (error instanceof TypeError) {
      throw new Error("无法连接后端服务，请确认后端 API 已启动并且前端代理配置正确");
    }
    throw error;
  } finally {
    if (timeout) window.clearTimeout(timeout);
  }
}

// ── Projects ──

export interface Project {
  id: string;
  name: string;
  status?: string;
  tender_deadline?: string;
  priority?: string;
  created_at: string;
  tender_no?: string | null;
  project_type?: string | null;
  industry?: string | null;
  business_line?: string | null;
  sub_type?: string | null;
  employer_name?: string | null;
  employer_type?: string | null;
  evaluation_method?: string | null;
  qualification_review_type?: string | null;
  submission_deadline?: string | null;
  bid_opening_time?: string | null;
  bid_validity_period?: number | null;
  bid_bond_amount?: string | null;
  bid_bond_form?: string | null;
  bid_bond_deadline?: string | null;
  voltage_level?: string[];
  project_scope?: string[];
  tender_platform?: string | null;
  submission_target?: string | null;
  procurement_type?: string | null;
  section_name?: string | null;
  lot_name?: string | null;
  category_code?: string | null;
  selected_template_package_id?: string | null;
  workflow_status?: string | null;
}

export function listProjects(options?: {
  signal?: AbortSignal;
}): Promise<Project[]> {
  return request<Project[]>("/projects", { signal: options?.signal });
}

export function createProject(data: {
  name: string;
  category_code: string;
  tender_no?: string;
  project_type?: string;
  tender_deadline?: string;
  priority?: string;
  industry?: string;
  business_line?: string;
  sub_type?: string;
  employer_name?: string;
  employer_type?: string;
  evaluation_method?: string;
  qualification_review_type?: string;
  submission_deadline?: string;
  bid_opening_time?: string;
  bid_validity_period?: number;
  bid_bond_amount?: string;
  bid_bond_form?: string;
  bid_bond_deadline?: string;
  voltage_level?: string[];
  project_scope?: string[];
  tender_platform?: string;
  submission_target?: string;
  procurement_type?: string;
  section_name?: string;
  lot_name?: string;
}): Promise<Project> {
  return request<Project>("/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function deleteProject(projectId: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/projects/${projectId}`, {
    method: "DELETE",
  });
}

export interface WorkflowEvent {
  id: string;
  project_id: string;
  previous_status: string | null;
  next_status: string;
  actor: string | null;
  reason: string | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
}

export function transitionProjectWorkflow(
  projectId: string,
  data: { next_status: string; reason?: string; metadata?: Record<string, unknown> },
): Promise<Project> {
  return request<Project>(`/projects/${projectId}/workflow-transition`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function listProjectWorkflowEvents(projectId: string, options?: { signal?: AbortSignal }): Promise<WorkflowEvent[]> {
  return request<WorkflowEvent[]>(`/projects/${projectId}/workflow-events`, { signal: options?.signal });
}

// ── Files ──

export interface ProjectFile {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
}

export function listFiles(
  projectId: string,
  options?: { signal?: AbortSignal },
): Promise<ProjectFile[]> {
  return request<ProjectFile[]>(`/projects/${projectId}/files`, {
    signal: options?.signal,
  });
}

export function uploadFile(
  projectId: string,
  file: File,
): Promise<ProjectFile> {
  const form = new FormData();
  form.append("file", file);
  return request<ProjectFile>(`/projects/${projectId}/files`, {
    method: "POST",
    body: form,
  });
}

// ── Parse ──

export interface ParseSummary {
  document_id: string;
  parsed: boolean;
  section_count: number;
  table_count: number;
  latest_parse_job_id: string | null;
}

export interface Section {
  id: string;
  section_code: string | null;
  title: string;
  level: number;
  page_start: number | null;
  page_end: number | null;
  text: string | null;
}

export interface ParseTable {
  id: string;
  page: number | null;
  raw_json: unknown;
}

export interface TenderDocumentFile {
  id: string;
  tender_document_id: string;
  parent_file_id: string | null;
  filename: string;
  relative_path: string;
  storage_key: string;
  content_type: string;
  size_bytes: number;
  file_type: string;
  classification: string;
  depth: number;
  is_archive: boolean;
  is_parsable: boolean;
  parse_status: string;
  error: string | null;
}

export interface TenderDocument {
  id: string;
  project_id: string;
  original_filename: string;
  upload_type: string;
  status: string;
  content_type: string;
  size_bytes: number;
  storage_key: string;
  file_sha256: string;
  error: string | null;
  file_count: number | null;
}

export interface TenderDocumentDetail extends TenderDocument {
  files: TenderDocumentFile[];
}

export interface TenderDocumentParseStatus {
  tender_document_id: string;
  document_status: string;
  total_file_count: number;
  pending_file_count: number;
  parsing_file_count: number;
  completed_file_count: number;
  failed_file_count: number;
  skipped_file_count: number;
  chunk_count: number;
  files: TenderDocumentFile[];
}

export interface TenderDocumentParseResult {
  tender_document_id: string;
  parsed_file_count: number;
  failed_file_count: number;
  skipped_file_count: number;
  chunk_count: number;
  files: TenderDocumentFile[];
}

export function fetchParseSummary(
  documentId: string,
  options?: { signal?: AbortSignal },
): Promise<ParseSummary> {
  return request<ParseSummary>(`/documents/${documentId}/parse-result`, {
    signal: options?.signal,
  });
}

export function fetchSections(
  documentId: string,
  options?: { signal?: AbortSignal },
): Promise<Section[]> {
  return request<Section[]>(`/documents/${documentId}/sections`, {
    signal: options?.signal,
  });
}

export function fetchTables(
  documentId: string,
  options?: { signal?: AbortSignal },
): Promise<ParseTable[]> {
  return request<ParseTable[]>(`/documents/${documentId}/tables`, {
    signal: options?.signal,
  });
}

export function listTenderDocuments(
  projectId: string,
  options?: { signal?: AbortSignal },
): Promise<TenderDocument[]> {
  return request<TenderDocument[]>(`/projects/${projectId}/tender-documents`, {
    signal: options?.signal,
  });
}

export function uploadTenderDocument(
  projectId: string,
  file: File,
): Promise<TenderDocumentDetail> {
  const form = new FormData();
  form.append("file", file);
  return request<TenderDocumentDetail>(`/projects/${projectId}/tender-documents`, {
    method: "POST",
    body: form,
  });
}

export function parseTenderDocument(
  tenderDocumentId: string,
): Promise<TenderDocumentParseResult> {
  return request<TenderDocumentParseResult>(`/tender-documents/${tenderDocumentId}/parse`, {
    method: "POST",
  });
}

export function fetchTenderDocumentParseStatus(
  tenderDocumentId: string,
  options?: { signal?: AbortSignal },
): Promise<TenderDocumentParseStatus> {
  return request<TenderDocumentParseStatus>(`/tender-documents/${tenderDocumentId}/parse-status`, {
    signal: options?.signal,
  });
}

export function fetchTenderSourceChunks(
  tenderDocumentId: string,
  options?: { signal?: AbortSignal },
): Promise<SourceChunk[]> {
  return request<SourceChunk[]>(`/tender-documents/${tenderDocumentId}/source-chunks`, {
    signal: options?.signal,
  });
}

// ── Requirements ──

export interface Requirement {
  id: string;
  category: string;
  title: string;
  source_text: string | null;
  requirement_text?: string | null;
  source_file?: string | null;
  source_locator?: string | null;
  source_chunk_id?: string | null;
  confidence?: number | null;
  human_confirmed: boolean;
  confirmed_by: string | null;
}

export interface RequirementPackageSource {
  requirement_id: string;
  title: string | null;
  source_file: string | null;
  source_locator: string | null;
  source_chunk_id: string | null;
  text: string;
  human_confirmed: boolean;
}

export interface RequirementPackage {
  id: string;
  category: string;
  topic: string | null;
  lane: string;
  confirmation_level: "critical" | "review" | "auto_accept" | "ignored";
  title: string;
  system_conclusion: string;
  source_count: number;
  confirmed_count: number;
  all_confirmed: boolean;
  blocking: boolean;
  has_conflict: boolean;
  conflict_fields: string[];
  key_fields: Record<string, string[]>;
  confidence: number | null;
  requirements: string[];
  sources: RequirementPackageSource[];
}

export interface RequirementWorkbenchLane {
  id: string;
  label: string;
  packages: RequirementPackage[];
}

export interface RequirementWorkbench {
  project_id: string;
  stats: {
    total_requirements: number;
    package_count: number;
    critical_count: number;
    blocking_count: number;
    conflict_count: number;
    auto_accept_count: number;
    review_count: number;
    ignored_count: number;
  };
  lanes: RequirementWorkbenchLane[];
  packages: RequirementPackage[];
}

export interface ClarificationImpact {
  override_policy: string;
  clarification_id: string;
  created_requirement_count: number;
  superseded_requirement_count: number;
  affected_pairs: Array<{
    old_requirement_id: string;
    new_requirement_id: string;
    category: string;
    title: string;
    similarity?: number;
  }>;
  stale_outline_count: number;
  stale_chapter_count: number;
  stale_draft_count: number;
  requires_reconfirmation: boolean;
}

export interface TenderClarification {
  id: string;
  project_id: string;
  round_no: number;
  clarification_type: string;
  title: string;
  source_file: string | null;
  content_text: string;
  impact_json: ClarificationImpact | Record<string, unknown>;
  status: string;
  created_at: string;
}

export interface SourceChunk {
  id: string;
  tender_document_id: string;
  tender_document_file_id: string;
  chunk_type: string;
  source_file: string;
  document_type: string | null;
  section_title: string | null;
  source_locator: string;
  title: string | null;
  text: string | null;
  table_json: { rows?: string[][]; headers?: string[]; [key: string]: unknown } | null;
  page_start: number | null;
  page_end: number | null;
  sheet_name: string | null;
  row_start: number | null;
  row_end: number | null;
  paragraph_index: number | null;
  sort_order: number;
  confidence: number;
}

export interface TenderSummary {
  project_id: string;
  tender_document_id: string | null;
  project_name: string | null;
  tenderer: string | null;
  tender_agency: string | null;
  project_location: string | null;
  construction_period: string | null;
  quality_requirement: string | null;
  control_price: string | null;
  bid_bond: string | null;
  bid_open_time: string | null;
  bid_deadline: string | null;
  raw_facts_json: Record<string, unknown>;
  source_chunk_ids_json: string[];
  extracted_model: string | null;
}

export function fetchRequirements(
  projectId: string,
  category?: string,
  options?: { signal?: AbortSignal },
): Promise<Requirement[]> {
  const params = category ? `?category=${category}` : "";
  return request<Requirement[]>(
    `/projects/${projectId}/requirements${params}`,
    { signal: options?.signal },
  );
}

export function fetchRequirementWorkbench(
  projectId: string,
  options?: { signal?: AbortSignal },
): Promise<RequirementWorkbench> {
  return request<RequirementWorkbench>(`/projects/${projectId}/requirements/workbench`, {
    signal: options?.signal,
  });
}

export function createTenderClarification(
  projectId: string,
  data: { round_no?: number; clarification_type?: string; title: string; source_file?: string; content_text: string },
): Promise<TenderClarification> {
  return request<TenderClarification>(`/projects/${projectId}/clarifications`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function listTenderClarifications(projectId: string, options?: { signal?: AbortSignal }): Promise<TenderClarification[]> {
  return request<TenderClarification[]>(`/projects/${projectId}/clarifications`, { signal: options?.signal });
}

export function uploadTenderClarification(
  projectId: string,
  data: { title: string; file: File; round_no?: number; clarification_type?: string },
): Promise<TenderClarification> {
  const form = new FormData();
  form.append("title", data.title);
  form.append("file", data.file);
  form.append("round_no", String(data.round_no ?? 1));
  form.append("clarification_type", data.clarification_type ?? "addendum");
  return request<TenderClarification>(`/projects/${projectId}/clarifications/upload`, {
    method: "POST",
    body: form,
  });
}

export function confirmRequirement(id: string): Promise<Requirement> {
  return request<Requirement>(`/requirements/${id}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmed: true }),
  });
}

export function bulkConfirmRequirements(projectId: string, requirementIds: string[]): Promise<{ confirmed_count: number }> {
  return request<{ confirmed_count: number }>(`/projects/${projectId}/requirements/bulk-confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ requirement_ids: requirementIds }),
  });
}

export function updateRequirement(id: string, fields: Partial<Requirement> & Record<string, unknown>): Promise<Requirement> {
  return request<Requirement>(`/requirements/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
}

export function rejectRequirement(id: string, reviewNote?: string): Promise<Requirement> {
  return request<Requirement>(`/requirements/${id}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ review_note: reviewNote ?? "人工从关键约束中排除" }),
  });
}

export function mergeRequirements(targetId: string, sourceRequirementIds: string[]): Promise<Requirement> {
  return request<Requirement>(`/requirements/${targetId}/merge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_requirement_ids: sourceRequirementIds }),
  });
}

export function splitRequirementForReview(id: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/requirements/${id}/split`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ parts: [] }),
  });
}

export function fetchSourceChunk(id: string, options?: { signal?: AbortSignal }): Promise<SourceChunk> {
  return request<SourceChunk>(`/source-chunks/${id}`, { signal: options?.signal });
}

export function fetchTenderSummary(projectId: string, options?: { signal?: AbortSignal }): Promise<TenderSummary> {
  return request<TenderSummary>(`/projects/${projectId}/tender-summary`, { signal: options?.signal });
}

export function buildConstraintSet(projectId: string): Promise<{ id: string; items: unknown[] }> {
  return request<{ id: string; items: unknown[] }>(`/projects/${projectId}/constraint-set`, { method: "POST" });
}

export function fetchConstraintSet(projectId: string, options?: { signal?: AbortSignal }): Promise<{ items: unknown[] }> {
  return request<{ items: unknown[] }>(`/projects/${projectId}/constraint-set`, { signal: options?.signal });
}

export function confirmConstraintSet(projectId: string): Promise<{ id: string; status: string; items: unknown[] }> {
  return request<{ id: string; status: string; items: unknown[] }>(`/projects/${projectId}/constraint-set/confirm`, {
    method: "POST",
  });
}

export function runComplianceCheck(projectId: string): Promise<{ id: string; findings: unknown[] }> {
  return request<{ id: string; findings: unknown[] }>(`/projects/${projectId}/compliance-check`, { method: "POST" });
}

export function fetchSubmissionChecklist(projectId: string, options?: { signal?: AbortSignal }): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/projects/${projectId}/submission-checklist`, { signal: options?.signal });
}

export type AiExtractionRunStatus =
  | "pending"
  | "running"
  | "completed"
  | "partial"
  | "failed"
  | "cancelled";

export type AiExtractionFileCoverage = {
  source_file: string;
  batches: number;
  succeeded: number;
  failed: number;
  needs_review: number;
  skipped: number;
  chunks: number;
  extracted_requirements: number;
  skip_reason: string | null;
};

export type AiExtractionRun = {
  id: string;
  tender_document_id?: string;
  project_id?: string;
  status: AiExtractionRunStatus;
  total_batches: number;
  succeeded_batches: number;
  failed_batches: number;
  skipped_batches: number;
  total_chunks: number;
  covered_chunks: number;
  extracted_requirements: number;
  total_input_tokens: number;
  total_output_tokens: number;
  file_coverage: AiExtractionFileCoverage[];
};

export type AiExtractionBatchStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "skipped"
  | "needs_review";

export type AiExtractionBatch = {
  id: string;
  source_file: string;
  batch_index: number;
  status: AiExtractionBatchStatus;
  chunk_count: number;
  model: string;
  reasoning_effort: string | null;
  retry_count: number;
  max_retries: number;
  extracted_requirements: number;
  dropped_invalid: number;
  error_type: string | null;
  error_message: string | null;
  skip_reason: string | null;
};

export function fetchAiExtractionRun(
  runId: string,
  options?: { signal?: AbortSignal },
): Promise<AiExtractionRun> {
  return request<AiExtractionRun>(`/tender-ai-extraction-runs/${runId}`, {
    signal: options?.signal,
  });
}

export function fetchAiExtractionBatches(
  runId: string,
  status?: AiExtractionBatchStatus,
  options?: { signal?: AbortSignal },
): Promise<AiExtractionBatch[]> {
  const suffix = status ? `?status=${encodeURIComponent(status)}` : "";
  return request<AiExtractionBatch[]>(
    `/tender-ai-extraction-runs/${runId}/batches${suffix}`,
    { signal: options?.signal },
  );
}

export function retryFailedAiExtractionBatches(runId: string): Promise<AiExtractionRun> {
  return request<AiExtractionRun>(`/tender-ai-extraction-runs/${runId}/retry-failed`, {
    method: "POST",
  });
}

export function startTenderAiExtractionRun(
  tenderDocumentId: string,
  body: { mode?: string; model_policy?: string; force_replan?: boolean } = {},
): Promise<AiExtractionRun> {
  return request<AiExtractionRun>(
    `/tender-documents/${tenderDocumentId}/ai-extraction-runs`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

// ── Drafts ──

export interface Draft {
  id: string;
  chapter_code: string;
  content_md: string;
  updated_at: string;
  is_stale?: boolean;
  stale_reason?: string | null;
}

export function fetchDrafts(
  projectId: string,
  options?: { signal?: AbortSignal },
): Promise<Draft[]> {
  return request<Draft[]>(`/projects/${projectId}/drafts`, {
    signal: options?.signal,
  });
}

export function updateDraft(draftId: string, contentMd: string): Promise<Draft> {
  return request<Draft>(`/drafts/${draftId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content_md: contentMd }),
  });
}

export interface BidChapter {
  id: string;
  chapter_code: string;
  chapter_title: string;
  volume_type: string;
  sort_order: number;
  requirement_ids?: string[];
  metadata_json?: Record<string, unknown>;
}

export interface BidOutline {
  id: string;
  project_id: string;
  outline_name: string;
  status: string;
  chapters: BidChapter[];
}

export interface OutlineDiff {
  chapter_id: string;
  chapter_code: string;
  chapter_title: string;
  volume_type: string;
  operation:
    | "add"
    | "remove"
    | "rename"
    | "move"
    | "keep"
    | "keep_template"
    | "keep_mapped"
    | "tender_conflict_override"
    | "mark_manual_required"
    | "mark_external_attached";
  requirement_count: number;
  reason: string;
  source_locator?: string | null;
  proposed_action?: string | null;
}

export interface BidOutlineReconciliation {
  project_id: string;
  outline: BidOutline;
  diffs: OutlineDiff[];
  unresolved_critical_count: number;
  can_confirm: boolean;
  blocking_requirements: Array<Record<string, unknown>>;
}

export interface BusinessBidAssembly {
  project_id: string;
  run: Record<string, unknown>;
  chapters: BidChapter[];
  response_matrix: Array<Record<string, unknown>>;
  missing_materials: Array<Record<string, unknown>>;
  boundary: string;
}

export interface TechnicalWritingPlan {
  project_id: string;
  outline_id: string;
  chapter_count: number;
  chapters: Array<BidChapter & { writing_strategy: string; required_context: string[] }>;
}

export interface ChartAsset {
  id: string;
  project_id: string;
  outline_node_id: string | null;
  chart_type: string;
  title: string;
  spec_json: Record<string, unknown>;
  rendered_svg?: string | null;
  rendered_path?: string | null;
  rendered_png_path?: string | null;
  placeholder_key?: string | null;
  mermaid_source?: string | null;
  status: string;
  version?: number;
  metadata_json?: Record<string, unknown>;
  created_at: string;
  updated_at?: string;
}

export function generateBidOutline(projectId: string): Promise<BidOutline> {
  return request<BidOutline>(`/projects/${projectId}/bid-outline`, {
    method: "POST",
  });
}

export function fetchBidOutline(
  projectId: string,
  options?: { signal?: AbortSignal },
): Promise<BidOutline> {
  return request<BidOutline>(`/projects/${projectId}/bid-outline`, {
    signal: options?.signal,
  });
}

export function updateBidChapter(
  chapterId: string,
  data: {
    chapter_code?: string;
    chapter_title?: string;
    volume_type?: string;
    sort_order?: number;
    outline_md?: string;
    metadata_json?: Record<string, unknown>;
  },
): Promise<BidChapter> {
  return request<BidChapter>(`/bid-outline/chapters/${chapterId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function previewBidOutlineReconciliation(
  projectId: string,
  options?: { signal?: AbortSignal },
): Promise<BidOutlineReconciliation> {
  return request<BidOutlineReconciliation>(`/projects/${projectId}/bid-outline/reconciliation`, {
    signal: options?.signal,
  });
}

export function confirmBidOutline(projectId: string): Promise<BidOutline> {
  return request<BidOutline>(`/projects/${projectId}/bid-outline/confirm`, {
    method: "POST",
  });
}

export function generateBidChapter(projectId: string, chapterId: string): Promise<Draft> {
  return request<Draft>(`/projects/${projectId}/bid-chapters/${chapterId}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
}

export function assembleBusinessBid(projectId: string): Promise<BusinessBidAssembly> {
  return request<BusinessBidAssembly>(`/projects/${projectId}/business-bid/assemble`, {
    method: "POST",
  });
}

export function fetchTechnicalWritingPlan(
  projectId: string,
  options?: { signal?: AbortSignal },
): Promise<TechnicalWritingPlan> {
  return request<TechnicalWritingPlan>(`/projects/${projectId}/technical-bid/writing-plan`, {
    signal: options?.signal,
  });
}

export function generateTechnicalChapter(
  projectId: string,
  chapterId: string,
  data?: { rewrite_note?: string | null; target_pages?: number | null },
): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/projects/${projectId}/technical-bid/chapters/${chapterId}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data ?? {}),
  });
}

export function fetchTechnicalChapterContext(
  projectId: string,
  chapterId: string,
  options?: { signal?: AbortSignal },
): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/projects/${projectId}/technical-bid/chapters/${chapterId}/context`, {
    signal: options?.signal,
  });
}

export function listChartAssets(projectId: string, options?: { signal?: AbortSignal }): Promise<ChartAsset[]> {
  return request<ChartAsset[]>(`/projects/${projectId}/chart-assets`, { signal: options?.signal });
}

export function createChartAsset(
  projectId: string,
  data: { chart_type: string; title: string; spec_json: Record<string, unknown>; outline_node_id?: string | null },
): Promise<ChartAsset> {
  return request<ChartAsset>(`/projects/${projectId}/chart-assets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function generateChartAsset(
  projectId: string,
  data: { chart_type: string; title: string; placeholder_key?: string | null; outline_node_id?: string | null },
): Promise<ChartAsset> {
  return request<ChartAsset>(`/projects/${projectId}/chart-assets/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function approveChartAsset(assetId: string): Promise<ChartAsset> {
  return request<ChartAsset>(`/chart-assets/${assetId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
}

// ── Review Issues ──

export interface ReviewIssue {
  id: string;
  severity: string;
  title: string;
  detail: string | null;
  resolved: boolean;
  metadata_json?: Record<string, unknown>;
}

export function fetchReviewIssues(
  projectId: string,
  options?: { signal?: AbortSignal },
): Promise<ReviewIssue[]> {
  return request<ReviewIssue[]>(`/projects/${projectId}/review-issues`, {
    signal: options?.signal,
  });
}

export function resolveIssue(issueId: string): Promise<ReviewIssue> {
  return request<ReviewIssue>(`/review-issues/${issueId}/resolve`, {
    method: "POST",
  });
}

export interface BidReviewResult {
  issue_count: number;
  blocking_issue_count: number;
  can_export: boolean;
}

export function runBidReview(projectId: string): Promise<BidReviewResult> {
  return request<BidReviewResult>(`/projects/${projectId}/bid-review`, {
    method: "POST",
  });
}

// ── Compliance Matrix ──

export interface ComplianceEntry {
  requirement_id: string;
  requirement_title: string;
  category: string;
  chapter_code: string | null;
  coverage: string;
}

export function fetchComplianceMatrix(
  projectId: string,
  options?: { signal?: AbortSignal },
): Promise<ComplianceEntry[]> {
  return request<ComplianceEntry[]>(
    `/projects/${projectId}/compliance-matrix`,
    { signal: options?.signal },
  );
}

// ── Export ──

export interface ExportGates {
  gates: {
    veto_confirmed: boolean;
    unconfirmed_veto_count: number;
    review_passed: boolean;
    blocking_issue_count: number;
    charts_approved: boolean;
    unapproved_chart_count: number;
    referenced_chart_count: number;
    constraints_confirmed: boolean;
    legacy_pre_constraint_set: boolean;
    critical_constraints_resolved: boolean;
    unresolved_critical_constraint_count: number;
    template_required_items_rendered: boolean;
    required_template_failed_count: number;
    failed_required_template_items?: string[];
    stale_artifacts_clear: boolean;
    stale_artifact_count: number;
    format_passed: boolean;
    format_status: "passed" | "failed" | "warning_not_checked";
    format_message?: string;
  };
  can_export: boolean;
}

export interface ExportRecord {
  id: string;
  status: string;
  template_name: string | null;
  export_key: string | null;
  created_at: string;
  mode?: ExportMode;
}

export type ExportMode = "single_docx" | "multi_docx_zip" | "multi_doc_zip";

export function fetchExportGates(
  projectId: string,
  options?: { signal?: AbortSignal },
): Promise<ExportGates> {
  return request<ExportGates>(`/projects/${projectId}/export-gates`, {
    signal: options?.signal,
  });
}

export function fetchExports(
  projectId: string,
  options?: { signal?: AbortSignal },
): Promise<ExportRecord[]> {
  return request<ExportRecord[]>(`/projects/${projectId}/exports`, {
    signal: options?.signal,
  });
}

export function createExport(
  projectId: string,
  mode: ExportMode = "single_docx",
): Promise<ExportRecord> {
  return request<ExportRecord>(`/projects/${projectId}/exports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
}

export interface DeliveryPackage {
  id: string;
  version_no: number;
  status: string;
  package_name: string;
  created_at: string;
}

export function createDeliveryPackage(projectId: string): Promise<DeliveryPackage> {
  return request<DeliveryPackage>(`/projects/${projectId}/delivery-package`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
}

export function fetchDeliveryPackages(
  projectId: string,
  options?: { signal?: AbortSignal },
): Promise<DeliveryPackage[]> {
  return request<DeliveryPackage[]>(`/projects/${projectId}/delivery-packages`, {
    signal: options?.signal,
  });
}

export function deliveryPackageDownloadUrl(packageId: string): string {
  return buildApiUrl(`/delivery-packages/${packageId}/download`);
}

// ── Template Packages ──

export type TemplateSourceType =
  | "company_profile"
  | "person_profile"
  | "project_performance"
  | "qualification_certificate"
  | "financial_statement"
  | "evidence_asset";

export type TemplateSelectionMode = "all" | "latest" | "first" | "by_id";
export type TemplateFieldMappingMode = "augment" | "replace";

export interface TemplateFieldMapping {
  target_field: string;
  source_field?: string;
  source_fields?: string[];
  transform?: "copy" | "join" | "date" | "number";
  join_with?: string;
  date_format?: string;
  decimals?: number;
  default_value?: unknown;
}

export interface TemplateItem {
  id: string;
  item_code: string | null;
  item_name: string;
  filename: string;
  relative_path: string;
  source_kind: string;
  item_type: string;
  render_mode: string;
  is_required: boolean;
  sort_order: number;
}

export interface TemplatePackageSummary {
  id: string;
  package_key: string;
  display_name: string;
  package_type: string;
  category_code: string | null;
  source_root: string;
  item_count: number;
}

export interface TemplatePackageDetail extends TemplatePackageSummary {
  items: TemplateItem[];
}

export interface TemplateBindingRule {
  id: string;
  template_item_id: string;
  binding_name: string;
  source_type: TemplateSourceType;
  selection_mode: TemplateSelectionMode;
  source_filters: Record<string, unknown>;
  field_mappings: TemplateFieldMapping[];
  field_mapping_mode: TemplateFieldMappingMode;
  output_key: string;
  required: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface TemplateBindingPayload {
  binding_name: string;
  source_type: TemplateSourceType;
  selection_mode: TemplateSelectionMode;
  source_filters: Record<string, unknown>;
  field_mappings: TemplateFieldMapping[];
  field_mapping_mode: TemplateFieldMappingMode;
  output_key: string;
  required: boolean;
  sort_order: number;
}

export interface TemplateResolvedBinding {
  binding_id: string;
  binding_name: string;
  source_type: TemplateSourceType;
  selection_mode: TemplateSelectionMode;
  field_mappings: TemplateFieldMapping[];
  field_mapping_mode: TemplateFieldMappingMode;
  output_key: string;
  required: boolean;
  filters: Record<string, unknown>;
  matched_count: number;
  data: unknown;
}

export interface TemplateItemRenderContext {
  item_id: string;
  item_code: string | null;
  item_name: string;
  filename: string;
  render_mode: string;
  binding_count: number;
  ready: boolean;
  missing_required_bindings: string[];
  context: Record<string, unknown>;
  bindings: TemplateResolvedBinding[];
}

export interface TemplatePackageRenderContextItem extends TemplateItemRenderContext {}

export interface TemplatePackageRenderContext {
  package_id: string;
  package_key: string;
  display_name: string;
  package_type: string;
  ready_item_count: number;
  total_item_count: number;
  items: TemplatePackageRenderContextItem[];
}

export interface TemplateRenderPreflightIssue {
  code: string;
  message: string;
  bindings?: string[];
  asset_id?: string;
  asset_name?: string;
  file_name?: string;
}

export interface TemplatePackageRenderPreflightItem {
  item_id: string;
  item_name: string;
  filename: string;
  relative_path: string;
  render_mode: string;
  item_type: string;
  ready: boolean;
  issue_count: number;
  issues: TemplateRenderPreflightIssue[];
  missing_required_bindings: string[];
  asset_count: number;
  valid_asset_count: number;
  invalid_asset_count: number;
  context_keys: string[];
}

export interface TemplatePackageRenderPreflight {
  package_id: string;
  package_key: string;
  display_name: string;
  package_type: string;
  total_item_count: number;
  ready_item_count: number;
  blocked_item_count: number;
  issue_count: number;
  ready: boolean;
  items: TemplatePackageRenderPreflightItem[];
}

export interface TemplateFieldMappingSuggestionGroup {
  source_type: TemplateSourceType;
  field_mapping_mode: TemplateFieldMappingMode;
  field_mappings: TemplateFieldMapping[];
  confidence: number;
}

export interface TemplateFieldMappingSuggestions {
  item_id: string;
  item_code: string | null;
  item_name: string;
  suggestions: TemplateFieldMappingSuggestionGroup[];
}

export interface TemplatePackageCategory {
  code: string;
  display_name: string;
  description: string | null;
  sort_order: number;
  enabled: boolean;
  metadata_json: Record<string, unknown>;
}

export interface TemplatePackageUploadPayload {
  project_type: string;
  template_kind: "business" | "technical";
  display_name?: string;
  category_code?: string;
  file: File;
}

export function listTemplatePackages(options?: {
  signal?: AbortSignal;
  categoryCode?: string;
}): Promise<TemplatePackageSummary[]> {
  const params = new URLSearchParams();
  if (options?.categoryCode) params.set("category_code", options.categoryCode);
  const suffix = params.size > 0 ? `?${params.toString()}` : "";
  return request<TemplatePackageSummary[]>(`/template-packages${suffix}`, {
    signal: options?.signal,
  });
}

export function listTemplatePackageCategories(options?: {
  signal?: AbortSignal;
}): Promise<TemplatePackageCategory[]> {
  return request<TemplatePackageCategory[]>("/template-package-categories", {
    signal: options?.signal,
  });
}

export function fetchTemplatePackageDetail(
  packageId: string,
  options?: { signal?: AbortSignal },
): Promise<TemplatePackageDetail> {
  return request<TemplatePackageDetail>(`/template-packages/${packageId}`, {
    signal: options?.signal,
  });
}

export interface TemplateSelectionCandidate {
  package_id: string;
  package_key: string;
  display_name: string;
  package_type: string;
  category_code: string | null;
  score: number;
  reasons: string[];
  warnings: string[];
}

export interface TemplateSelectionPreview {
  project_id: string;
  recommended: TemplateSelectionCandidate | null;
  candidates: TemplateSelectionCandidate[];
}

export interface BusinessTemplatePreviewPage {
  page_number: number;
  blocks: string[];
}

export interface BusinessTemplatePreviewChapter {
  chapter_code: string;
  chapter_title: string;
  page_start: number;
  page_end: number;
  pages: BusinessTemplatePreviewPage[];
}

export interface BusinessTemplatePreview {
  package_title: string;
  chapters: BusinessTemplatePreviewChapter[];
}

export function previewTemplateSelection(projectId: string, options?: { signal?: AbortSignal }): Promise<TemplateSelectionPreview> {
  return request<TemplateSelectionPreview>(`/projects/${projectId}/template-selection`, { signal: options?.signal });
}

export function confirmTemplateSelection(projectId: string, packageId: string): Promise<{ selected_template_package_id: string }> {
  return request<{ selected_template_package_id: string }>(`/projects/${projectId}/template-selection`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ package_id: packageId }),
  });
}

export function fetchBusinessTemplatePreview(projectId: string, options?: { signal?: AbortSignal }): Promise<BusinessTemplatePreview> {
  return request<BusinessTemplatePreview>(`/projects/${projectId}/business-template-preview`, { signal: options?.signal });
}

export function fetchTemplatePackageRenderContext(
  packageId: string,
  options?: { signal?: AbortSignal },
): Promise<TemplatePackageRenderContext> {
  return request<TemplatePackageRenderContext>(`/template-packages/${packageId}/render-context`, {
    signal: options?.signal,
  });
}

export function fetchTemplatePackageRenderPreflight(
  packageId: string,
  options?: { signal?: AbortSignal },
): Promise<TemplatePackageRenderPreflight> {
  return request<TemplatePackageRenderPreflight>(`/template-packages/${packageId}/render-preflight`, {
    signal: options?.signal,
  });
}

export function fetchTemplateItemBindings(
  itemId: string,
  options?: { signal?: AbortSignal },
): Promise<TemplateBindingRule[]> {
  return request<TemplateBindingRule[]>(`/template-items/${itemId}/bindings`, {
    signal: options?.signal,
  });
}

export function createTemplateItemBinding(
  itemId: string,
  data: TemplateBindingPayload,
): Promise<TemplateBindingRule> {
  return request<TemplateBindingRule>(`/template-items/${itemId}/bindings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function updateTemplateBindingRule(
  ruleId: string,
  data: Partial<TemplateBindingPayload>,
): Promise<TemplateBindingRule> {
  return request<TemplateBindingRule>(`/template-bindings/${ruleId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function deleteTemplateBindingRule(
  ruleId: string,
): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/template-bindings/${ruleId}`, {
    method: "DELETE",
  });
}

export function fetchTemplateItemRenderContext(
  itemId: string,
  options?: { signal?: AbortSignal },
): Promise<TemplateItemRenderContext> {
  return request<TemplateItemRenderContext>(`/template-items/${itemId}/render-context`, {
    signal: options?.signal,
  });
}

export function fetchTemplateFieldMappingSuggestions(
  itemId: string,
  options?: { signal?: AbortSignal },
): Promise<TemplateFieldMappingSuggestions> {
  return request<TemplateFieldMappingSuggestions>(`/template-items/${itemId}/field-mapping-suggestions`, {
    signal: options?.signal,
  });
}

export function uploadTemplatePackage(data: TemplatePackageUploadPayload): Promise<TemplatePackageDetail> {
  const form = new FormData();
  form.append("project_type", data.project_type);
  form.append("template_kind", data.template_kind);
  if (data.display_name) form.append("display_name", data.display_name);
  if (data.category_code) form.append("category_code", data.category_code);
  form.append("file", data.file);
  return request<TemplatePackageDetail>("/template-packages/upload", {
    method: "POST",
    body: form,
  });
}

// ── Master Data ──

export interface LibraryCompany {
  id: string;
  company_key: string;
  company_name: string;
  company_type: string | null;
  enabled: boolean;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface CompanyProfile {
  id: string;
  library_company_id: string | null;
  company_name: string;
  company_code: string | null;
  unified_social_credit_code: string | null;
  registered_address: string | null;
  contact_name: string | null;
  contact_phone: string | null;
  contact_email: string | null;
  website: string | null;
  registered_capital: string | null;
  company_type: string | null;
  business_scope: string | null;
  profile_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export type CompanyAssetType = "vehicle" | "machine" | "tool" | "safety";
export type CompanyAssetOwnership = "self" | "leased" | "third_party";
export type CompanyAssetStatus = "active" | "maintenance" | "retired";

export interface CompanyAsset {
  id: string;
  library_company_id: string;
  asset_type: CompanyAssetType;
  name: string;
  spec_model: string | null;
  serial_no: string | null;
  manufacturer: string | null;
  quantity: string;
  unit: string;
  ownership: CompanyAssetOwnership;
  acquired_at: string | null;
  expires_at: string | null;
  technical_condition: string | null;
  status: CompanyAssetStatus;
  location: string | null;
  extras: Record<string, unknown>;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface CompanyAssetWithAttachments extends CompanyAsset {
  attachments: EvidenceAsset[];
}

export interface PersonProfile {
  id: string;
  library_company_id: string | null;
  full_name: string;
  gender: string | null;
  age: number | null;
  education: string | null;
  title: string | null;
  role_name: string | null;
  specialty: string | null;
  years_experience: number | null;
  phone: string | null;
  email: string | null;
  resume_text: string | null;
  profile_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface PersonProfileWithAttachments extends PersonProfile {
  attachments: EvidenceAsset[];
}

export interface PersonProfilePayload {
  library_company_id?: string | null;
  full_name: string;
  gender?: string | null;
  age?: number | null;
  education?: string | null;
  title?: string | null;
  role_name?: string | null;
  specialty?: string | null;
  years_experience?: number | null;
  phone?: string | null;
  email?: string | null;
  resume_text?: string | null;
  profile_json?: Record<string, unknown>;
}

export type PersonProfileUpdatePayload = Partial<PersonProfilePayload>;

export interface EvidenceAsset {
  id: string;
  library_company_id: string | null;
  owner_type: string;
  owner_id: string | null;
  asset_name: string;
  asset_domain: string;
  asset_category: string;
  asset_type: string;
  file_name: string;
  media_type: string | null;
  issuer_name: string | null;
  issued_on: string | null;
  expires_on: string | null;
  metadata_json: Record<string, unknown>;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface CompanyContractPerformance {
  id: string;
  library_company_id: string | null;
  auto_number: number;
  contract_name: string;
  party_a_company: string;
  contract_category: string | null;
  engineering_category: string | null;
  contract_amount: string | null;
  contract_signed_date: string | null;
  contract_completed_date: string | null;
  contract_status: string | null;
  signature_asset_id: string | null;
  signature_asset_name: string | null;
  invoice_asset_id: string | null;
  invoice_asset_name: string | null;
  invoice_verification_asset_id: string | null;
  invoice_verification_asset_name: string | null;
  performance_evaluation_asset_id: string | null;
  performance_evaluation_asset_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface CompanyContractPerformanceCreatePayload {
  library_company_id: string;
  contract_name: string;
  party_a_company: string;
  contract_category?: string | null;
  engineering_category?: string | null;
  contract_amount?: string | null;
  contract_signed_date?: string | null;
  contract_completed_date?: string | null;
  contract_status?: string | null;
  signature_asset_id?: string | null;
  signature_asset_name?: string | null;
  invoice_asset_id?: string | null;
  invoice_asset_name?: string | null;
  invoice_verification_asset_id?: string | null;
  invoice_verification_asset_name?: string | null;
  performance_evaluation_asset_id?: string | null;
  performance_evaluation_asset_name?: string | null;
}

export interface CompanyContractPerformanceUpdatePayload {
  contract_name?: string;
  party_a_company?: string;
  contract_category?: string | null;
  engineering_category?: string | null;
  contract_amount?: string | null;
  contract_signed_date?: string | null;
  contract_completed_date?: string | null;
  contract_status?: string | null;
  signature_asset_id?: string | null;
  signature_asset_name?: string | null;
  invoice_asset_id?: string | null;
  invoice_asset_name?: string | null;
  invoice_verification_asset_id?: string | null;
  invoice_verification_asset_name?: string | null;
  performance_evaluation_asset_id?: string | null;
  performance_evaluation_asset_name?: string | null;
}

export interface AssetTaxonomyCategory {
  code: string;
  label: string;
}

export interface AssetTaxonomyDomain {
  domain: string;
  label: string;
  categories: [string, string][];
}

export interface AssetTaxonomyResponse {
  domains: AssetTaxonomyDomain[];
}

export interface LibraryCompanyCreatePayload {
  company_name: string;
  company_key?: string;
  company_type?: string;
  enabled?: boolean;
  metadata_json?: Record<string, unknown>;
}

export interface CompanyAssetPayload {
  asset_type: CompanyAssetType;
  name: string;
  spec_model?: string | null;
  serial_no?: string | null;
  manufacturer?: string | null;
  quantity?: string | number;
  unit: string;
  ownership: CompanyAssetOwnership;
  acquired_at?: string | null;
  expires_at?: string | null;
  technical_condition?: string | null;
  status?: CompanyAssetStatus;
  location?: string | null;
  extras?: Record<string, unknown>;
  notes?: string | null;
}

export interface EquipmentSelection {
  id: string;
  project_id: string;
  asset_id: string;
  asset_type: CompanyAssetType;
  intended_role: string | null;
  snapshot_json: Record<string, unknown> | null;
  display_order: number;
  confirmed: boolean;
  confirmed_at: string | null;
  created_at: string;
  updated_at: string;
}

export type EquipmentPreviewRow = Record<string, string>;
export type EquipmentPreview = Record<CompanyAssetType, EquipmentPreviewRow[]>;

export interface PersonnelSelection {
  id: string;
  project_id: string;
  person_id: string;
  intended_role: string | null;
  snapshot_json: Record<string, unknown> | null;
  display_order: number;
  confirmed: boolean;
  confirmed_at: string | null;
  created_at: string;
  updated_at: string;
}

export type PersonnelPreviewRow = Record<string, string>;

export interface EvidenceAssetUploadPayload {
  library_company_id?: string;
  owner_type: string;
  owner_id?: string;
  asset_name: string;
  asset_domain: string;
  asset_category: string;
  asset_type?: string;
  issuer_name?: string;
  issued_on?: string;
  expires_on?: string;
  sort_order?: number;
  metadata_json?: Record<string, unknown>;
  file: File;
}

export function fetchLibraryCompanies(options?: {
  signal?: AbortSignal;
}): Promise<LibraryCompany[]> {
  return request<LibraryCompany[]>("/master-data/library-companies", {
    signal: options?.signal,
  });
}

export function createLibraryCompany(data: LibraryCompanyCreatePayload): Promise<LibraryCompany> {
  return request<LibraryCompany>("/master-data/library-companies", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function deleteLibraryCompany(recordId: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/master-data/library-companies/${recordId}`, {
    method: "DELETE",
  });
}

export function fetchAssetTaxonomy(options?: {
  signal?: AbortSignal;
}): Promise<AssetTaxonomyResponse> {
  return request<AssetTaxonomyResponse>("/master-data/asset-taxonomy", {
    signal: options?.signal,
  });
}

export function fetchCompanyProfiles(options?: {
  signal?: AbortSignal;
  libraryCompanyId?: string;
}): Promise<CompanyProfile[]> {
  const params = new URLSearchParams();
  if (options?.libraryCompanyId) params.set("library_company_id", options.libraryCompanyId);
  const suffix = params.size > 0 ? `?${params.toString()}` : "";
  return request<CompanyProfile[]>(`/master-data/company-profiles${suffix}`, {
    signal: options?.signal,
  });
}

export function fetchCompanyAssets(options: {
  signal?: AbortSignal;
  libraryCompanyId: string;
  assetType?: CompanyAssetType;
  status?: CompanyAssetStatus | "";
  q?: string;
}): Promise<CompanyAsset[]> {
  const params = new URLSearchParams();
  if (options.assetType) params.set("asset_type", options.assetType);
  if (options.status) params.set("status", options.status);
  if (options.q?.trim()) params.set("q", options.q.trim());
  const suffix = params.size > 0 ? `?${params.toString()}` : "";
  return request<CompanyAsset[]>(
    `/master-data/library-companies/${options.libraryCompanyId}/assets${suffix}`,
    { signal: options.signal },
  );
}

export function createCompanyAsset(
  libraryCompanyId: string,
  data: CompanyAssetPayload,
): Promise<CompanyAsset> {
  return request<CompanyAsset>(`/master-data/library-companies/${libraryCompanyId}/assets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function updateCompanyAsset(
  recordId: string,
  data: Partial<CompanyAssetPayload>,
): Promise<CompanyAsset> {
  return request<CompanyAsset>(`/master-data/assets/${recordId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function deleteCompanyAsset(recordId: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/master-data/assets/${recordId}`, {
    method: "DELETE",
  });
}

export function retireCompanyAsset(recordId: string): Promise<CompanyAsset> {
  return request<CompanyAsset>(`/master-data/assets/${recordId}/retire`, {
    method: "POST",
  });
}

export function fetchProjectEquipmentAssets(options: {
  projectId: string;
  assetType?: CompanyAssetType;
  q?: string;
  status?: CompanyAssetStatus | "";
  validOnly?: boolean;
  signal?: AbortSignal;
}): Promise<CompanyAsset[]> {
  const params = new URLSearchParams();
  if (options.assetType) params.set("asset_type", options.assetType);
  if (options.q?.trim()) params.set("q", options.q.trim());
  if (options.status) params.set("status", options.status);
  if (options.validOnly) params.set("valid_only", "true");
  const suffix = params.size > 0 ? `?${params.toString()}` : "";
  return request<CompanyAsset[]>(`/projects/${options.projectId}/equipment/assets${suffix}`, {
    signal: options.signal,
  });
}

export function fetchProjectEquipmentSelections(
  projectId: string,
  options?: { signal?: AbortSignal },
): Promise<EquipmentSelection[]> {
  return request<EquipmentSelection[]>(`/projects/${projectId}/equipment/selections`, {
    signal: options?.signal,
  });
}

export function createProjectEquipmentSelection(
  projectId: string,
  data: { asset_id: string },
): Promise<EquipmentSelection> {
  return request<EquipmentSelection>(`/projects/${projectId}/equipment/selections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function updateProjectEquipmentSelection(
  projectId: string,
  selectionId: string,
  data: { intended_role?: string | null; display_order?: number },
): Promise<EquipmentSelection> {
  return request<EquipmentSelection>(`/projects/${projectId}/equipment/selections/${selectionId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function deleteProjectEquipmentSelection(
  projectId: string,
  selectionId: string,
): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/projects/${projectId}/equipment/selections/${selectionId}`, {
    method: "DELETE",
  });
}

export function confirmProjectEquipmentSelections(projectId: string): Promise<EquipmentSelection[]> {
  return request<EquipmentSelection[]>(`/projects/${projectId}/equipment/selections/confirm`, {
    method: "POST",
  });
}

export function fetchProjectEquipmentPreview(
  projectId: string,
  options?: { signal?: AbortSignal },
): Promise<EquipmentPreview> {
  return request<EquipmentPreview>(`/projects/${projectId}/equipment/preview`, {
    signal: options?.signal,
  });
}

export async function downloadProjectEquipmentXlsx(projectId: string): Promise<Blob> {
  const res = await fetch(buildApiUrl(`/projects/${projectId}/equipment/attachment-xlsx`), {
    headers: getAuthHeaders(),
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }
  return res.blob();
}

export function fetchProjectPersonnelPeople(options: {
  projectId: string;
  libraryCompanyId?: string;
  q?: string;
  signal?: AbortSignal;
}): Promise<PersonProfile[]> {
  const params = new URLSearchParams();
  if (options.libraryCompanyId) params.set("library_company_id", options.libraryCompanyId);
  if (options.q?.trim()) params.set("q", options.q.trim());
  const suffix = params.size > 0 ? `?${params.toString()}` : "";
  return request<PersonProfile[]>(`/projects/${options.projectId}/personnel/people${suffix}`, {
    signal: options.signal,
  });
}

export function fetchProjectPersonnelSelections(
  projectId: string,
  options?: { signal?: AbortSignal },
): Promise<PersonnelSelection[]> {
  return request<PersonnelSelection[]>(`/projects/${projectId}/personnel/selections`, {
    signal: options?.signal,
  });
}

export function createProjectPersonnelSelection(
  projectId: string,
  data: { person_id: string },
): Promise<PersonnelSelection> {
  return request<PersonnelSelection>(`/projects/${projectId}/personnel/selections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function updateProjectPersonnelSelection(
  projectId: string,
  selectionId: string,
  data: { intended_role?: string | null; display_order?: number },
): Promise<PersonnelSelection> {
  return request<PersonnelSelection>(`/projects/${projectId}/personnel/selections/${selectionId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function deleteProjectPersonnelSelection(
  projectId: string,
  selectionId: string,
): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/projects/${projectId}/personnel/selections/${selectionId}`, {
    method: "DELETE",
  });
}

export function confirmProjectPersonnelSelections(projectId: string): Promise<PersonnelSelection[]> {
  return request<PersonnelSelection[]>(`/projects/${projectId}/personnel/selections/confirm`, {
    method: "POST",
  });
}

export function fetchProjectPersonnelPreview(
  projectId: string,
  options?: { signal?: AbortSignal },
): Promise<PersonnelPreviewRow[]> {
  return request<PersonnelPreviewRow[]>(`/projects/${projectId}/personnel/preview`, {
    signal: options?.signal,
  });
}

export function fetchPeople(options?: {
  signal?: AbortSignal;
  libraryCompanyId?: string;
}): Promise<PersonProfile[]> {
  const params = new URLSearchParams();
  if (options?.libraryCompanyId) params.set("library_company_id", options.libraryCompanyId);
  const suffix = params.size > 0 ? `?${params.toString()}` : "";
  return request<PersonProfile[]>(`/master-data/people${suffix}`, {
    signal: options?.signal,
  });
}

export function createPerson(data: PersonProfilePayload): Promise<PersonProfile> {
  return request<PersonProfile>("/master-data/people", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function updatePerson(recordId: string, data: PersonProfileUpdatePayload): Promise<PersonProfile> {
  return request<PersonProfile>(`/master-data/people/${recordId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function deletePerson(recordId: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/master-data/people/${recordId}`, {
    method: "DELETE",
  });
}

export function fetchEvidenceAssets(options?: {
  signal?: AbortSignal;
  libraryCompanyId?: string;
  assetDomain?: string;
}): Promise<EvidenceAsset[]> {
  const params = new URLSearchParams();
  if (options?.libraryCompanyId) params.set("library_company_id", options.libraryCompanyId);
  if (options?.assetDomain) params.set("asset_domain", options.assetDomain);
  const suffix = params.size > 0 ? `?${params.toString()}` : "";
  return request<EvidenceAsset[]>(`/master-data/evidence-assets${suffix}`, {
    signal: options?.signal,
  });
}

export function uploadEvidenceAsset(data: EvidenceAssetUploadPayload): Promise<EvidenceAsset> {
  const form = new FormData();
  if (data.library_company_id) form.append("library_company_id", data.library_company_id);
  form.append("owner_type", data.owner_type);
  if (data.owner_id) form.append("owner_id", data.owner_id);
  form.append("asset_name", data.asset_name);
  form.append("asset_domain", data.asset_domain);
  form.append("asset_category", data.asset_category);
  form.append("asset_type", data.asset_type ?? data.asset_category);
  if (data.issuer_name) form.append("issuer_name", data.issuer_name);
  if (data.issued_on) form.append("issued_on", data.issued_on);
  if (data.expires_on) form.append("expires_on", data.expires_on);
  form.append("sort_order", String(data.sort_order ?? 0));
  form.append("metadata_json", JSON.stringify(data.metadata_json ?? {}));
  form.append("file", data.file);
  return request<EvidenceAsset>("/master-data/evidence-assets/upload", {
    method: "POST",
    body: form,
  });
}

export function replaceEvidenceAssetFile(assetId: string, file: File): Promise<EvidenceAsset> {
  const form = new FormData();
  form.append("file", file);
  return request<EvidenceAsset>(`/master-data/evidence-assets/${assetId}/replace-file`, {
    method: "POST",
    body: form,
  });
}

export function deleteEvidenceAsset(assetId: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/master-data/evidence-assets/${assetId}`, {
    method: "DELETE",
  });
}

export function fetchCompanyContractPerformances(options: {
  signal?: AbortSignal;
  libraryCompanyId: string;
}): Promise<CompanyContractPerformance[]> {
  const params = new URLSearchParams();
  params.set("library_company_id", options.libraryCompanyId);
  return request<CompanyContractPerformance[]>(`/master-data/company-contract-performances?${params.toString()}`, {
    signal: options.signal,
  });
}

export function createCompanyContractPerformance(
  data: CompanyContractPerformanceCreatePayload,
): Promise<CompanyContractPerformance> {
  return request<CompanyContractPerformance>("/master-data/company-contract-performances", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function updateCompanyContractPerformance(
  recordId: string,
  data: CompanyContractPerformanceUpdatePayload,
): Promise<CompanyContractPerformance> {
  return request<CompanyContractPerformance>(`/master-data/company-contract-performances/${recordId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function deleteCompanyContractPerformance(recordId: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/master-data/company-contract-performances/${recordId}`, {
    method: "DELETE",
  });
}

export function companyContractPerformanceExportUrl(libraryCompanyId: string): string {
  const params = new URLSearchParams();
  params.set("library_company_id", libraryCompanyId);
  return buildApiUrl(`/master-data/company-contract-performances/export?${params.toString()}`);
}

export function evidenceAssetDownloadUrl(assetId: string): string {
  return buildApiUrl(`/master-data/evidence-assets/${assetId}/download`);
}

// ── Table Override ──

export function submitTableOverride(
  tableId: string,
  overrideJson: object,
): Promise<ParseTable> {
  return request<ParseTable>(`/tables/${tableId}/override`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ override_json: overrideJson }),
  });
}

// ── Settings ──

export type AgentType = "ocr" | "llm";

export interface AgentConfig {
  agent_key: string;
  display_name: string;
  description: string;
  agent_type: AgentType;
  base_url: string;
  api_key_display: string;
  primary_model: string;
  fallback_base_url: string;
  fallback_api_key_display: string;
  fallback_model: string;
  enabled: boolean;
  updated_at: string;
}

export interface AgentConfigUpdate {
  base_url?: string;
  api_key?: string;
  primary_model?: string;
  fallback_base_url?: string;
  fallback_api_key?: string;
  fallback_model?: string;
  enabled?: boolean;
}

export function fetchAgentConfigs(options?: {
  signal?: AbortSignal;
}): Promise<AgentConfig[]> {
  return request<AgentConfig[]>("/settings/agents", {
    signal: options?.signal,
  });
}

export function updateAgentConfig(
  agentKey: string,
  data: AgentConfigUpdate,
): Promise<AgentConfig> {
  return request<AgentConfig>(`/settings/agents/${agentKey}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function testAgentConnection(
  agentKey: string,
): Promise<{ success: boolean; message: string }> {
  return request(`/settings/agents/${agentKey}/test`, { method: "POST" });
}

export interface SkillDefinition {
  skill_name: string;
  description: string;
  tool_names: string[];
  prompt_template_id: string | null;
  version: number;
  active: boolean;
  created_at: string;
}

export interface SkillDefinitionUpdate {
  description?: string;
  tool_names?: string[];
  prompt_template_id?: string | null;
  version?: number;
  active?: boolean;
}

export interface SkillDefinitionCreate extends SkillDefinitionUpdate {
  skill_name: string;
}

export interface SkillSyncResult {
  inserted: number;
  updated: number;
  total: number;
  skill_names: string[];
}

export function fetchSkillDefinitions(options?: {
  signal?: AbortSignal;
}): Promise<SkillDefinition[]> {
  return request<SkillDefinition[]>("/settings/skills", {
    signal: options?.signal,
  });
}

export function createSkillDefinition(
  data: SkillDefinitionCreate,
): Promise<SkillDefinition> {
  return request<SkillDefinition>("/settings/skills", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function updateSkillDefinition(
  skillName: string,
  data: SkillDefinitionUpdate,
): Promise<SkillDefinition> {
  return request<SkillDefinition>(`/settings/skills/${encodeURIComponent(skillName)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function deleteSkillDefinition(
  skillName: string,
): Promise<{ skill_name: string; deleted: boolean }> {
  return request(`/settings/skills/${encodeURIComponent(skillName)}`, {
    method: "DELETE",
  });
}

export function syncDefaultSkills(): Promise<SkillSyncResult> {
  return request<SkillSyncResult>("/settings/skills/sync-defaults", {
    method: "POST",
  });
}

// ── Auth ──

export interface LoginResponse {
  token: string;
  username: string;
  display_name: string;
  role: string;
}

export interface MeResponse {
  username: string;
  display_name: string;
  role: string;
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const url = buildApiUrl("/auth/login");
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `HTTP ${res.status}`);
  }
  const data: LoginResponse = await res.json();
  localStorage.setItem("tender_token", data.token);
  return data;
}

export function logout(): Promise<void> {
  return request<void>("/auth/logout", { method: "POST" }).finally(() => {
    localStorage.removeItem("tender_token");
  });
}

export function fetchMe(options?: {
  signal?: AbortSignal;
}): Promise<MeResponse> {
  return request<MeResponse>("/auth/me", { signal: options?.signal });
}


export interface CompanybaseIssue {
  severity: string;
  sheet: string;
  row: number | null;
  message: string;
}

export interface CompanybaseReport {
  summary: Record<string, number>;
  issues: CompanybaseIssue[];
  p0_count: number;
  p1_count: number;
  actions: { created: number; updated: number; skipped: number };
  dry_run: boolean;
}

export function validateCompanybaseWorkbook(file: File): Promise<CompanybaseReport> {
  const form = new FormData();
  form.append("file", file);
  return request<CompanybaseReport>("/master-data/companybase/validate", { method: "POST", body: form });
}

export function importCompanybaseWorkbook(file: File, dryRun: boolean): Promise<CompanybaseReport> {
  const form = new FormData();
  form.append("file", file);
  return request<CompanybaseReport>(`/master-data/companybase/import?dry_run=${dryRun ? "true" : "false"}`, { method: "POST", body: form });
}

export function backupCompanybaseUrl(): string {
  return buildApiUrl("/master-data/companybase/backup");
}

// ── Users ──

export interface SystemUser {
  id: string;
  username: string;
  display_name: string;
  role: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface UserCreateData {
  username: string;
  password: string;
  display_name: string;
  role: string;
}

export interface UserUpdateData {
  display_name?: string;
  role?: string;
  password?: string;
  enabled?: boolean;
}

export function fetchUsers(options?: {
  signal?: AbortSignal;
}): Promise<SystemUser[]> {
  return request<SystemUser[]>("/users", { signal: options?.signal });
}

export function createUser(data: UserCreateData): Promise<SystemUser> {
  return request<SystemUser>("/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function updateUser(userId: string, data: UserUpdateData): Promise<SystemUser> {
  return request<SystemUser>(`/users/${userId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function deleteUser(userId: string): Promise<void> {
  return request<void>(`/users/${userId}`, { method: "DELETE" });
}

// ── Standards ──

export interface Standard {
  id: string;
  standard_code: string;
  standard_name: string;
  version_year: string | null;
  specialty: string | null;
  status: string | null;
  processing_status: string;
  ocr_status: string | null;
  ai_status: string | null;
  error_message?: string | null;
  queue_position?: number | null;
  clause_count: number;
  is_dev_artifact?: boolean;
  created_at: string | null;
}

export interface StandardDetail extends Standard {
  error_message: string | null;
  processing_started_at: string | null;
  processing_finished_at: string | null;
  clause_tree: StandardClauseNode[];
}

export interface StandardViewerData extends StandardDetail {
  document_id: string;
  pdf_url: string;
}

export interface StandardClause {
  id: string;
  clause_no: string | null;
  // "outline" is used by the merged viewer tree for OCR-derived directory nodes.
  node_type?: string;
  node_key?: string | null;
  node_label?: string | null;
  clause_title: string | null;
  clause_text: string | null;
  summary: string | null;
  tags: string[];
  clause_type: string;
  source_type?: string;
  source_label?: string | null;
  page_start: number | null;
  page_end: number | null;
  sort_order: number | null;
  parent_id: string | null;
}

export interface StandardClauseNode extends StandardClause {
  children: StandardClauseNode[];
}

export interface StandardSearchHit {
  standard_id: string;
  standard_name: string;
  specialty: string | null;
  clause_id: string;
  clause_no: string | null;
  tags: string[];
  summary: string | null;
  page_start: number | null;
  page_end: number | null;
}

export interface StandardProcessingStatus {
  standard_id: string;
  processing_status: string;
  ocr_status: string | null;
  ai_status: string | null;
  error_message: string | null;
  clause_count: number;
  processing_started_at: string | null;
  processing_finished_at: string | null;
}

export interface StandardParseAssetSection {
  id: string;
  section_code: string | null;
  title: string;
  level: number;
  text: string | null;
  text_source: string | null;
  sort_order: number | null;
  page_start: number | null;
  page_end: number | null;
  raw_json: unknown;
}

export interface StandardParseAssetTable {
  id: string;
  section_id: string | null;
  page: number | null;
  page_start: number | null;
  page_end: number | null;
  table_title: string | null;
  table_html: string | null;
  raw_json: unknown;
}

export interface StandardParseAssets {
  standard_id: string;
  document: {
    id: string;
    parser_name: string | null;
    parser_version: string | null;
    raw_payload: unknown;
  } | null;
  sections: StandardParseAssetSection[];
  tables: StandardParseAssetTable[];
}

export interface StandardQualityGate {
  code: string;
  status: "pass" | "warn" | "fail";
  message: string;
  metric?: number;
  threshold?: number;
}

export interface StandardQualityIssue {
  code: string;
  severity: string;
  message: string;
  clause_no: string | null;
  page_start: number | null;
  page_end: number | null;
}

export interface StandardQualitySkillRecommendation {
  skill_name: string;
  description: string;
  tool_names: string[];
  active: boolean;
  reason: string;
  trigger_codes: string[];
}

export interface StandardQualityReport {
  overview: {
    status: "pass" | "review" | "fail";
    summary: string;
  };
  metrics: {
    page_count: number;
    raw_section_count: number;
    normalized_section_count: number;
    table_count: number;
    clause_count: number;
    commentary_clause_count: number;
    table_clause_count: number;
    anchored_section_count: number;
    anchored_clause_count: number;
    section_anchor_coverage: number;
    clause_anchor_coverage: number;
    backfilled_anchor_count: number;
    dropped_noise_count: number;
    validation_issue_count: number;
    validation_phrase_flag_count: number;
    validation_severity_counts: Record<string, number>;
    validation_issue_code_counts: Record<string, number>;
    toc_noise_count: number;
    front_matter_noise_count: number;
    suspicious_year_code_count: number;
    unanchored_heading_noise_count: number;
    terminal_heading_noise_count: number;
  };
  gates: StandardQualityGate[];
  warnings: string[];
  top_issues: StandardQualityIssue[];
  recommended_skills: StandardQualitySkillRecommendation[];
}

export interface StandardQualityReportResponse {
  standard_id: string;
  standard_code: string;
  standard_name: string;
  processing_status: string;
  ocr_status: string | null;
  ai_status: string | null;
  report: StandardQualityReport;
}

export interface BatchStandardUploadItem {
  file: File;
  standard_code: string;
  standard_name: string;
  version_year?: string;
  specialty?: string;
}

export type BatchStandardUploadResponse = Array<{
  id: string;
  standard_code: string;
  standard_name: string;
  document_id: string;
  processing_status: string;
  ocr_status: string | null;
  ai_status: string | null;
}>;

export function uploadStandards(
  items: BatchStandardUploadItem[],
): Promise<BatchStandardUploadResponse> {
  const form = new FormData();
  for (const item of items) {
    form.append("files", item.file);
  }
  form.append("items_json", JSON.stringify(items.map((item) => ({
    filename: item.file.name,
    standard_code: item.standard_code,
    standard_name: item.standard_name,
    version_year: item.version_year,
    specialty: item.specialty,
  }))));
  return request("/standards/upload", { method: "POST", body: form });
}

export function listStandards(options?: {
  signal?: AbortSignal;
}): Promise<Standard[]> {
  return request<Standard[]>("/standards", { signal: options?.signal });
}

export function fetchStandardDetail(
  standardId: string,
  options?: { signal?: AbortSignal },
): Promise<StandardDetail> {
  return request<StandardDetail>(`/standards/${standardId}`, {
    signal: options?.signal,
  });
}

export function fetchStandardClauses(
  standardId: string,
  clauseType?: string,
  options?: { signal?: AbortSignal },
): Promise<StandardClause[]> {
  const params = clauseType ? `?clause_type=${clauseType}` : "";
  return request<StandardClause[]>(
    `/standards/${standardId}/clauses${params}`,
    { signal: options?.signal },
  );
}

export function fetchStandardViewer(
  standardId: string,
  options?: { signal?: AbortSignal },
): Promise<StandardViewerData> {
  return request<StandardViewerData>(`/standards/${standardId}/viewer`, {
    signal: options?.signal,
  });
}

export function fetchStandardParseAssets(
  standardId: string,
  options?: { signal?: AbortSignal },
): Promise<StandardParseAssets> {
  return request<StandardParseAssets>(`/standards/${standardId}/parse-assets`, {
    signal: options?.signal,
  });
}

export function fetchStandardQualityReport(
  standardId: string,
  options?: { signal?: AbortSignal },
): Promise<StandardQualityReportResponse> {
  return request<StandardQualityReportResponse>(`/standards/${standardId}/quality-report`, {
    signal: options?.signal,
  });
}

export function triggerStandardProcessing(
  standardId: string,
): Promise<{ standard_id: string; processing_status: string; ocr_status: string | null; ai_status: string | null }> {
  return request(`/standards/${standardId}/process`, { method: "POST" });
}

export function triggerVisionProcessing(
  standardId: string,
): Promise<{ standard_id: string; status: string; pipeline: string; total_clauses: number }> {
  return request(`/standards/${standardId}/process-vision`, { method: "POST" });
}

export function searchStandardClauses(
  query: string,
  options?: { specialty?: string; topK?: number; signal?: AbortSignal },
): Promise<StandardSearchHit[]> {
  const params = new URLSearchParams({ q: query });
  if (options?.specialty) params.set("specialty", options.specialty);
  if (options?.topK != null) params.set("top_k", String(options.topK));
  return request<StandardSearchHit[]>(`/standards/search?${params.toString()}`, {
    signal: options?.signal,
  });
}

export function deleteStandard(
  standardId: string,
): Promise<{ standard_id: string; deleted: boolean }> {
  return request(`/standards/${standardId}`, { method: "DELETE" });
}

export function fetchStandardStatus(
  standardId: string,
  options?: { signal?: AbortSignal },
): Promise<StandardProcessingStatus> {
  return request<StandardProcessingStatus>(
    `/standards/${standardId}/status`,
    { signal: options?.signal },
  );
}

// ── Deviation Table ──

export interface DeviationItem {
  seq_number: number;
  procurement_clause_number: string;
  procurement_clause: string;
  response_clause: string;
  deviation_note: string;
}

export interface DeviationTableData {
  has_deviation: boolean;
  items: DeviationItem[];
}

export function fetchDeviationTable(
  chapterId: string,
  options?: { signal?: AbortSignal },
): Promise<DeviationTableData> {
  return request<DeviationTableData>(
    `/bid-outline/chapters/${chapterId}/deviation-table`,
    { signal: options?.signal },
  );
}

export function updateDeviationTable(
  chapterId: string,
  data: DeviationTableData,
): Promise<{ id: string; metadata_json: Record<string, unknown> }> {
  return request(`/bid-outline/chapters/${chapterId}/deviation-table`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}
