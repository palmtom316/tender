import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  buildConstraintSet,
  bulkConfirmRequirements,
  confirmConstraintSet,
  createTenderClarification,
  fetchConstraintSet,
  fetchRequirementWorkbench,
  fetchTenderSummary,
  listTenderClarifications,
  mergeRequirements,
  rejectRequirement,
  splitRequirementForReview,
  startTenderAiExtractionRun,
  type RequirementPackage,
  type RequirementWorkbenchLane,
  type TenderClarification,
  updateRequirement,
  uploadTenderClarification,
} from "../../lib/api";
import { useNavigation } from "../../lib/NavigationContext";
import { ClayButton } from "../../components/ui/ClayButton";
import { Badge } from "../../components/ui/Badge";
import { ProgressBar, type ProgressMeta } from "../../components/ui/ProgressBar";
import { AiExtractionRunPanel } from "./AiExtractionRunPanel";
import { EquipmentSelectionWorkbench } from "./EquipmentSelectionWorkbench";
import { PersonnelSelectionWorkbench } from "./PersonnelSelectionWorkbench";
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

function impactPayload(item: TenderClarification) {
  return item.impact_json as Partial<{
    created_requirement_count: number;
    superseded_requirement_count: number;
    stale_outline_count: number;
    stale_chapter_count: number;
    stale_draft_count: number;
    requires_reconfirmation: boolean;
  }>;
}

function hasReconfirmationImpact(item: TenderClarification) {
  return Boolean(impactPayload(item).requires_reconfirmation);
}

function impactSummary(item: TenderClarification) {
  const impact = impactPayload(item);
  return `新增 ${impact.created_requirement_count ?? 0} 条，覆盖 ${impact.superseded_requirement_count ?? 0} 条，标记 ${impact.stale_chapter_count ?? 0} 个章节 stale`;
}

type UploadStageMeta = ProgressMeta;

function clarificationTextMeta(params: {
  text: string;
  isPending: boolean;
  isSuccess: boolean;
  isError: boolean;
}): UploadStageMeta {
  if (params.isError) {
    return {
      percent: 100,
      label: "文字分析失败",
      hint: "请检查文本内容后重试，系统会重新匹配前文条款",
      tone: "danger",
    };
  }
  if (params.isSuccess) {
    return {
      percent: 100,
      label: "文字分析完成",
      hint: "已完成条款比对并回写覆盖影响",
      tone: "success",
    };
  }
  if (params.isPending) {
    return {
      percent: 72,
      label: "文字分析中",
      hint: "系统正在解析文本并匹配前文条款",
      tone: "active",
    };
  }
  if (params.text.trim()) {
    return {
      percent: 18,
      label: "待提交文字",
      hint: "文本已录入，提交后会直接进入覆盖分析",
      tone: "default",
    };
  }
  return {
    percent: 0,
    label: "未录入文字",
    hint: "粘贴答疑、澄清或补遗正文后，系统会自动分类并匹配前文条款",
    tone: "default",
  };
}

function clarificationUploadMeta(params: {
  hasFile: boolean;
  isPending: boolean;
  isSuccess: boolean;
  isError: boolean;
  fileName: string | null;
}): UploadStageMeta {
  if (params.isError) {
    return {
      percent: 100,
      label: "分析失败",
      hint: `文件 ${params.fileName ?? ""} 处理失败，请检查格式或解析配置`.trim(),
      tone: "danger",
    };
  }
  if (params.isSuccess) {
    return {
      percent: 100,
      label: "影响分析完成",
      hint: `文件 ${params.fileName ?? ""} 已完成解析并回写条款影响`.trim(),
      tone: "success",
    };
  }
  if (params.isPending) {
    return {
      percent: 72,
      label: "解析与分析中",
      hint: `文件 ${params.fileName ?? ""} 已上传，服务端正在解析并比对前文条款`.trim(),
      tone: "active",
    };
  }
  if (params.hasFile) {
    return {
      percent: 18,
      label: "待上传",
      hint: `已选择文件 ${params.fileName ?? ""}，提交后会直接进入解析与影响分析`.trim(),
      tone: "default",
    };
  }
  return {
    percent: 0,
    label: "未选择文件",
    hint: "可上传 doc、docx、pdf，系统会自动解析文本并分析覆盖影响",
    tone: "default",
  };
}

export function RequirementsContent() {
  const { projectId, documentId } = useNavigation();
  const queryClient = useQueryClient();
  const [activeLane, setActiveLane] = useState("all");
  const [sourceChunkId, setSourceChunkId] = useState<string | null>(null);
  const [selectedPackage, setSelectedPackage] = useState<RequirementPackage | null>(null);
  const [latestRunId, setLatestRunId] = useState<string | null>(null);
  const [clarificationText, setClarificationText] = useState("");
  const [clarificationTitle, setClarificationTitle] = useState("澄清/补遗文件");
  const [clarificationFile, setClarificationFile] = useState<File | null>(null);
  const [expandedRiskCard, setExpandedRiskCard] = useState<"blocking" | "conflict" | null>(null);

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

  const { data: constraintSet } = useQuery({
    queryKey: ["constraint-set", projectId],
    queryFn: ({ signal }) => {
      if (!projectId) throw new Error("No project selected");
      return fetchConstraintSet(projectId, { signal });
    },
    enabled: !!projectId,
    retry: false,
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

  const { data: clarifications = [] } = useQuery({
    queryKey: ["tender-clarifications", projectId],
    queryFn: ({ signal }) => {
      if (!projectId) throw new Error("No project selected");
      return listTenderClarifications(projectId, { signal });
    },
    enabled: !!projectId,
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

  const packageAction = useMutation({
    mutationFn: async ({ action, pkg }: { action: "reject" | "pricing_ignored" | "promote" | "merge" | "split"; pkg: RequirementPackage }) => {
      const ids = pkg.requirements;
      if (ids.length === 0) return null;
      if (action === "merge") return mergeRequirements(ids[0], ids.slice(1));
      if (action === "split") return splitRequirementForReview(ids[0]);
      if (action === "reject") return Promise.all(ids.map((id) => rejectRequirement(id)));
      if (action === "pricing_ignored") return Promise.all(ids.map((id) => updateRequirement(id, { ignored_for_pricing: true, review_status: "rejected" })));
      return Promise.all(ids.map((id) => updateRequirement(id, { is_hard_constraint: true, requires_human_confirm: true })));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["requirement-workbench", projectId] });
      queryClient.invalidateQueries({ queryKey: ["constraint-set", projectId] });
    },
  });

  const buildConstraints = useMutation({
    mutationFn: async () => {
      if (!projectId) throw new Error("No project selected");
      return buildConstraintSet(projectId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["constraint-set", projectId] });
      queryClient.invalidateQueries({ queryKey: ["requirement-workbench", projectId] });
    },
  });

  const confirmConstraints = useMutation({
    mutationFn: async () => {
      if (!projectId) throw new Error("No project selected");
      return confirmConstraintSet(projectId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["constraint-set", projectId] });
      queryClient.invalidateQueries({ queryKey: ["export-gates", projectId] });
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

  const createClarification = useMutation({
    mutationFn: async () => {
      if (!projectId) throw new Error("No project selected");
      return createTenderClarification(projectId, {
        title: clarificationTitle || "澄清/补遗文件",
        clarification_type: "addendum",
        content_text: clarificationText,
      });
    },
    onSuccess: () => {
      setClarificationText("");
      queryClient.invalidateQueries({ queryKey: ["requirement-workbench", projectId] });
      queryClient.invalidateQueries({ queryKey: ["tender-clarifications", projectId] });
      queryClient.invalidateQueries({ queryKey: ["bid-outline", projectId] });
      queryClient.invalidateQueries({ queryKey: ["drafts", projectId] });
    },
  });

  const uploadClarification = useMutation({
    mutationFn: async () => {
      if (!projectId) throw new Error("No project selected");
      if (!clarificationFile) throw new Error("请先选择澄清/补遗文件");
      return uploadTenderClarification(projectId, {
        title: clarificationTitle || clarificationFile.name || "澄清/补遗文件",
        clarification_type: "addendum",
        file: clarificationFile,
      });
    },
    onSuccess: () => {
      setClarificationFile(null);
      queryClient.invalidateQueries({ queryKey: ["requirement-workbench", projectId] });
      queryClient.invalidateQueries({ queryKey: ["tender-clarifications", projectId] });
      queryClient.invalidateQueries({ queryKey: ["bid-outline", projectId] });
      queryClient.invalidateQueries({ queryKey: ["drafts", projectId] });
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
  const selected = selectedPackage ?? workbench?.packages[0] ?? null;
  const blockingPackages = useMemo(
    () => workbench?.packages.filter((pkg) => pkg.blocking) ?? [],
    [workbench],
  );
  const conflictPackages = useMemo(
    () => workbench?.packages.filter((pkg) => pkg.has_conflict) ?? [],
    [workbench],
  );
  const orderedShownLanes = useMemo(
    () =>
      visibleLanes(lanes, activeLane).map((lane) => ({
        ...lane,
        packages: [...lane.packages].sort((left, right) => {
          const leftRank = left.all_confirmed ? 1 : 0;
          const rightRank = right.all_confirmed ? 1 : 0;
          if (leftRank !== rightRank) return leftRank - rightRank;
          if (left.blocking !== right.blocking) return Number(right.blocking) - Number(left.blocking);
          if (left.has_conflict !== right.has_conflict) return Number(right.has_conflict) - Number(left.has_conflict);
          return (right.confidence ?? 0) - (left.confidence ?? 0);
        }),
      })),
    [lanes, activeLane],
  );
  const uploadMeta = clarificationUploadMeta({
    hasFile: Boolean(clarificationFile),
    isPending: uploadClarification.isPending,
    isSuccess: uploadClarification.isSuccess,
    isError: uploadClarification.isError,
    fileName: clarificationFile?.name ?? uploadClarification.data?.source_file ?? null,
  });
  const textMeta = clarificationTextMeta({
    text: clarificationText,
    isPending: createClarification.isPending,
    isSuccess: createClarification.isSuccess,
    isError: createClarification.isError,
  });
  const constraintSetStatus = String((constraintSet as { status?: string } | undefined)?.status || "not_built");
  const constraintItemCount = Array.isArray(constraintSet?.items) ? constraintSet.items.length : 0;
  const canConfirmConstraintSet = Boolean(constraintSet && constraintItemCount > 0 && constraintSetStatus !== "confirmed");

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

      {workbench && (
        <section className="workflow-gate-panel" aria-label="约束集确认里程碑">
          <div>
            <strong>确认约束集</strong>
            <p>
              {constraintSetStatus === "confirmed"
                ? `已确认 ${constraintItemCount} 条约束，后续目录映射、商务装配、技术生成和导出以该版本为准。`
                : `当前有 ${workbench.stats.package_count} 个条款包，需生成并确认约束集后再进入目录映射。`}
            </p>
          </div>
          <div className="workflow-gate-panel__chips">
            <span>状态：{constraintSetStatus === "not_built" ? "未生成" : constraintSetStatus}</span>
            <span>阻断：{workbench.stats.blocking_count}</span>
            <span>冲突：{workbench.stats.conflict_count}</span>
          </div>
          <div className="toolbar-row" style={{ margin: 0 }}>
            <ClayButton
              variant="secondary"
              onClick={() => buildConstraints.mutate()}
              disabled={buildConstraints.isPending || workbench.stats.package_count === 0}
            >
              {buildConstraints.isPending ? "生成中..." : "生成约束集"}
            </ClayButton>
            <ClayButton
              onClick={() => confirmConstraints.mutate()}
              disabled={!canConfirmConstraintSet || confirmConstraints.isPending}
            >
              {constraintSetStatus === "confirmed" ? "约束集已确认" : confirmConstraints.isPending ? "确认中..." : "确认约束集"}
            </ClayButton>
          </div>
        </section>
      )}

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

      <EquipmentSelectionWorkbench projectId={projectId} />
      <PersonnelSelectionWorkbench projectId={projectId} />

      <section className="clarification-impact-panel" aria-label="澄清补遗影响分析">
        <div className="clarification-impact-panel__header">
          <div>
            <span className="tender-summary-card__eyebrow">Later File Wins</span>
            <h2>澄清/补遗覆盖分析</h2>
            <p>后发文件覆盖前文；系统会自动标记受影响条款、大纲、章节和草稿为 stale，并把新条款送回关键确认。</p>
          </div>
          <Badge variant={clarifications.some(hasReconfirmationImpact) ? "danger" : "info"}>
            {clarifications.some(hasReconfirmationImpact) ? "需重新确认" : "无待处理影响"}
          </Badge>
        </div>
        <div className="clarification-impact-panel__form">
          <input
            className="clay-input"
            value={clarificationTitle}
            onChange={(event) => setClarificationTitle(event.target.value)}
            aria-label="澄清补遗标题"
          />
          <div className="clarification-impact-panel__entry-grid">
            <div className="clarification-impact-panel__entry">
              <div className="clarification-impact-panel__entry-header">
                <strong>粘贴文字</strong>
                <span>适合快速录入答疑、澄清或补遗正文</span>
              </div>
              <textarea
                className="clay-textarea"
                value={clarificationText}
                onChange={(event) => setClarificationText(event.target.value)}
                placeholder="粘贴澄清、答疑或补遗文件中的关键文字。系统会按类别和相似度匹配前文条款。"
                aria-label="澄清补遗内容"
              />
              <ClayButton
                size="lg"
                className="clarification-impact-panel__action"
                onClick={() => createClarification.mutate()}
                disabled={!clarificationText.trim() || createClarification.isPending}
              >
                {createClarification.isPending ? "分析中..." : "保存文字并分析"}
              </ClayButton>
              <ProgressBar meta={textMeta} role="status" ariaLive="polite" />
            </div>
            <div className="clarification-impact-panel__entry">
              <div className="clarification-impact-panel__entry-header">
                <strong>上传文件</strong>
                <span>支持 doc、docx、pdf，上传后进入解析并自动分析影响</span>
              </div>
              <label className="clarification-upload-picker">
                <input
                  type="file"
                  accept=".doc,.docx,.pdf,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  onChange={(event) => setClarificationFile(event.target.files?.[0] ?? null)}
                />
                <span>{clarificationFile ? clarificationFile.name : "选择澄清/补遗文件"}</span>
              </label>
              <ClayButton
                size="lg"
                className="clarification-impact-panel__action"
                onClick={() => uploadClarification.mutate()}
                disabled={!clarificationFile || uploadClarification.isPending}
              >
                {uploadClarification.isPending ? "解析并分析中..." : "上传文件并分析"}
              </ClayButton>
              <ProgressBar meta={uploadMeta} role="status" ariaLive="polite" />
            </div>
          </div>
        </div>
        {createClarification.isError && (
          <div className="warning-banner">
            影响分析失败：{createClarification.error instanceof Error ? createClarification.error.message : "请稍后重试"}
          </div>
        )}
        {uploadClarification.isError && (
          <div className="warning-banner">
            文件分析失败：{uploadClarification.error instanceof Error ? uploadClarification.error.message : "请稍后重试"}
          </div>
        )}
        {clarifications.length > 0 && (
          <div className="clarification-impact-list">
            {clarifications.slice(0, 3).map((item) => (
              <div className="clarification-impact-card" key={item.id}>
                <strong>{item.title}</strong>
                <span>{impactSummary(item)}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {workbench && (
        <div className="requirement-workbench__metrics" aria-label="关键条款统计">
          <div><span>原始条款</span><strong>{workbench.stats.total_requirements}</strong></div>
          <div><span>条款包</span><strong>{workbench.stats.package_count}</strong></div>
          <button className={`requirement-metric-card ${expandedRiskCard === "blocking" ? "is-active" : ""}`} type="button" onClick={() => setExpandedRiskCard((value) => (value === "blocking" ? null : "blocking"))}>
            <span>待确认红线</span>
            <strong>{workbench.stats.blocking_count}</strong>
          </button>
          <button className={`requirement-metric-card ${expandedRiskCard === "conflict" ? "is-active" : ""}`} type="button" onClick={() => setExpandedRiskCard((value) => (value === "conflict" ? null : "conflict"))}>
            <span>冲突条款</span>
            <strong>{workbench.stats.conflict_count}</strong>
          </button>
          <div><span>自动采纳</span><strong>{workbench.stats.auto_accept_count}</strong></div>
        </div>
      )}

      {([
        { kind: "blocking", heading: "待确认红线相关条款", packages: blockingPackages },
        { kind: "conflict", heading: "冲突条款相关条款", packages: conflictPackages },
      ] as const).map((panel) =>
        expandedRiskCard === panel.kind && panel.packages.length > 0 ? (
          <section key={panel.kind} className="requirement-risk-panel" aria-label={panel.heading}>
            <div className="requirement-risk-panel__header">
              <h2>{panel.heading}</h2>
              <span>{panel.packages.length} 个条款包</span>
            </div>
            <div className="requirement-package-list requirement-package-list--tri">
              {panel.packages.map((pkg) => (
                <article key={pkg.id} className={`requirement-package ${selected?.id === pkg.id ? "is-selected" : ""} ${pkg.blocking ? "is-blocking" : ""}`} onClick={() => setSelectedPackage(pkg)}>
                  <div className="requirement-package__topline">
                    <Badge variant={LEVEL_BADGES[pkg.confirmation_level]}>{LEVEL_LABELS[pkg.confirmation_level]}</Badge>
                    {pkg.has_conflict && <Badge variant="danger">字段冲突</Badge>}
                    {pkg.all_confirmed && <Badge variant="success">已确认</Badge>}
                  </div>
                  <h3>{pkg.title}</h3>
                  <p>{pkg.system_conclusion || "系统暂无结论，需查看来源原文。"}</p>
                </article>
              ))}
            </div>
          </section>
        ) : null,
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
            {orderedShownLanes.map((lane) => (
              <section className="requirement-lane" key={lane.id} aria-label={lane.label}>
                <div className="requirement-lane__header">
                  <h2>{lane.label}</h2>
                  <span>{lane.packages.length} 个条款包</span>
                </div>
                <div className="requirement-package-list requirement-package-list--tri">
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
                        <ClayButton size="sm" variant="ghost" onClick={(event) => { event.stopPropagation(); packageAction.mutate({ action: "promote", pkg }); }} disabled={packageAction.isPending}>
                          提为关键
                        </ClayButton>
                        <ClayButton size="sm" variant="ghost" onClick={(event) => { event.stopPropagation(); packageAction.mutate({ action: "pricing_ignored", pkg }); }} disabled={packageAction.isPending}>
                          标记报价忽略
                        </ClayButton>
                        <ClayButton size="sm" variant="ghost" onClick={(event) => { event.stopPropagation(); packageAction.mutate({ action: "merge", pkg }); }} disabled={packageAction.isPending || pkg.requirements.length < 2}>
                          合并
                        </ClayButton>
                        <ClayButton size="sm" variant="ghost" onClick={(event) => { event.stopPropagation(); packageAction.mutate({ action: "split", pkg }); }} disabled={packageAction.isPending}>
                          拆分复核
                        </ClayButton>
                        <ClayButton size="sm" variant="danger" onClick={(event) => { event.stopPropagation(); packageAction.mutate({ action: "reject", pkg }); }} disabled={packageAction.isPending}>
                          剔除
                        </ClayButton>
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
