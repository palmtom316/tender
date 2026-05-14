export interface TemplateEditImpact {
  stale_drafts?: number;
  stale_charts?: number;
  stale_docx?: number;
  stale_draft_count?: number;
  stale_chart_count?: number;
  stale_export_artifact_count?: number;
}

export interface TemplateEditImpactResponse {
  revision_no?: number;
  impact?: TemplateEditImpact;
}

export function formatTemplateEditImpact(response: TemplateEditImpactResponse): string {
  if (!response.revision_no || !response.impact) {
    return "已保存模板块，预览已刷新";
  }
  const staleDrafts = response.impact.stale_draft_count ?? response.impact.stale_drafts ?? 0;
  const staleCharts = response.impact.stale_chart_count ?? response.impact.stale_charts ?? 0;
  const staleExports = response.impact.stale_export_artifact_count ?? response.impact.stale_docx ?? 0;
  return `已保存模板修订 ${response.revision_no}，受影响：正文草稿 ${staleDrafts}、图表 ${staleCharts}、导出产物 ${staleExports}`;
}
