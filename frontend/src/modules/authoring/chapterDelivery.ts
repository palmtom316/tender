import type { BidChapter, ChartAsset } from "../../lib/api";

export type ChapterDeliveryKind = "material_composition" | "ai_content";
export type MaterialSlotStatus = "ready" | "missing";
export type ChartTaskStatus = "not_generated" | "draft" | "needs_review" | "approved" | "failed" | "rejected" | string;

export interface MaterialSlotSummary {
  key: string;
  label: string;
  sourceLabel: string;
  status: MaterialSlotStatus;
  helpText: string;
  boundLabel?: string;
}

export interface ChartTaskCard {
  key: string;
  title: string;
  chartType: string;
  purpose: string;
  sourceSummary: string;
  placeholder: string;
  status: ChartTaskStatus;
  assetId: string | null;
  renderedSvg: string | null;
  isStaleByTemplate: boolean;
}

const CHART_LABELS: Record<string, string> = {
  org_chart: "项目组织机构图",
  responsibility_matrix: "岗位职责矩阵",
  construction_flow: "施工流程图",
  quality_system: "质量管理体系图",
  safety_system: "安全管理体系图",
  risk_matrix: "风险分级管控矩阵",
  emergency_org: "应急组织图",
  schedule_gantt: "施工进度横道图",
  response_matrix: "条款响应矩阵",
  indicator_table: "指标台账",
  interface_table: "协调接口表",
  equipment_table: "设备配置表",
  closure_flow: "闭环流程图",
  data_flow: "数据流转图",
  critical_path: "关键路径图",
};

const CHART_PURPOSES: Record<string, string> = {
  schedule_gantt: "响应工期及进度保证措施，展示关键节点和施工顺序。",
  critical_path: "说明影响工期的关键工作和前后依赖关系。",
  quality_system: "响应质量保证体系要求，展示质量管理职责链路。",
  safety_system: "响应安全管理要求，展示安全责任体系。",
  risk_matrix: "响应危险源辨识与风险控制要求。",
  construction_flow: "说明主要工序和施工组织逻辑。",
  org_chart: "展示项目管理组织和岗位分工。",
  equipment_table: "说明主要施工机械、车辆和工器具投入。",
  response_matrix: "逐项对应招标条款、评分点或技术规范要求。",
};

const CHART_SOURCES: Record<string, string> = {
  schedule_gantt: "招标工期、关键节点、施工工序模板。",
  critical_path: "工序依赖、里程碑、工期约束。",
  quality_system: "项目组织、质量岗位、检查闭环。",
  safety_system: "项目组织、安全岗位、危险源控制措施。",
  risk_matrix: "危险源清单、控制措施、责任岗位。",
  construction_flow: "施工方案、主要工序、项目类型。",
  org_chart: "项目人员选择和岗位职责。",
  equipment_table: "公司设备库和本项目设备选择。",
  response_matrix: "招标条款、评分点、章节正文。",
};

function chartPlaceholder(asset: Pick<ChartAsset, "placeholder_key" | "chart_type">) {
  return asset.placeholder_key || asset.chart_type;
}

function chartTitle(chartType: string) {
  return CHART_LABELS[chartType] ?? chartType;
}

function materialSourceLabel(materialType: unknown) {
  const value = typeof materialType === "string" ? materialType : "";
  if (value.includes("person")) return "人员资料库";
  if (value.includes("performance") || value.includes("业绩")) return "业绩库";
  if (value.includes("certificate") || value.includes("asset") || value.includes("证书")) return "证书/附件";
  return "公司资料库";
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function inferMaterialKey(label: string, fallback: string) {
  if (/安全生产许可证/.test(label)) return "safety_license";
  if (/营业执照|法人证书|登记证书/.test(label)) return "business_license";
  if (/资质证书/.test(label)) return "qualification_certificate";
  if (/项目经理/.test(label)) return "project_manager";
  if (/技术负责人/.test(label)) return "technical_lead";
  if (/安全员/.test(label)) return "safety_officer";
  if (/业绩证明附件/.test(label)) return "performance_attachment";
  if (/类似项目业绩/.test(label)) return "similar_performance";
  return fallback;
}

export function chapterDeliveryKind(chapter: BidChapter | null | undefined): ChapterDeliveryKind {
  return chapter?.volume_type === "technical" ? "ai_content" : "material_composition";
}

export function deliveryKindLabel(kind: ChapterDeliveryKind) {
  return kind === "ai_content" ? "AI 正文" : "资料编排";
}

export function readableContextCount(context: Record<string, unknown> | undefined, key: string) {
  const labels: Record<string, string> = {
    constraints: "约束",
    scoring_items: "评分",
    standard_clauses: "标准",
    personnel_selections: "人员",
    equipment_selections: "设备",
    chart_assets: "图表",
  };
  const value = context?.[key];
  const count = Array.isArray(value) ? value.length : 0;
  return `${labels[key] ?? key}：${count}`;
}

export function buildMaterialSlots(
  chapter: BidChapter | null | undefined,
  assembly: { missing_materials?: Array<Record<string, unknown>> } | undefined,
  boundMaterials?: Record<string, string>,
): MaterialSlotSummary[] {
  if (!chapter) return [];

  const missing = assembly?.missing_materials ?? [];
  const matchingMissing = missing.filter((item) => {
    const record = asRecord(item);
    return record.chapter_code === chapter.chapter_code || record.chapter_id === chapter.id;
  });

  if (matchingMissing.length > 0) {
    return matchingMissing.map((item, index) => {
      const record = asRecord(item);
      const label = String(record.material_name ?? record.name ?? record.title ?? `待补资料 ${index + 1}`);
      const fallbackKey = String(record.material_key ?? record.id ?? `${chapter.id}-${index}`);
      const key = inferMaterialKey(label, fallbackKey);
      return {
        key,
        label,
        sourceLabel: materialSourceLabel(record.material_type ?? record.source_type),
        status: boundMaterials?.[key] ? "ready" : "missing",
        helpText: String(record.reason ?? record.message ?? "选择或补充该资料后重新检查。"),
        boundLabel: boundMaterials?.[key],
      };
    });
  }

  const title = chapter.chapter_title;
  if (/人员|项目经理|团队/.test(title)) {
    return [
      { key: "project_manager", label: "项目经理", sourceLabel: "人员资料库", status: "ready", helpText: "从项目人员选择中带入。" },
      { key: "technical_lead", label: "技术负责人", sourceLabel: "人员资料库", status: "ready", helpText: "从项目人员选择中带入。" },
      { key: "safety_officer", label: "安全员", sourceLabel: "人员资料库", status: "ready", helpText: "从项目人员选择中带入。" },
    ];
  }

  if (/业绩|类似/.test(title)) {
    return [
      { key: "similar_performance", label: "类似项目业绩", sourceLabel: "业绩库", status: "ready", helpText: "从公司合同业绩台账带入。" },
      { key: "performance_attachment", label: "业绩证明附件", sourceLabel: "证书/附件", status: "ready", helpText: "从证明材料库带入。" },
    ];
  }

  return [
    { key: "business_license", label: "企业营业执照", sourceLabel: "公司资料库", status: "ready", helpText: "从公司基础资料带入。" },
    { key: "qualification_certificate", label: "资质证书", sourceLabel: "证书/附件", status: "ready", helpText: "从公司资质证书库带入。" },
    { key: "safety_license", label: "安全生产许可证", sourceLabel: "证书/附件", status: "ready", helpText: "从公司资质证书库带入。" },
  ];
}

export function buildChartTaskCards(recommendedChartKeys: string[], assets: ChartAsset[]): ChartTaskCard[] {
  const allKeys = Array.from(new Set([
    ...recommendedChartKeys,
    ...assets.map((asset) => chartPlaceholder(asset)).filter(Boolean),
  ]));

  return allKeys.map((key) => {
    const asset = assets.find((item) => chartPlaceholder(item) === key || item.chart_type === key);
    const chartType = asset?.chart_type ?? key;
    return {
      key,
      title: asset?.title ?? chartTitle(chartType),
      chartType,
      purpose: CHART_PURPOSES[chartType] ?? "辅助说明本章技术响应内容。",
      sourceSummary: CHART_SOURCES[chartType] ?? "章节正文、招标要求和已选资料。",
      placeholder: `{{chart:${key}}}`,
      status: asset?.status ?? "not_generated",
      assetId: asset?.id ?? null,
      renderedSvg: asset?.rendered_svg ?? null,
      isStaleByTemplate: Boolean(asset?.is_stale_by_template),
    };
  });
}
