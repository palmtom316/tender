export type AuthoringTab = "upload" | "parse" | "requirements" | "template" | "editor";
export type WorkflowStepState = "done" | "active" | "blocked" | "pending";
export type TemplateStatus = "missing" | "draft" | "needs_reconciliation" | "ready_for_authoring" | "locked_for_generation" | "confirmed";

export interface AuthoringWorkflowStatusInput {
  hasDocument?: boolean;
  parseStatus?: "idle" | "running" | "done" | "failed";
  requirementsConfirmed?: boolean;
  templateStatus?: TemplateStatus | string | null;
  unresolvedCriticalIssues?: number;
  unansweredRequirementCount?: number;
  pendingSealChecklistCount?: number;
  reviewReady?: boolean;
}

export interface AuthoringStep {
  id: AuthoringTab | "review";
  label: string;
  state: WorkflowStepState;
  tab?: AuthoringTab;
}

export interface ProjectNextAction {
  tab: AuthoringTab;
  label: string;
}

function templateReady(status: AuthoringWorkflowStatusInput): boolean {
  return status.templateStatus === "ready_for_authoring" || status.templateStatus === "locked_for_generation" || status.templateStatus === "confirmed";
}

export function editorBlockReason(status: AuthoringWorkflowStatusInput): string | null {
  if (!templateReady(status)) {
    if ((status.unresolvedCriticalIssues ?? 0) > 0) return `${status.unresolvedCriticalIssues} 个模板阻断问题未处理`;
    if ((status.unansweredRequirementCount ?? 0) > 0) return `${status.unansweredRequirementCount} 条招标要求未响应`;
    if ((status.pendingSealChecklistCount ?? 0) > 0) return `${status.pendingSealChecklistCount} 项签章清单未确认`;
    if (!status.templateStatus || status.templateStatus === "missing") return "项目模板实例未生成";
    return "项目模板尚未确认";
  }
  return null;
}

export function nextAuthoringTab(status: AuthoringWorkflowStatusInput): AuthoringTab {
  if (!status.hasDocument) return "upload";
  if (status.parseStatus !== "done") return "parse";
  if (!status.requirementsConfirmed) return "requirements";
  if (editorBlockReason(status)) return "template";
  return "editor";
}

export function projectNextAction(status: AuthoringWorkflowStatusInput): ProjectNextAction {
  const tab = nextAuthoringTab(status);
  const labels: Record<AuthoringTab, string> = {
    upload: "上传招标文件",
    parse: "解析招标要求",
    requirements: "确认要求",
    template: "调整模板",
    editor: "编写标书",
  };
  return { tab, label: labels[tab] };
}

export function authoringSteps(status: AuthoringWorkflowStatusInput, activeTab?: string): AuthoringStep[] {
  const parseDone = status.parseStatus === "done";
  const requirementsDone = Boolean(status.requirementsConfirmed);
  const templateBlock = editorBlockReason(status);
  const isTemplateReady = templateReady(status);
  const steps: AuthoringStep[] = [
    { id: "upload", label: "项目建立", tab: "upload", state: status.hasDocument ? "done" : activeTab === "upload" ? "active" : "pending" },
    { id: "parse", label: "文件解析", tab: "parse", state: parseDone ? "done" : activeTab === "parse" ? "active" : status.hasDocument ? "pending" : "blocked" },
    { id: "requirements", label: "要求确认", tab: "requirements", state: requirementsDone ? "done" : activeTab === "requirements" ? "active" : parseDone ? "pending" : "blocked" },
    { id: "template", label: "模板调整", tab: "template", state: isTemplateReady ? "done" : activeTab === "template" ? "active" : requirementsDone ? (templateBlock ? "blocked" : "pending") : "blocked" },
    { id: "editor", label: "标书编写", tab: "editor", state: activeTab === "editor" ? (templateBlock ? "blocked" : "active") : isTemplateReady ? "pending" : "blocked" },
    { id: "review", label: "审查/导出", state: status.reviewReady ? "done" : isTemplateReady ? "pending" : "blocked" },
  ];
  return steps;
}

export function projectStatusFromProject(project: {
  workflow_status?: string | null;
  status?: string | null;
  selected_template_package_id?: string | null;
  template_status?: string | null;
  project_template_status?: string | null;
  has_document?: boolean;
  parse_status?: string | null;
  requirements_confirmed?: boolean;
  unresolved_template_issue_count?: number;
  unanswered_requirement_count?: number;
  pending_seal_checklist_count?: number;
}): AuthoringWorkflowStatusInput {
  const workflow = project.workflow_status ?? project.status ?? "created";
  return {
    hasDocument: project.has_document ?? !["created"].includes(workflow),
    parseStatus: (project.parse_status as AuthoringWorkflowStatusInput["parseStatus"]) ?? (workflow === "created" ? "idle" : workflow === "source_uploaded" ? "running" : "done"),
    requirementsConfirmed: project.requirements_confirmed ?? !["created", "source_uploaded", "analysis_running", "constraints_pending_confirmation"].includes(workflow),
    templateStatus: project.template_status ?? project.project_template_status ?? (project.selected_template_package_id ? "draft" : "missing"),
    unresolvedCriticalIssues: project.unresolved_template_issue_count ?? 0,
    unansweredRequirementCount: project.unanswered_requirement_count ?? 0,
    pendingSealChecklistCount: project.pending_seal_checklist_count ?? 0,
  };
}
