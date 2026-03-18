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
