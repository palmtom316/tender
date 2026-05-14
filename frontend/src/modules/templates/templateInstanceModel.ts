export interface ProjectTemplateBlock {
  id: string;
  template_chapter_id?: string;
  project_id?: string;
  block_type: string;
  sort_order?: number;
  label: string;
  content_text?: string;
  prompt_text?: string;
  placeholder_key?: string | null;
  asset_type?: string | null;
  required?: boolean;
  render_options_json?: Record<string, unknown>;
  condition_json?: Record<string, unknown>;
  metadata_json?: Record<string, unknown>;
}

export interface ProjectTemplateChapter {
  id: string;
  chapter_code: string;
  chapter_title: string;
  sort_order: number;
  enabled: boolean;
  chapter_status?: string;
  tender_requirement_status?: string;
  lock_owner?: string | null;
  blocks: ProjectTemplateBlock[];
}

export interface TemplatePromotionProposal {
  id: string;
  proposal_status: "draft" | "submitted" | "approved" | "rejected" | string;
}

export interface ProjectTemplateInstance {
  id: string;
  project_id: string;
  display_name: string;
  status: string;
  chapters: ProjectTemplateChapter[];
  promotion_proposals?: TemplatePromotionProposal[];
  reconciliation_summary?: Record<string, unknown>;
  unanswered_requirement_count?: number;
  pending_seal_checklist_count?: number;
}

export function promotionProposalStatusLabel(status: string): string {
  const labels: Record<string, string> = { draft: "草稿", submitted: "已提交", approved: "已批准", rejected: "已拒绝" };
  return labels[status] ?? status;
}

export function groupBlocksByFormSection(blocks: ProjectTemplateBlock[]) {
  const sorted = [...blocks].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
  return {
    fixedText: sorted.filter((block) => block.block_type === "fixed_text"),
    aiPrompts: sorted.filter((block) => block.block_type === "ai_prompt"),
    tableDefinitions: sorted.filter((block) => block.block_type === "table_definition"),
    chartPrompts: sorted.filter((block) => block.block_type === "chart_prompt"),
    variables: sorted.filter((block) => block.block_type === "variable"),
    assetPlaceholders: sorted.filter((block) => block.block_type === "asset_placeholder"),
    pageBreaks: sorted.filter((block) => block.block_type === "page_break"),
    headerFooters: sorted.filter((block) => block.block_type === "header_footer"),
    pageFormats: sorted.filter((block) => block.block_type === "page_format" || block.block_type === "page_break" || block.block_type === "header_footer"),
    sealMarks: sorted.filter((block) => block.block_type === "seal_mark"),
    pricingAttachments: sorted.filter((block) => block.block_type === "pricing_block" || block.block_type === "excel_attachment"),
    requirementResponses: sorted.filter((block) => block.block_type === "requirement_response"),
    conditions: sorted.filter((block) => block.block_type === "condition"),
  };
}

export function chapterStatusLabel(chapter: Partial<ProjectTemplateChapter>): string {
  if (chapter.enabled === false) return "已停用";
  if (chapter.lock_owner) return `${chapter.lock_owner} 正在编辑`;
  if (chapter.chapter_status === "confirmed") return "已确认";
  if (chapter.tender_requirement_status === "changed_order") return "顺序差异";
  if (chapter.tender_requirement_status === "missing_from_tender") return "招标未要求";
  return "待调整";
}

export function reconciliationSeverityCounts(summary: any): { critical: number; medium: number; low: number } {
  const counts = summary?.counts_by_severity ?? summary ?? {};
  return { critical: Number(counts.critical ?? 0), medium: Number(counts.medium ?? 0), low: Number(counts.low ?? 0) };
}

export function templateInstanceCanConfirm(instance: Partial<ProjectTemplateInstance> & { reconciliation_summary?: any; unanswered_requirement_count?: number; pending_seal_checklist_count?: number }) {
  const counts = reconciliationSeverityCounts(instance.reconciliation_summary);
  if (counts.critical > 0) return { canConfirm: false, reason: `仍有 ${counts.critical} 个阻断级模板差异` };
  if ((instance.unanswered_requirement_count ?? 0) > 0) return { canConfirm: false, reason: `仍有 ${instance.unanswered_requirement_count} 条要求未响应` };
  if ((instance.pending_seal_checklist_count ?? 0) > 0) return { canConfirm: false, reason: `仍有 ${instance.pending_seal_checklist_count} 项签章未确认` };
  return { canConfirm: true, reason: "可确认" };
}
