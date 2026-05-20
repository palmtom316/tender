import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  approveChartAsset,
  assembleBusinessBid,
  confirmBidOutline,
  fetchBidOutline,
  fetchBusinessTemplatePreview,
  fetchDrafts,
  fetchProjectTemplateInstance,
  fetchTechnicalChapterContext,
  fetchTechnicalWritingPlan,
  generateBidChapter,
  generateBidOutline,
  generateChartAsset,
  generateTechnicalChapter,
  listChartAssets,
  previewBidOutlineReconciliation,
  updateBidChapter,
  updateDraft,
} from "../../lib/api";
import type { BidChapter } from "../../lib/api";
import { useNavigation } from "../../lib/NavigationContext";
import { ClayButton } from "../../components/ui/ClayButton";
import { Badge } from "../../components/ui/Badge";
import { EmptyState } from "../../components/ui/EmptyState";
import { LoadingState } from "../../components/ui/LoadingState";
import {
  buildChartTaskCards,
  buildMaterialSlots,
  chapterDeliveryKind,
  deliveryKindLabel,
  readableContextCount,
  type ChartTaskCard,
  type MaterialSlotSummary,
} from "./chapterDelivery";
import { buildBusinessMaterialCandidates, groupBusinessMaterialCandidates, type BusinessMaterialCandidate } from "./businessMaterialWorkbench";
import { matchPreviewChapter } from "./businessTemplatePreview";
import { AdHocChapterTaskCard } from "./AdHocChapterTaskCard";

const CHART_TYPE_OPTIONS = [
  { value: "org_chart", label: "项目组织机构图" },
  { value: "responsibility_matrix", label: "岗位职责矩阵" },
  { value: "construction_flow", label: "施工流程图" },
  { value: "quality_system", label: "质量管理体系图" },
  { value: "safety_system", label: "安全管理体系图" },
  { value: "risk_matrix", label: "风险分级管控矩阵" },
  { value: "emergency_org", label: "应急组织图" },
  { value: "schedule_gantt", label: "施工进度横道图" },
  { value: "response_matrix", label: "条款响应矩阵" },
  { value: "indicator_table", label: "指标台账" },
  { value: "interface_table", label: "协调接口表" },
  { value: "equipment_table", label: "设备配置表" },
  { value: "closure_flow", label: "闭环流程图" },
  { value: "data_flow", label: "数据流转图" },
  { value: "critical_path", label: "关键路径图" },
] as const;

const DEFAULT_TARGET_PAGES_BY_CHAPTER: Record<string, number> = {
  "8": 100,
  "9": 50,
  "10.1": 80,
  "10.2": 50,
  "10.3": 50,
};

function chartTitle(chartType: string) {
  return CHART_TYPE_OPTIONS.find((option) => option.value === chartType)?.label ?? "技术图表";
}

function appendChartPlaceholder(content: string, key: string) {
  const placeholder = `{{chart:${key}}}`;
  if (content.includes(placeholder)) return content;
  return `${content}${content.trim().length > 0 ? "\n\n" : ""}${placeholder}`;
}

function recommendedChartKeys(context: Record<string, unknown> | undefined) {
  const charts = context?.recommended_charts;
  if (!Array.isArray(charts)) return [];
  return charts.flatMap((chart) => {
    if (typeof chart === "string" && chart.trim()) return [chart];
    if (!chart || typeof chart !== "object") return [];
    const record = chart as Record<string, unknown>;
    const key = record.placeholder_key ?? record.chart_type ?? record.key;
    return typeof key === "string" && key.trim() ? [key] : [];
  });
}

function chartAssetStatusVariant(status: string): "default" | "success" | "warning" | "danger" | "info" {
  if (status === "approved") return "success";
  if (status === "failed" || status === "rejected") return "danger";
  if (status === "draft" || status === "needs_review" || status === "not_generated") return "warning";
  return "default";
}

function normalizeTargetPages(value: unknown) {
  const parsed = typeof value === "string" && value.trim() !== "" ? Number(value) : value;
  if (typeof parsed !== "number" || !Number.isFinite(parsed)) return null;
  return Math.min(300, Math.max(1, Math.round(parsed)));
}

function targetPagesFromContext(context: Record<string, unknown> | undefined) {
  const controls = context?.generation_controls;
  if (!controls || typeof controls !== "object") return null;
  return normalizeTargetPages((controls as Record<string, unknown>).target_pages);
}

function defaultTargetPagesForChapter(chapterCode: string) {
  return DEFAULT_TARGET_PAGES_BY_CHAPTER[chapterCode] ?? null;
}

function targetPagesInputValue(
  chapter: BidChapter | null | undefined,
  context: Record<string, unknown> | undefined,
  editedValues: Record<string, string>,
) {
  if (!chapter) return "";
  if (editedValues[chapter.id] !== undefined) return editedValues[chapter.id];
  const metadataPages = normalizeTargetPages(chapter.metadata_json?.target_pages);
  if (metadataPages !== null) return String(metadataPages);
  const contextPages = targetPagesFromContext(context);
  if (contextPages !== null) return String(contextPages);
  const defaultPages = defaultTargetPagesForChapter(chapter.chapter_code);
  return defaultPages === null ? "" : String(defaultPages);
}

function targetPagesForChapter(
  chapter: BidChapter,
  context: Record<string, unknown> | undefined,
  editedValues: Record<string, string>,
) {
  return normalizeTargetPages(targetPagesInputValue(chapter, context, editedValues));
}

const BUSINESS_PLACEHOLDER_PATTERN = /\{\{\s*([^}]+?)\s*\}\}/g;

function previewPlaceholderKey(rawKey: string) {
  return rawKey.replace(/^asset\./, "").trim();
}

function renderPreviewBlock(
  block: string,
  keyPrefix: string,
  boundMaterials: Record<string, string> | undefined,
) {
  const matches = Array.from(block.matchAll(BUSINESS_PLACEHOLDER_PATTERN));
  if (matches.length === 0) return <p key={keyPrefix}>{block}</p>;

  const fragments: JSX.Element[] = [];
  let lastIndex = 0;

  matches.forEach((match, index) => {
    const matchText = match[0];
    const rawKey = match[1] ?? "";
    const start = match.index ?? 0;
    const before = block.slice(lastIndex, start);
    if (before.trim()) {
      fragments.push(<span key={`${keyPrefix}-text-${index}`}>{before}</span>);
    }

    const placeholderKey = previewPlaceholderKey(rawKey);
    const boundLabel = boundMaterials?.[placeholderKey];
    fragments.push(
      <span key={`${keyPrefix}-placeholder-${index}`} className="preview-placeholder-chip">
        <span className="preview-placeholder-chip__label">待插资料位</span>
        <code>{rawKey.trim()}</code>
        {boundLabel ? <span className="preview-placeholder-chip__bound">已绑定资料：{boundLabel}</span> : null}
      </span>,
    );
    lastIndex = start + matchText.length;
  });

  const after = block.slice(lastIndex);
  if (after.trim()) {
    fragments.push(<span key={`${keyPrefix}-text-tail`}>{after}</span>);
  }

  return <p key={keyPrefix}>{fragments}</p>;
}

function MaterialSlotList({
  slots,
  selectedSlotKey,
  onSelectSlot,
  boundLabelPrefix = "已绑定资料",
}: {
  slots: MaterialSlotSummary[];
  selectedSlotKey: string | null;
  onSelectSlot?: (slot: MaterialSlotSummary) => void;
  boundLabelPrefix?: string;
}) {
  return (
    <section className="chapter-delivery-card" aria-label="资料位清单">
      <div className="chapter-delivery-card__header">
        <div>
          <strong>资料位清单</strong>
          <p>把公司、人员、业绩或附件绑定到固定资料位，避免自由插入导致格式失控。</p>
        </div>
        <Badge variant={slots.some((slot) => slot.status === "missing") ? "warning" : "success"}>
          {slots.filter((slot) => slot.status === "missing").length} 项待补
        </Badge>
      </div>
      <div className="material-slot-list">
        {slots.map((slot) => (
          <article key={slot.key} className="material-slot-item">
            <div>
              <strong>{slot.label}</strong>
              <p>{slot.helpText}</p>
              {slot.boundLabel && <p>{boundLabelPrefix}：{slot.boundLabel}</p>}
            </div>
            <div className="material-slot-item__meta">
              <Badge variant={slot.status === "missing" ? "warning" : "success"}>
                {slot.status === "missing" ? "待补资料" : "已匹配"}
              </Badge>
              <span>{slot.sourceLabel}</span>
              {onSelectSlot && (
                <ClayButton
                  size="sm"
                  variant={selectedSlotKey === slot.key ? "primary" : "secondary"}
                  onClick={() => onSelectSlot(slot)}
                >
                  {selectedSlotKey === slot.key ? `当前资料位 ${slot.label}` : `选择资料位 ${slot.label}`}
                </ClayButton>
              )}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function BusinessMaterialCandidatePanel({
  slot,
  groupedCandidates,
  onBind,
}: {
  slot: MaterialSlotSummary | null;
  groupedCandidates: Array<{ groupLabel: string; rows: BusinessMaterialCandidate[] }>;
  onBind: (candidate: BusinessMaterialCandidate) => void;
}) {
  return (
    <section className="chapter-delivery-card" aria-label="资料候选区">
      <div className="chapter-delivery-card__header">
        <div>
          <strong>资料候选区</strong>
          <p>按资料来源筛选候选资料，并绑定到当前资料位。</p>
        </div>
      </div>
      {slot ? <p>当前资料位：{slot.label}</p> : <p>先在左侧选择一个资料位。</p>}
      {slot && groupedCandidates.map((group) => (
        <div key={group.groupLabel} className="material-slot-list">
          <strong>{group.groupLabel}</strong>
          {group.rows.map((candidate) => (
            <article key={candidate.key} className="material-slot-item">
              <div>
                <strong>{candidate.label}</strong>
                <p>{candidate.summary}</p>
              </div>
              <div className="material-slot-item__meta">
                <span>{candidate.sourceLabel}</span>
                <ClayButton size="sm" variant="secondary" onClick={() => onBind(candidate)}>
                  绑定到当前资料位 {candidate.label}
                </ClayButton>
              </div>
            </article>
          ))}
        </div>
      ))}
    </section>
  );
}

function TechnicalWritingBrief({
  chapterCode,
  context,
  targetPagesValue,
  onTargetPagesChange,
  onSaveTargetPages,
  saveDisabled,
  saveLabel,
}: {
  chapterCode: string;
  context: Record<string, unknown> | undefined;
  targetPagesValue: string;
  onTargetPagesChange: (value: string) => void;
  onSaveTargetPages: () => void;
  saveDisabled: boolean;
  saveLabel: string;
}) {
  return (
    <section className="chapter-delivery-card" aria-label="章节写作要求">
      <div className="chapter-delivery-card__header">
        <div>
          <strong>章节写作要求</strong>
          <p>投标工程师优先调整业务要求；完整提示词保留在高级区。</p>
        </div>
      </div>
      <div className="workflow-gate-panel__chips">
        <span>{readableContextCount(context, "constraints")}</span>
        <span>{readableContextCount(context, "scoring_items")}</span>
        <span>{readableContextCount(context, "standard_clauses")}</span>
        <span>{readableContextCount(context, "personnel_selections")}</span>
        <span>{readableContextCount(context, "equipment_selections")}</span>
        <span>{readableContextCount(context, "chart_assets")}</span>
      </div>
      <div className="chapter-target-pages" aria-label="章节篇幅设置">
        <label>
          <span>目标页数</span>
          <input
            className="clay-input"
            type="number"
            min={1}
            max={300}
            step={1}
            value={targetPagesValue}
            onChange={(event) => onTargetPagesChange(event.target.value)}
            aria-label={`${chapterCode} 目标页数`}
          />
        </label>
        <ClayButton size="sm" variant="secondary" onClick={onSaveTargetPages} disabled={saveDisabled}>
          {saveLabel}
        </ClayButton>
        <span>生成时注入篇幅要求</span>
      </div>
    </section>
  );
}

function ChartTaskCards({
  tasks,
  generating,
  approving,
  onGenerate,
  onApprove,
  onInsert,
}: {
  tasks: ChartTaskCard[];
  generating: boolean;
  approving: boolean;
  onGenerate: (chartType: string) => void;
  onApprove: (assetId: string) => void;
  onInsert: (placeholderKey: string) => void;
}) {
  return (
    <section className="chapter-delivery-card" aria-label="图表任务">
      <div className="chapter-delivery-card__header">
        <div>
          <strong>图表任务</strong>
          <p>按“任务 → 数据/结构 → 预览 → 审批 → 插入”处理图表，不自由生成不可校核图片。</p>
        </div>
        <Badge variant="info">{tasks.length}</Badge>
      </div>
      <div className="chart-task-list">
        {tasks.map((task) => (
          <article key={task.key} className="chart-task-card">
            <div className="chart-task-card__header">
              <div>
                <strong>{task.title}</strong>
                <span>{task.chartType}</span>
              </div>
              <Badge variant={chartAssetStatusVariant(task.status)}>
                {task.status === "not_generated" ? "未生成" : task.status}
              </Badge>
            </div>
            {task.isStaleByTemplate && <Badge variant="danger">模板已更新，需重新生成图表</Badge>}
            <p>{task.purpose}</p>
            <p>来源：{task.sourceSummary}</p>
            <code>{task.placeholder}</code>
            {task.renderedSvg && (
              <div className="chart-asset-card__preview">
                <img src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(task.renderedSvg)}`} alt={task.title} />
              </div>
            )}
            <div className="chart-task-card__actions">
              <ClayButton size="sm" variant="secondary" onClick={() => onGenerate(task.chartType)} disabled={generating}>
                {task.isStaleByTemplate ? "按新模板重新生成图表" : task.assetId ? "重新生成" : "生成图表草案"}
              </ClayButton>
              <ClayButton
                size="sm"
                variant="secondary"
                onClick={() => task.assetId && onApprove(task.assetId)}
                disabled={!task.assetId || task.status === "approved" || approving}
              >
                {task.status === "approved" ? "已审批" : "审批图表"}
              </ClayButton>
              <ClayButton size="sm" variant="ghost" onClick={() => onInsert(task.key)} disabled={!task.assetId}>
                插入图表
              </ClayButton>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

export function EditorContent() {
  const { projectId } = useNavigation();
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");
  const [selectedChapterId, setSelectedChapterId] = useState<string | null>(null);
  const [targetPagesByChapter, setTargetPagesByChapter] = useState<Record<string, string>>({});
  const [selectedMaterialSlotKeyByChapter, setSelectedMaterialSlotKeyByChapter] = useState<Record<string, string>>({});
  const [boundMaterialByChapter, setBoundMaterialByChapter] = useState<Record<string, Record<string, string>>>({});

  const { data: drafts = [], isLoading } = useQuery({
    queryKey: ["drafts", projectId],
    queryFn: ({ signal }) => {
      if (!projectId) throw new Error("No project selected");
      return fetchDrafts(projectId, { signal });
    },
    enabled: !!projectId,
  });

  const { data: outline } = useQuery({
    queryKey: ["bid-outline", projectId],
    queryFn: ({ signal }) => {
      if (!projectId) throw new Error("No project selected");
      return fetchBidOutline(projectId, { signal });
    },
    enabled: !!projectId,
    retry: false,
  });

  const { data: reconciliation } = useQuery({
    queryKey: ["bid-outline-reconciliation", projectId],
    queryFn: ({ signal }) => {
      if (!projectId) throw new Error("No project selected");
      return previewBidOutlineReconciliation(projectId, { signal });
    },
    enabled: !!projectId && !!outline,
    retry: false,
  });

  const { data: technicalPlan } = useQuery({
    queryKey: ["technical-writing-plan", projectId],
    queryFn: ({ signal }) => {
      if (!projectId) throw new Error("No project selected");
      return fetchTechnicalWritingPlan(projectId, { signal });
    },
    enabled: !!projectId && outline?.status === "confirmed",
    retry: false,
  });

  const { data: chartAssets = [] } = useQuery({
    queryKey: ["chart-assets", projectId],
    queryFn: ({ signal }) => {
      if (!projectId) throw new Error("No project selected");
      return listChartAssets(projectId, { signal });
    },
    enabled: !!projectId,
  });

  const selected = drafts.find((d) => d.id === selectedId);
  const selectedOutlineChapter = selectedChapterId
    ? outline?.chapters.find((chapter) => chapter.id === selectedChapterId)
    : selected
      ? outline?.chapters.find((chapter) => chapter.chapter_code === selected.chapter_code)
      : null;

  const { data: chapterContext } = useQuery({
    queryKey: ["technical-chapter-context", projectId, selectedOutlineChapter?.id],
    queryFn: ({ signal }) => {
      if (!projectId || !selectedOutlineChapter?.id) throw new Error("No technical chapter selected");
      return fetchTechnicalChapterContext(projectId, selectedOutlineChapter.id, { signal });
    },
    enabled: !!projectId && !!selectedOutlineChapter?.id && selectedOutlineChapter.volume_type === "technical",
    retry: false,
  });

  const pendingChartCount = chartAssets.filter((asset) => asset.status !== "approved").length;
  const approvedChartCount = chartAssets.length - pendingChartCount;
  const recommendedCharts = recommendedChartKeys(chapterContext);
  const selectedTargetPagesValue = targetPagesInputValue(selectedOutlineChapter, chapterContext, targetPagesByChapter);
  const selectedTargetPages = normalizeTargetPages(selectedTargetPagesValue);
  const selectedDeliveryKind = chapterDeliveryKind(selectedOutlineChapter);
  const selectedDeliveryLabel = deliveryKindLabel(selectedDeliveryKind);
  const save = useMutation({
    mutationFn: ({ id, content }: { id: string; content: string }) => updateDraft(id, content),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["drafts", projectId] });
    },
  });

  const createOutline = useMutation({
    mutationFn: () => {
      if (!projectId) throw new Error("No project selected");
      return generateBidOutline(projectId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bid-outline", projectId] });
      queryClient.invalidateQueries({ queryKey: ["bid-outline-reconciliation", projectId] });
    },
  });

  const confirmOutline = useMutation({
    mutationFn: () => {
      if (!projectId) throw new Error("No project selected");
      return confirmBidOutline(projectId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bid-outline", projectId] });
      queryClient.invalidateQueries({ queryKey: ["bid-outline-reconciliation", projectId] });
      queryClient.invalidateQueries({ queryKey: ["technical-writing-plan", projectId] });
    },
  });

  const businessAssembly = useMutation({
    mutationFn: () => {
      if (!projectId) throw new Error("No project selected");
      return assembleBusinessBid(projectId);
    },
  });

  const { data: projectTemplateInstance } = useQuery({
    queryKey: ["project-template-instance", projectId],
    queryFn: ({ signal }) => {
      if (!projectId) throw new Error("No project selected");
      return fetchProjectTemplateInstance(projectId, { signal });
    },
    enabled: !!projectId,
    retry: false,
  });
  const templateBlockReason = projectTemplateInstance && projectTemplateInstance.status !== "ready_for_authoring" && projectTemplateInstance.status !== "locked_for_generation"
    ? "项目模板尚未确认，生成已阻断"
    : null;

  const { data: businessTemplatePreview } = useQuery({
    queryKey: ["business-template-preview", projectId],
    queryFn: ({ signal }) => {
      if (!projectId) throw new Error("No project selected");
      return fetchBusinessTemplatePreview(projectId, { signal });
    },
    enabled: !!projectId && !!businessAssembly.data,
    retry: false,
  });

  const selectedBoundMaterials = selectedOutlineChapter ? boundMaterialByChapter[selectedOutlineChapter.id] : undefined;
  const selectedMaterialSlotsReal = buildMaterialSlots(selectedOutlineChapter, businessAssembly.data, selectedBoundMaterials);
  const chartTaskCards = buildChartTaskCards(recommendedCharts, chartAssets);
  const isBusinessCompositionChapter = selectedOutlineChapter?.volume_type === "business" || selectedOutlineChapter?.volume_type === "qualification";
  const selectedMaterialSlotKey = selectedOutlineChapter ? selectedMaterialSlotKeyByChapter[selectedOutlineChapter.id] ?? null : null;
  const selectedMaterialSlot =
    selectedMaterialSlotsReal.find((slot) => slot.key === selectedMaterialSlotKey) ?? null;
  const groupedMaterialCandidates = groupBusinessMaterialCandidates(
    buildBusinessMaterialCandidates(selectedMaterialSlot, selectedOutlineChapter?.chapter_title ?? ""),
  );
  const matchedPreviewChapter = matchPreviewChapter(businessTemplatePreview, selectedOutlineChapter);
  const previewBoundMaterials = selectedBoundMaterials ?? {};

  const generateChapter = useMutation({
    mutationFn: (chapterId: string) => {
      if (!projectId) throw new Error("No project selected");
      return generateBidChapter(projectId, chapterId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["drafts", projectId] });
    },
  });

  const generateTechnical = useMutation({
    mutationFn: ({ chapterId, targetPages }: { chapterId: string; targetPages?: number | null }) => {
      if (!projectId) throw new Error("No project selected");
      return generateTechnicalChapter(projectId, chapterId, targetPages ? { target_pages: targetPages } : undefined);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["drafts", projectId] });
    },
  });

  const updateTargetPages = useMutation({
    mutationFn: ({ chapter, targetPages }: { chapter: BidChapter; targetPages: number }) =>
      updateBidChapter(chapter.id, {
        metadata_json: {
          ...(chapter.metadata_json ?? {}),
          target_pages: targetPages,
        },
      }),
    onSuccess: (_updatedChapter, variables) => {
      setTargetPagesByChapter((current) => ({
        ...current,
        [variables.chapter.id]: String(variables.targetPages),
      }));
      queryClient.invalidateQueries({ queryKey: ["bid-outline", projectId] });
      queryClient.invalidateQueries({ queryKey: ["technical-chapter-context", projectId, variables.chapter.id] });
    },
  });

  const generateChart = useMutation({
    mutationFn: (nextChartType: string) => {
      if (!projectId) throw new Error("No project selected");
      return generateChartAsset(projectId, {
        chart_type: nextChartType,
        title: chartTitle(nextChartType),
        placeholder_key: nextChartType,
        outline_node_id: selectedOutlineChapter?.id ?? null,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chart-assets", projectId] });
    },
  });

  const approveChart = useMutation({
    mutationFn: (assetId: string) => approveChartAsset(assetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chart-assets", projectId] });
    },
  });

  if (!projectId) {
    return (
      <EmptyState
        icon="项"
        title="先选择投标项目"
        description="选择项目后，可编辑生成的章节草稿。"
      />
    );
  }

  const handleSelect = (draft: { id: string; chapter_code: string; content_md: string }) => {
    setSelectedId(draft.id);
    setEditContent(draft.content_md);
    const chapter = outline?.chapters.find((item) => item.chapter_code === draft.chapter_code);
    setSelectedChapterId(chapter?.id ?? null);
  };

  const handleSelectChapter = (chapter: BidChapter) => {
    setSelectedChapterId(chapter.id);
    const draft = drafts.find((item) => item.chapter_code === chapter.chapter_code);
    if (draft) {
      setSelectedId(draft.id);
      setEditContent(draft.content_md);
    } else {
      setSelectedId(null);
      setEditContent("");
    }
  };

  return (
    <div>
      <h1 className="section-heading">章节编辑</h1>
      <div className="toolbar-row">
        <ClayButton onClick={() => createOutline.mutate()} disabled={createOutline.isPending}>
          {outline ? "检查模板冲突" : "按模板生成目录映射"}
        </ClayButton>
        <ClayButton
          variant="secondary"
          onClick={() => confirmOutline.mutate()}
          disabled={!outline || outline.status === "confirmed" || !reconciliation?.can_confirm || confirmOutline.isPending}
        >
          {outline?.status === "confirmed" ? "目录映射已确认" : "确认目录映射"}
        </ClayButton>
        <ClayButton
          variant="secondary"
          onClick={() => businessAssembly.mutate()}
          disabled={!!templateBlockReason || outline?.status !== "confirmed" || businessAssembly.isPending}
        >
          {businessAssembly.isPending ? "装配中..." : "资格商务装配"}
        </ClayButton>
      </div>

      {projectTemplateInstance && (
        <section className="workflow-gate-panel" aria-label="项目模板实例状态">
          <div>
            <strong>项目模板实例</strong>
            <p>{templateBlockReason ?? "已确认，可用于标书生成。"}</p>
          </div>
          <div className="workflow-gate-panel__chips">
            <span>状态：{projectTemplateInstance.status}</span>
            <span>未响应：{projectTemplateInstance.unanswered_requirement_count ?? 0}</span>
            <span>签章待确认：{projectTemplateInstance.pending_seal_checklist_count ?? 0}</span>
          </div>
        </section>
      )}

      {reconciliation && (
        <section className="workflow-gate-panel">
          <div>
            <strong>目录模板映射确认</strong>
            <p>
              {reconciliation.can_confirm
                ? `可确认，${reconciliation.diffs.length} 项模板映射/冲突检查结果已汇总。`
                : `${reconciliation.unresolved_critical_count} 项关键条款未确认，暂不能进入商务/技术生成。`}
            </p>
          </div>
          <div className="workflow-gate-panel__chips">
            <span>目录状态：{outline?.status ?? "未生成"}</span>
            <span>图表：{chartAssets.length} 个</span>
            <span>技术章节：{technicalPlan?.chapter_count ?? 0} 个</span>
          </div>
        </section>
      )}

      {reconciliation?.diffs.some((diff) => diff.operation === "tender_conflict_override") && (
        <section className="workflow-gate-panel" aria-label="招标冲突确认记录">
          <div>
            <strong>招标冲突覆盖</strong>
            <p>仅已确认且有招标文件依据的目录冲突会覆盖用户目录模板。</p>
          </div>
          <div className="template-conflict-list">
            {reconciliation.diffs
              .filter((diff) => diff.operation === "tender_conflict_override")
              .map((diff) => (
                <article key={`${diff.chapter_id}-${diff.operation}`} className="template-conflict-item">
                  <strong>{diff.chapter_code} {diff.chapter_title}</strong>
                  <span>{diff.source_locator || "未记录来源位置"}</span>
                  <p>{diff.reason}</p>
                  {diff.proposed_action && <code>{diff.proposed_action}</code>}
                </article>
              ))}
          </div>
        </section>
      )}

      {businessAssembly.data && (
        <section className="workflow-gate-panel">
          <div>
            <strong>资格商务装配结果</strong>
            <p>{businessAssembly.data.boundary}</p>
          </div>
          <div className="workflow-gate-panel__chips">
            <span>章节：{businessAssembly.data.chapters.length}</span>
            <span>缺失资料：{businessAssembly.data.missing_materials.length}</span>
            <span>响应矩阵：{businessAssembly.data.response_matrix.length}</span>
          </div>
        </section>
      )}

      <div className="editor-layout">
        <aside className="outline-panel">
          <h2>提纲</h2>
          {outline?.chapters.map((chapter) => {
            const kind = chapterDeliveryKind(chapter);
            const isBusinessPreviewChapter = kind === "material_composition" && Boolean(
              businessTemplatePreview?.chapters.some((item) => item.chapter_code === chapter.chapter_code),
            );
            return (
              <div
                key={chapter.id}
                className="outline-item"
                onClick={() => handleSelectChapter(chapter)}
              >
                <span className="outline-code">{chapter.chapter_code}</span>
                <span>{chapter.chapter_title}</span>
                <Badge variant={kind === "ai_content" ? "info" : "success"}>{deliveryKindLabel(kind)}</Badge>
                <ClayButton
                  size="sm"
                  variant={isBusinessPreviewChapter ? "secondary" : "primary"}
                  onClick={(event) => {
                    event.stopPropagation();
                    if (isBusinessPreviewChapter) {
                      handleSelectChapter(chapter);
                      return;
                    }
                    if (kind === "ad_hoc_task_card") {
                      handleSelectChapter(chapter);
                      return;
                    }
                    if (chapter.volume_type === "technical" && outline?.status === "confirmed") {
                      const context = chapter.id === selectedOutlineChapter?.id ? chapterContext : undefined;
                      generateTechnical.mutate({
                        chapterId: chapter.id,
                        targetPages: targetPagesForChapter(chapter, context, targetPagesByChapter),
                      });
                    } else {
                      generateChapter.mutate(chapter.id);
                    }
                  }}
                  disabled={!isBusinessPreviewChapter && (generateChapter.isPending || generateTechnical.isPending)}
                >
                  {isBusinessPreviewChapter
                    ? `查看章节 ${chapter.chapter_code} ${chapter.chapter_title}`
                    : kind === "ad_hoc_task_card"
                      ? "打开任务卡"
                    : chapter.volume_type === "technical" && outline?.status === "confirmed"
                      ? "技术生成"
                      : "生成"}
                </ClayButton>
              </div>
            );
          })}
          {isLoading && <LoadingState label="章节草稿加载中" rows={3} compact />}
          {drafts.map((d) => (
            <div
              key={d.id}
              className={`outline-item ${d.id === selectedId ? "active" : ""}`}
              onClick={() => handleSelect(d)}
            >
              <span className="outline-code">{d.chapter_code}</span>
              <span className="outline-date">
                {new Date(d.updated_at).toLocaleDateString("zh-CN")}
              </span>
              {d.is_stale_by_template ? <Badge variant="danger">模板 stale</Badge> : d.is_stale && <Badge variant="danger">stale</Badge>}
            </div>
          ))}
          {!isLoading && drafts.length === 0 && (
            <EmptyState
              icon="章"
              title="暂无章节草稿"
              description="完成解析和要求确认后，生成的章节草稿会出现在这里。"
            />
          )}
        </aside>

        <main className="editor-main">
          {selected ? (
            <>
              <div className="editor-toolbar chapter-delivery-toolbar">
                <div>
                  <h2>{selected.chapter_code} {selectedOutlineChapter?.chapter_title ?? "章节草稿"}</h2>
                  <div className="chapter-delivery-toolbar__meta">
                    <Badge variant={selectedDeliveryKind === "ai_content" ? "info" : "success"}>{selectedDeliveryLabel}</Badge>
                    {selected.is_stale_by_template && <Badge variant="danger">模板已更新，需重新生成正文</Badge>}
                    {selected.is_stale && <Badge variant="danger">{selected.stale_reason || "内容已过期"}</Badge>}
                  </div>
                </div>
                <ClayButton
                  onClick={() => save.mutate({ id: selected.id, content: editContent })}
                  disabled={save.isPending}
                >
                  {save.isPending ? "保存中..." : "保存正文"}
                </ClayButton>
                {selected.is_stale_by_template && selectedOutlineChapter && (
                  <ClayButton
                    variant="secondary"
                    onClick={() => generateTechnical.mutate({ chapterId: selectedOutlineChapter.id, targetPages: selectedTargetPages })}
                    disabled={generateTechnical.isPending || Boolean(templateBlockReason)}
                  >
                    按新模板重新生成正文
                  </ClayButton>
                )}
              </div>

              <div className="chapter-delivery-controls">
                {selectedDeliveryKind === "material_composition" && (
                  <>
                    <MaterialSlotList
                      slots={selectedMaterialSlotsReal}
                      selectedSlotKey={selectedMaterialSlotKey}
                      boundLabelPrefix={matchedPreviewChapter ? "资料位已选" : "已绑定资料"}
                      onSelectSlot={isBusinessCompositionChapter ? (slot) => {
                        if (!selectedOutlineChapter) return;
                        setSelectedMaterialSlotKeyByChapter((current) => ({
                          ...current,
                          [selectedOutlineChapter.id]: slot.key,
                        }));
                      } : undefined}
                    />
                    {isBusinessCompositionChapter && (
                      <BusinessMaterialCandidatePanel
                        slot={selectedMaterialSlot}
                        groupedCandidates={groupedMaterialCandidates}
                        onBind={(candidate) => {
                          if (!selectedOutlineChapter || !selectedMaterialSlot) return;
                          setBoundMaterialByChapter((current) => ({
                            ...current,
                            [selectedOutlineChapter.id]: {
                              ...(current[selectedOutlineChapter.id] ?? {}),
                              [selectedMaterialSlot.key]: candidate.label,
                            },
                          }));
                        }}
                      />
                    )}
                  </>
                )}
                {selectedDeliveryKind === "ai_content" && selectedOutlineChapter && (
                  <>
                    <TechnicalWritingBrief
                      chapterCode={selectedOutlineChapter.chapter_code}
                      context={chapterContext}
                      targetPagesValue={selectedTargetPagesValue}
                      onTargetPagesChange={(value) => {
                        setTargetPagesByChapter((current) => ({
                          ...current,
                          [selectedOutlineChapter.id]: value,
                        }));
                      }}
                      onSaveTargetPages={() => {
                        if (!selectedOutlineChapter || selectedTargetPages === null) return;
                        updateTargetPages.mutate({ chapter: selectedOutlineChapter, targetPages: selectedTargetPages });
                      }}
                      saveDisabled={!selectedOutlineChapter || selectedTargetPages === null || updateTargetPages.isPending}
                      saveLabel={updateTargetPages.isPending ? "保存中..." : "保存篇幅"}
                    />
                    <ChartTaskCards
                      tasks={chartTaskCards}
                      generating={generateChart.isPending}
                      approving={approveChart.isPending}
                      onGenerate={(nextChartType) => generateChart.mutate(nextChartType)}
                      onApprove={(assetId) => approveChart.mutate(assetId)}
                      onInsert={(key) => setEditContent((current) => appendChartPlaceholder(current, key))}
                    />
                  </>
                )}
                {selectedDeliveryKind === "ad_hoc_task_card" && selectedOutlineChapter && projectId && (
                  <AdHocChapterTaskCard
                    projectId={projectId}
                    chapter={selectedOutlineChapter}
                    onGenerateDraft={() => generateChapter.mutate(selectedOutlineChapter.id)}
                    generatingDraft={generateChapter.isPending}
                  />
                )}
              </div>

              {selectedDeliveryKind === "material_composition" && matchedPreviewChapter ? (
                <section className="chapter-delivery-card" aria-label="模板页面预览">
                  <div className="chapter-delivery-card__header">
                    <div>
                      <strong>模板页面预览</strong>
                      <p>按模板分页展示固定正文，当前版本只读，不直接编辑版式。</p>
                    </div>
                    <Badge variant="info">{matchedPreviewChapter.pages.length} 页</Badge>
                  </div>
                  <div className="preview-page-grid">
                    {matchedPreviewChapter.pages.map((page) => (
                      <article key={page.page_number} className="preview-page-card">
                        <div className="preview-page-card__header">
                          <strong>{`第 ${page.page_number} 页`}</strong>
                        </div>
                        <div className="preview-page-card__body">
                          {page.blocks.map((block, index) => renderPreviewBlock(
                            block,
                            `${page.page_number}-${index}`,
                            previewBoundMaterials,
                          ))}
                        </div>
                      </article>
                    ))}
                  </div>
                </section>
              ) : (
                <section className="chapter-delivery-card" aria-label="章节预览">
                  <div className="chapter-delivery-card__header">
                    <div>
                      <strong>
                        {selectedDeliveryKind === "ai_content"
                          ? "AI 生成正文"
                          : selectedDeliveryKind === "ad_hoc_task_card"
                            ? "新增章节正文"
                            : "模板生成预览"}
                      </strong>
                      <p>
                        {selectedDeliveryKind === "ai_content" || selectedDeliveryKind === "ad_hoc_task_card"
                          ? "审阅生成内容，可直接修改后保存。"
                          : "固定文字和资料位最终会装配到该章节。"}
                      </p>
                    </div>
                  </div>
                  <textarea
                    className="clay-textarea draft-editor"
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    aria-label={`${selected.chapter_code} 章节正文`}
                  />
                </section>
              )}
            </>
          ) : selectedDeliveryKind === "ad_hoc_task_card" && selectedOutlineChapter && projectId ? (
            <AdHocChapterTaskCard
              projectId={projectId}
              chapter={selectedOutlineChapter}
              onGenerateDraft={() => generateChapter.mutate(selectedOutlineChapter.id)}
              generatingDraft={generateChapter.isPending}
            />
          ) : (
            <EmptyState
              icon="编"
              title="选择章节开始编辑"
              description="左侧选择章节后，可在这里调整正文并保存。"
            />
          )}
        </main>
      </div>
    </div>
  );
}
