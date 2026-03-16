/**
 * API client for the tender backend.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BASE_URL}/api${path}`;
  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string>),
  };
  // Attach auth token if available
  const token = localStorage.getItem("tender_token") ?? "dev-token";
  headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(url, { ...init, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// --- Projects ---

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

// --- Files ---

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
