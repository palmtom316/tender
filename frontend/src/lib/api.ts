/**
 * API client for the tender backend.
 * All fetch calls are centralized here.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

function getToken(): string {
  return localStorage.getItem("tender_token") ?? "dev-token";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BASE_URL}/api${path}`;
  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string>),
  };
  headers["Authorization"] = `Bearer ${getToken()}`;

  const res = await fetch(url, { ...init, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Projects ──

export interface Project {
  id: string;
  name: string;
  status?: string;
  tender_deadline?: string;
  priority?: string;
  created_at: string;
}

export function listProjects(options?: {
  signal?: AbortSignal;
}): Promise<Project[]> {
  return request<Project[]>("/projects", { signal: options?.signal });
}

export function createProject(data: {
  name: string;
  tender_no?: string;
  project_type?: string;
  tender_deadline?: string;
  priority?: string;
}): Promise<Project> {
  return request<Project>("/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
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

// ── Requirements ──

export interface Requirement {
  id: string;
  category: string;
  title: string;
  source_text: string | null;
  human_confirmed: boolean;
  confirmed_by: string | null;
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

export function confirmRequirement(id: string): Promise<Requirement> {
  return request<Requirement>(`/requirements/${id}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmed: true }),
  });
}

// ── Drafts ──

export interface Draft {
  id: string;
  chapter_code: string;
  content_md: string;
  updated_at: string;
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

// ── Review Issues ──

export interface ReviewIssue {
  id: string;
  severity: string;
  title: string;
  detail: string | null;
  resolved: boolean;
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
    format_passed: boolean;
  };
  can_export: boolean;
}

export interface ExportRecord {
  id: string;
  status: string;
  template_name: string | null;
  export_key: string | null;
  created_at: string;
}

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
  const url = `${BASE_URL}/api/auth/login`;
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
  clause_title: string | null;
  clause_text: string | null;
  summary: string | null;
  tags: string[];
  clause_type: string;
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

export function triggerStandardProcessing(
  standardId: string,
): Promise<{ standard_id: string; processing_status: string; ocr_status: string | null; ai_status: string | null }> {
  return request(`/standards/${standardId}/process`, { method: "POST" });
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
