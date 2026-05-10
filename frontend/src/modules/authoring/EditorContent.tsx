import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  approveChartAsset,
  assembleBusinessBid,
  confirmBidOutline,
  fetchBidOutline,
  fetchDrafts,
  fetchTechnicalChapterContext,
  fetchTechnicalWritingPlan,
  generateBidChapter,
  generateBidOutline,
  generateChartAsset,
  generateTechnicalChapter,
  listChartAssets,
  previewBidOutlineReconciliation,
  updateDraft,
} from "../../lib/api";
import { useNavigation } from "../../lib/NavigationContext";
import { ClayButton } from "../../components/ui/ClayButton";

const CHART_TYPE_OPTIONS = [
  { value: "org_chart", label: "项目组织机构图" },
  { value: "responsibility_matrix", label: "岗位职责矩阵" },
  { value: "construction_flow", label: "施工流程图" },
  { value: "quality_system", label: "质量管理体系图" },
  { value: "safety_system", label: "安全管理体系图" },
  { value: "risk_matrix", label: "风险分级管控矩阵" },
  { value: "emergency_org", label: "应急组织图" },
  { value: "schedule_gantt", label: "施工进度横道图" },
] as const;

function chartTitle(chartType: string) {
  return CHART_TYPE_OPTIONS.find((option) => option.value === chartType)?.label ?? "技术图表";
}

function chartPlaceholder(asset: { placeholder_key?: string | null; chart_type: string }) {
  return asset.placeholder_key || asset.chart_type;
}

function appendChartPlaceholder(content: string, key: string) {
  const placeholder = `{{chart:${key}}}`;
  if (content.includes(placeholder)) return content;
  return `${content}${content.trim().length > 0 ? "\n\n" : ""}${placeholder}`;
}

function contextCount(context: Record<string, unknown> | undefined, key: string) {
  const value = context?.[key];
  return Array.isArray(value) ? value.length : 0;
}

function companyAssetCount(context: Record<string, unknown> | undefined, key: string) {
  const assets = context?.company_assets;
  if (!assets || typeof assets !== "object") return 0;
  const value = (assets as Record<string, unknown>)[key];
  return Array.isArray(value) ? value.length : 0;
}

export function EditorContent() {
  const { projectId } = useNavigation();
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");
  const [chartType, setChartType] = useState<string>("quality_system");

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
  const selectedOutlineChapter = selected
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

  const save = useMutation({
    mutationFn: ({ id, content }: { id: string; content: string }) =>
      updateDraft(id, content),
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
    mutationFn: (chapterId: string) => {
      if (!projectId) throw new Error("No project selected");
      return generateTechnicalChapter(projectId, chapterId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["drafts", projectId] });
    },
  });

  const generateChart = useMutation({
    mutationFn: () => {
      if (!projectId) throw new Error("No project selected");
      return generateChartAsset(projectId, {
        chart_type: chartType,
        title: chartTitle(chartType),
        placeholder_key: chartType,
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
      <div className="empty-state">
        <span className="empty-state__icon">项</span>
        <p className="empty-state__title">先选择投标项目</p>
        <p className="empty-state__description">选择项目后，可编辑生成的章节草稿。</p>
      </div>
    );
  }

  const handleSelect = (draft: { id: string; content_md: string }) => {
    setSelectedId(draft.id);
    setEditContent(draft.content_md);
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
          disabled={outline?.status !== "confirmed" || businessAssembly.isPending}
        >
          {businessAssembly.isPending ? "装配中..." : "资格商务装配"}
        </ClayButton>
      </div>

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

      {chartAssets.length > 0 && (
        <section className="workflow-gate-panel">
          <div>
            <strong>图表资产</strong>
            <p>模板中使用占位符插入图表，正式导出只使用已审批图表。</p>
          </div>
          <div className="chart-asset-grid">
            {chartAssets.map((asset) => (
              <article key={asset.id} className="chart-asset-card">
                <div className="chart-asset-card__header">
                  <div>
                    <strong>{asset.title}</strong>
                    <span>{asset.chart_type}</span>
                  </div>
                  <span className={`status-pill status-pill--${asset.status}`}>{asset.status}</span>
                </div>
                {asset.rendered_svg && (
                  <div className="chart-asset-card__preview">
                    <img
                      src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(asset.rendered_svg)}`}
                      alt={asset.title}
                    />
                  </div>
                )}
                <div className="chart-asset-card__meta">
                  <code>{`{{chart:${asset.placeholder_key || asset.chart_type}}}`}</code>
                  <span>v{asset.version ?? 1}</span>
                </div>
                <ClayButton
                  size="sm"
                  variant="secondary"
                  onClick={() => approveChart.mutate(asset.id)}
                  disabled={asset.status === "approved" || approveChart.isPending}
                >
                  {asset.status === "approved" ? "已审批" : "审批图表"}
                </ClayButton>
                <ClayButton
                  size="sm"
                  variant="ghost"
                  onClick={() => setEditContent((current) => appendChartPlaceholder(current, chartPlaceholder(asset)))}
                  disabled={!selected}
                >
                  插入 {chartPlaceholder(asset)}
                </ClayButton>
              </article>
            ))}
          </div>
        </section>
      )}

      <section className="workflow-gate-panel" aria-label="图表生成与插入">
        <div>
          <strong>图表生成与插入</strong>
          <p>按技术章节选择图表类型，生成草案后用占位符插入正文，正式导出前审批引用图表。</p>
        </div>
        <div className="chart-control-row">
          <label>
            <span>图表类型</span>
            <select
              className="clay-input"
              value={chartType}
              onChange={(event) => setChartType(event.target.value)}
              aria-label="图表类型"
            >
              {CHART_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <ClayButton onClick={() => generateChart.mutate()} disabled={generateChart.isPending}>
            {generateChart.isPending ? "生成中..." : "生成图表草案"}
          </ClayButton>
        </div>
      </section>

      {selectedOutlineChapter?.volume_type === "technical" && (
        <section className="workflow-gate-panel" aria-label="章节生成上下文">
          <div>
            <strong>章节生成上下文</strong>
            <p>生成前核对约束、评分、标准、人员、设备、图表和企业资料输入。</p>
          </div>
          <div className="workflow-gate-panel__chips">
            <span>约束：{contextCount(chapterContext, "constraints")}</span>
            <span>评分：{contextCount(chapterContext, "scoring_items")}</span>
            <span>标准：{contextCount(chapterContext, "standard_clauses")}</span>
            <span>人员：{contextCount(chapterContext, "personnel_selections")}</span>
            <span>设备：{contextCount(chapterContext, "equipment_selections")}</span>
            <span>图表：{contextCount(chapterContext, "chart_assets")}</span>
            <span>业绩：{companyAssetCount(chapterContext, "performances")}</span>
            <span>证书：{companyAssetCount(chapterContext, "certificates")}</span>
          </div>
        </section>
      )}

      <div className="editor-layout">
        <aside className="outline-panel">
          <h2>提纲</h2>
          {outline?.chapters.map((chapter) => (
            <div key={chapter.id} className="outline-item">
              <span className="outline-code">{chapter.chapter_code}</span>
              <span>{chapter.chapter_title}</span>
              <ClayButton
                size="sm"
                onClick={() => {
                  if (chapter.volume_type === "technical" && outline?.status === "confirmed") {
                    generateTechnical.mutate(chapter.id);
                  } else {
                    generateChapter.mutate(chapter.id);
                  }
                }}
                disabled={generateChapter.isPending || generateTechnical.isPending}
              >
                {chapter.volume_type === "technical" && outline?.status === "confirmed" ? "技术生成" : "生成"}
              </ClayButton>
            </div>
          ))}
          {isLoading && (
            <div className="skeleton-stack" aria-label="章节草稿加载中">
              <div className="skeleton-line" />
              <div className="skeleton-line" />
              <div className="skeleton-line" />
            </div>
          )}
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
              {d.is_stale && <span className="status-pill status-pill--needs_review">stale</span>}
            </div>
          ))}
          {!isLoading && drafts.length === 0 && (
            <div className="empty-state">
              <span className="empty-state__icon">章</span>
              <p className="empty-state__title">暂无章节草稿</p>
              <p className="empty-state__description">完成解析和要求确认后，生成的章节草稿会出现在这里。</p>
            </div>
          )}
        </aside>

        <main className="editor-main">
          {selected ? (
            <>
              <div className="editor-toolbar">
                <h2>{selected.chapter_code}</h2>
                {selected.is_stale && <span className="status-pill status-pill--needs_review">{selected.stale_reason || "内容已过期"}</span>}
                <ClayButton
                  onClick={() => save.mutate({ id: selected.id, content: editContent })}
                  disabled={save.isPending}
                >
                  {save.isPending ? "保存中..." : "保存"}
                </ClayButton>
              </div>
              <textarea
                className="clay-textarea draft-editor"
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                aria-label={`${selected.chapter_code} 章节正文`}
              />
            </>
          ) : (
            <div className="empty-state">
              <span className="empty-state__icon">编</span>
              <p className="empty-state__title">选择章节开始编辑</p>
              <p className="empty-state__description">左侧选择章节后，可在这里调整正文并保存。</p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
