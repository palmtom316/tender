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

export function listProjects(): Promise<Project[]> {
  return request<Project[]>("/projects");
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

export function listFiles(projectId: string): Promise<ProjectFile[]> {
  return request<ProjectFile[]>(`/projects/${projectId}/files`);
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

export function fetchParseSummary(documentId: string): Promise<ParseSummary> {
  return request<ParseSummary>(`/documents/${documentId}/parse-result`);
}

export function fetchSections(documentId: string): Promise<Section[]> {
  return request<Section[]>(`/documents/${documentId}/sections`);
}

export function fetchTables(documentId: string): Promise<ParseTable[]> {
  return request<ParseTable[]>(`/documents/${documentId}/tables`);
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
): Promise<Requirement[]> {
  const params = category ? `?category=${category}` : "";
  return request<Requirement[]>(`/projects/${projectId}/requirements${params}`);
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

export function fetchDrafts(projectId: string): Promise<Draft[]> {
  return request<Draft[]>(`/projects/${projectId}/drafts`);
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

export function fetchReviewIssues(projectId: string): Promise<ReviewIssue[]> {
  return request<ReviewIssue[]>(`/projects/${projectId}/review-issues`);
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

export function fetchComplianceMatrix(projectId: string): Promise<ComplianceEntry[]> {
  return request<ComplianceEntry[]>(`/projects/${projectId}/compliance-matrix`);
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

export function fetchExportGates(projectId: string): Promise<ExportGates> {
  return request<ExportGates>(`/projects/${projectId}/export-gates`);
}

export function fetchExports(projectId: string): Promise<ExportRecord[]> {
  return request<ExportRecord[]>(`/projects/${projectId}/exports`);
}

// ── Table Override ──

export function submitTableOverride(
  tableId: string,
  overrideJson: object,
): Promise<unknown> {
  return request(`/tables/${tableId}/override`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ override_json: overrideJson }),
  });
}
