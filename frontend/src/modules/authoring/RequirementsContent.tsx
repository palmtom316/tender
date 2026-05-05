import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchRequirements,
  confirmRequirement,
  fetchTenderSummary,
  startTenderAiExtractionRun,
} from "../../lib/api";
import { useNavigation } from "../../lib/NavigationContext";
import { Card } from "../../components/ui/Card";
import { ClayButton } from "../../components/ui/ClayButton";
import { Badge } from "../../components/ui/Badge";
import { AiExtractionRunPanel } from "./AiExtractionRunPanel";
import { SourceChunkViewer } from "./SourceChunkViewer";

const CATEGORY_LABELS: Record<string, string> = {
  veto: "否决项",
  qualification: "资质要求",
  personnel: "人员要求",
  performance: "业绩要求",
  technical: "技术要求",
  scoring: "评分标准",
  format: "格式要求",
};

export function RequirementsContent() {
  const { projectId, documentId } = useNavigation();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<string>("");
  const [sourceChunkId, setSourceChunkId] = useState<string | null>(null);
  const [latestRunId, setLatestRunId] = useState<string | null>(null);

  const { data: requirements = [], isLoading } = useQuery({
    queryKey: ["requirements", projectId, filter],
    queryFn: ({ signal }) => {
      if (!projectId) throw new Error("No project selected");
      return fetchRequirements(projectId, filter || undefined, { signal });
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

  const confirm = useMutation({
    mutationFn: confirmRequirement,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["requirements", projectId] });
    },
  });

  const startAiExtraction = useMutation({
    mutationFn: async () => {
      if (!documentId) throw new Error("No document selected");
      return startTenderAiExtractionRun(documentId);
    },
    onSuccess: (result) => {
      setLatestRunId(result.run_id);
    },
  });

  if (!projectId) {
    return (
      <div className="empty-state">
        <span className="empty-state__icon">项</span>
        <p className="empty-state__title">先选择投标项目</p>
        <p className="empty-state__description">选择项目后，可确认否决项、资质要求和评分规则。</p>
      </div>
    );
  }

  const vetoUnconfirmed = requirements.filter(
    (r) => r.category === "veto" && !r.human_confirmed,
  ).length;

  return (
    <div>
      <h1 className="section-heading">要求确认</h1>

      {tenderSummary && (
        <section className="tender-summary-card" aria-label="招标摘要">
          <div className="tender-summary-card__header">
            <div>
              <span className="tender-summary-card__eyebrow">Tender Brief</span>
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

      <div className="requirement-toolbar">
        <div>
          <span className="tender-summary-card__eyebrow">AI Extraction</span>
          <p className="requirement-toolbar__hint">
            对当前招标文件启动异步 AI 抽取，并查看批次级进度与失败详情。
          </p>
        </div>
        <ClayButton
          onClick={() => startAiExtraction.mutate()}
          disabled={!documentId || startAiExtraction.isPending}
        >
          {startAiExtraction.isPending ? "抽取提交中..." : "开始 AI 抽取"}
        </ClayButton>
      </div>

      {latestRunId && <AiExtractionRunPanel runId={latestRunId} />}

      {vetoUnconfirmed > 0 && (
        <div className="warning-banner">
          {vetoUnconfirmed} 条否决项未确认，导出将被阻断
        </div>
      )}

      <div className="filter-bar">
        <button
          className={`filter-chip ${filter === "" ? "active" : ""}`}
          onClick={() => setFilter("")}
        >
          全部
        </button>
        {Object.entries(CATEGORY_LABELS).map(([key, label]) => (
          <button
            key={key}
            className={`filter-chip ${filter === key ? "active" : ""}`}
            onClick={() => setFilter(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {isLoading && (
        <div className="skeleton-stack" aria-label="要求列表加载中">
          <div className="skeleton-card" />
          <div className="skeleton-card" />
          <div className="skeleton-card" />
        </div>
      )}

      <div className="requirement-list">
        {requirements.map((r) => (
          <Card
            key={r.id}
            style={r.human_confirmed ? { opacity: 0.7 } : undefined}
          >
            <div className="requirement-header">
              <Badge variant="primary">{CATEGORY_LABELS[r.category] ?? r.category}</Badge>
              {r.human_confirmed ? (
                <Badge variant="success">已确认 ({r.confirmed_by})</Badge>
              ) : (
                <ClayButton
                  size="sm"
                  onClick={() => confirm.mutate(r.id)}
                  disabled={confirm.isPending}
                >
                  确认
                </ClayButton>
              )}
            </div>
            <h3 className="requirement-title">{r.title}</h3>
            {r.source_text && <p className="source-text">{r.source_text}</p>}
            <div className="requirement-actions">
              {r.source_file && <span className="requirement-source-file">{r.source_file.split("/").pop()}</span>}
              {r.source_chunk_id && (
                <ClayButton variant="ghost" size="sm" onClick={() => setSourceChunkId(r.source_chunk_id ?? null)}>
                  查看原文
                </ClayButton>
              )}
            </div>
          </Card>
        ))}
        {!isLoading && requirements.length === 0 && (
          <div className="empty-state">
            <span className="empty-state__icon">要</span>
            <p className="empty-state__title">暂无要求记录</p>
            <p className="empty-state__description">解析招标文件后，关键要求会按类别汇总到这里供人工确认。</p>
          </div>
        )}
      </div>
      <SourceChunkViewer chunkId={sourceChunkId} onClose={() => setSourceChunkId(null)} />
    </div>
  );
}
