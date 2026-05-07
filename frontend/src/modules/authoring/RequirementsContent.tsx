import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  bulkConfirmRequirements,
  fetchRequirementWorkbench,
  fetchTenderSummary,
  startTenderAiExtractionRun,
  type RequirementPackage,
  type RequirementWorkbenchLane,
} from "../../lib/api";
import { useNavigation } from "../../lib/NavigationContext";
import { ClayButton } from "../../components/ui/ClayButton";
import { Badge } from "../../components/ui/Badge";
import { AiExtractionRunPanel } from "./AiExtractionRunPanel";
import { SourceChunkViewer } from "./SourceChunkViewer";

const LEVEL_LABELS: Record<RequirementPackage["confirmation_level"], string> = {
  critical: "关键确认",
  review: "抽查复核",
  auto_accept: "自动采纳",
  ignored: "仅归档",
};

const LEVEL_BADGES: Record<RequirementPackage["confirmation_level"], "danger" | "warning" | "success" | "default"> = {
  critical: "danger",
  review: "warning",
  auto_accept: "success",
  ignored: "default",
};

const FIELD_LABELS: Record<string, string> = {
  date: "日期/时间",
  amount: "金额/比例",
  copy_count: "份数",
  certificate_grade: "证书等级",
  social_security_months: "社保月数",
  file_size: "文件大小",
};

function getLatestRunStorageKey(documentId: string) {
  return `tender:ai-extraction-run:${documentId}`;
}

function readStoredLatestRunId(documentId: string | null) {
  if (!documentId || typeof window === "undefined") return null;
  return window.localStorage.getItem(getLatestRunStorageKey(documentId));
}

function formatPercent(value: number | null) {
  if (value == null) return "置信度待评估";
  return `${Math.round(value * 100)}%`;
}

function fileName(path: string | null) {
  if (!path) return "未知来源";
  return path.split("/").pop() ?? path;
}

function visibleLanes(lanes: RequirementWorkbenchLane[], activeLane: string) {
  if (activeLane === "all") return lanes.filter((lane) => lane.packages.length > 0);
  return lanes.filter((lane) => lane.id === activeLane);
}

export function RequirementsContent() {
  const { projectId, documentId } = useNavigation();
  const queryClient = useQueryClient();
  const [activeLane, setActiveLane] = useState("all");
  const [sourceChunkId, setSourceChunkId] = useState<string | null>(null);
  const [selectedPackage, setSelectedPackage] = useState<RequirementPackage | null>(null);
  const [latestRunId, setLatestRunId] = useState<string | null>(null);

  useEffect(() => {
    setLatestRunId(readStoredLatestRunId(documentId));
  }, [documentId]);

  const { data: workbench, isLoading } = useQuery({
    queryKey: ["requirement-workbench", projectId],
    queryFn: ({ signal }) => {
      if (!projectId) throw new Error("No project selected");
      return fetchRequirementWorkbench(projectId, { signal });
    },
    enabled: !!projectId,
  });

  const { data: tenderSummary } = useQuery({
    queryKey: ["tender-summary", projectId],
    queryFn: ({ signal }) => {
      if (!projectId) throw new Error("No project selected");
      return fetchTenderSummary(projectId, { signal });
    },
    enabled: !!projectId,
    retry: false,
  });

  const confirmPackage = useMutation({
    mutationFn: async (pkg: RequirementPackage) => {
      if (!projectId) throw new Error("No project selected");
      return bulkConfirmRequirements(projectId, pkg.requirements);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["requirement-workbench", projectId] });
    },
  });

  const startAiExtraction = useMutation({
    mutationFn: async () => {
      if (!documentId) throw new Error("No document selected");
      return startTenderAiExtractionRun(documentId);
    },
    onSuccess: (result) => {
      setLatestRunId(result.id);
      if (documentId && typeof window !== "undefined") {
        window.localStorage.setItem(getLatestRunStorageKey(documentId), result.id);
      }
    },
  });

  if (!projectId) {
    return (
      <div className="empty-state">
        <span className="empty-state__icon">项</span>
        <p className="empty-state__title">先选择投标项目</p>
        <p className="empty-state__description">选择项目后，可核对废标红线、资格商务硬条件和递交清单。</p>
      </div>
    );
  }

  const lanes = workbench?.lanes ?? [];
  const laneTabs = lanes.filter((lane) => lane.packages.length > 0);
  const shownLanes = visibleLanes(lanes, activeLane);
  const selected = selectedPackage ?? workbench?.packages[0] ?? null;

  return (
    <div className="requirement-workbench">
      <div className="requirement-workbench__masthead">
        <div>
          <span className="tender-summary-card__eyebrow">Tender Checkdesk</span>
          <h1 className="section-heading">招标解析工作台</h1>
          <p className="requirement-workbench__lead">
            普通条款已自动采纳并保留抽查；这里只处理会影响废标、资格商务、技术响应和递交清单的关键条款。
          </p>
        </div>
        <ClayButton
          onClick={() => startAiExtraction.mutate()}
          disabled={!documentId || startAiExtraction.isPending}
        >
          {startAiExtraction.isPending ? "任务提交中..." : "提交 AI 抽取任务"}
        </ClayButton>
      </div>

      {tenderSummary && (
        <section className="tender-summary-card" aria-label="招标摘要">
          <div className="tender-summary-card__header">
            <div>
              <span className="tender-summary-card__eyebrow">项目基本盘</span>
              <h2>{tenderSummary.project_name ?? "招标摘要"}</h2>
            </div>
            {tenderSummary.extracted_model && <Badge variant="info">{tenderSummary.extracted_model}</Badge>}
          </div>
          <div className="tender-summary-card__grid">
            {[
              ["招标人", tenderSummary.tenderer],
              ["代理机构", tenderSummary.tender_agency],
              ["建设地点", tenderSummary.project_location],
              ["工期/服务期", tenderSummary.construction_period],
              ["质量要求", tenderSummary.quality_requirement],
              ["控制价", tenderSummary.control_price],
              ["保证金", tenderSummary.bid_bond],
              ["截止/开标", tenderSummary.bid_deadline ?? tenderSummary.bid_open_time],
            ].map(([label, value]) => (
              <div className="tender-summary-card__item" key={label}>
                <span>{label}</span>
                <strong>{value || "待抽取"}</strong>
              </div>
            ))}
          </div>
        </section>
      )}

      {latestRunId && <AiExtractionRunPanel runId={latestRunId} />}
      {startAiExtraction.isError && (
        <div className="warning-banner">
          提交失败：{startAiExtraction.error instanceof Error ? startAiExtraction.error.message : "请稍后重试"}
        </div>
      )}

      {workbench && (
        <div className="requirement-workbench__metrics" aria-label="关键条款统计">
          <div><span>原始条款</span><strong>{workbench.stats.total_requirements}</strong></div>
          <div><span>条款包</span><strong>{workbench.stats.package_count}</strong></div>
          <div><span>待确认红线</span><strong>{workbench.stats.blocking_count}</strong></div>
          <div><span>冲突条款</span><strong>{workbench.stats.conflict_count}</strong></div>
          <div><span>自动采纳</span><strong>{workbench.stats.auto_accept_count}</strong></div>
        </div>
      )}

      <div className="requirement-workbench__tabs">
        <button className={`filter-chip ${activeLane === "all" ? "active" : ""}`} onClick={() => setActiveLane("all")}>
          全部工作项
        </button>
        {laneTabs.map((lane) => (
          <button
            key={lane.id}
            className={`filter-chip ${activeLane === lane.id ? "active" : ""}`}
            onClick={() => setActiveLane(lane.id)}
          >
            {lane.label} · {lane.packages.length}
          </button>
        ))}
      </div>

      {isLoading && (
        <div className="skeleton-stack" aria-label="关键条款加载中">
          <div className="skeleton-card" />
          <div className="skeleton-card" />
          <div className="skeleton-card" />
        </div>
      )}

      {!isLoading && workbench?.packages.length === 0 && (
        <div className="empty-state">
          <span className="empty-state__icon">条</span>
          <p className="empty-state__title">暂无解析条款</p>
          <p className="empty-state__description">上传并解析招标文件后，系统会先合并相似条款，再生成关键确认队列。</p>
        </div>
      )}

      {workbench && workbench.packages.length > 0 && (
        <div className="requirement-workbench__grid">
          <div className="requirement-workbench__lanes">
            {shownLanes.map((lane) => (
              <section className="requirement-lane" key={lane.id} aria-label={lane.label}>
                <div className="requirement-lane__header">
                  <h2>{lane.label}</h2>
                  <span>{lane.packages.length} 个条款包</span>
                </div>
                <div className="requirement-package-list">
                  {lane.packages.map((pkg) => (
                    <article
                      key={pkg.id}
                      className={`requirement-package ${selected?.id === pkg.id ? "is-selected" : ""} ${pkg.blocking ? "is-blocking" : ""}`}
                      onClick={() => setSelectedPackage(pkg)}
                    >
                      <div className="requirement-package__topline">
                        <Badge variant={LEVEL_BADGES[pkg.confirmation_level]}>{LEVEL_LABELS[pkg.confirmation_level]}</Badge>
                        {pkg.has_conflict && <Badge variant="danger">字段冲突</Badge>}
                        {pkg.all_confirmed && <Badge variant="success">已确认</Badge>}
                      </div>
                      <h3>{pkg.title}</h3>
                      <p>{pkg.system_conclusion || "系统暂无结论，需查看来源原文。"}</p>
                      <div className="requirement-package__meta">
                        <span>{pkg.source_count} 个来源</span>
                        <span>{formatPercent(pkg.confidence)}</span>
                        {pkg.conflict_fields.length > 0 && <span>{pkg.conflict_fields.map((field) => FIELD_LABELS[field] ?? field).join("、")}</span>}
                      </div>
                      <div className="requirement-package__actions">
                        {pkg.confirmation_level === "critical" && !pkg.all_confirmed && (
                          <ClayButton
                            size="sm"
                            onClick={(event) => {
                              event.stopPropagation();
                              confirmPackage.mutate(pkg);
                            }}
                            disabled={confirmPackage.isPending}
                          >
                            确认本组
                          </ClayButton>
                        )}
                        {pkg.confirmation_level !== "critical" && <span>默认不阻断，可抽查</span>}
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            ))}
          </div>

          <aside className="requirement-trace-panel" aria-label="条款溯源">
            {selected ? (
              <>
                <div className="requirement-trace-panel__header">
                  <span className="tender-summary-card__eyebrow">Source Trace</span>
                  <h2>{selected.title}</h2>
                  <p>{LEVEL_LABELS[selected.confirmation_level]} · {selected.source_count} 个来源</p>
                </div>
                {selected.has_conflict && (
                  <div className="requirement-conflict-box">
                    <strong>需要人工确认</strong>
                    <span>{selected.conflict_fields.map((field) => FIELD_LABELS[field] ?? field).join("、")} 存在差异，系统不会自动合并为单一结论。</span>
                  </div>
                )}
                {Object.entries(selected.key_fields).length > 0 && (
                  <div className="requirement-key-fields">
                    {Object.entries(selected.key_fields).map(([field, values]) => (
                      <div key={field}>
                        <span>{FIELD_LABELS[field] ?? field}</span>
                        <strong>{values.join(" / ")}</strong>
                      </div>
                    ))}
                  </div>
                )}
                <div className="requirement-source-list">
                  {selected.sources.map((source) => (
                    <div className="requirement-source-card" key={source.requirement_id}>
                      <div>
                        <strong>{source.title || "来源条款"}</strong>
                        <span>{fileName(source.source_file)} {source.source_locator ? `· ${source.source_locator}` : ""}</span>
                      </div>
                      <p>{source.text}</p>
                      <div className="requirement-source-card__actions">
                        {source.human_confirmed ? <Badge variant="success">已确认</Badge> : <Badge variant="warning">未确认</Badge>}
                        {source.source_chunk_id && (
                          <ClayButton variant="ghost" size="sm" onClick={() => setSourceChunkId(source.source_chunk_id)}>
                            查看原文
                          </ClayButton>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="empty-state">
                <p className="empty-state__title">选择一个条款包</p>
                <p className="empty-state__description">右侧会显示原文、来源页码、冲突字段和处理记录。</p>
              </div>
            )}
          </aside>
        </div>
      )}

      <SourceChunkViewer chunkId={sourceChunkId} onClose={() => setSourceChunkId(null)} />
    </div>
  );
}
