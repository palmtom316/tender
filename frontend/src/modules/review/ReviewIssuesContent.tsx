import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchReviewIssues, resolveIssue, runBidReview } from "../../lib/api";
import { useNavigation } from "../../lib/NavigationContext";
import { Card } from "../../components/ui/Card";
import { ClayButton } from "../../components/ui/ClayButton";
import { Badge } from "../../components/ui/Badge";

const SEVERITY_VARIANT: Record<string, "danger" | "warning" | "info" | "success"> = {
  P0: "danger",
  P1: "warning",
  P2: "info",
  P3: "success",
};

function qualityMetrics(issue: { metadata_json?: Record<string, unknown> }) {
  const metrics = issue.metadata_json?.quality_metrics;
  return metrics && typeof metrics === "object" ? metrics as Record<string, unknown> : null;
}

function percent(value: unknown) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

export function ReviewIssuesContent() {
  const { projectId } = useNavigation();
  const queryClient = useQueryClient();

  const { data: issues = [], isLoading } = useQuery({
    queryKey: ["review-issues", projectId],
    queryFn: ({ signal }) => {
      if (!projectId) throw new Error("No project selected");
      return fetchReviewIssues(projectId, { signal });
    },
    enabled: !!projectId,
  });

  const resolve = useMutation({
    mutationFn: resolveIssue,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["review-issues", projectId] });
    },
  });

  const review = useMutation({
    mutationFn: () => {
      if (!projectId) throw new Error("No project selected");
      return runBidReview(projectId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["review-issues", projectId] });
    },
  });

  if (!projectId) {
    return <p className="empty-state">请先从「投标项目」模块选择一个项目</p>;
  }

  const blocking = issues.filter(
    (i) => ["P0", "P1"].includes(i.severity) && !i.resolved,
  );

  return (
    <div>
      <h1 className="section-heading">审查问题</h1>
      <div className="toolbar-row">
        <ClayButton onClick={() => review.mutate()} disabled={review.isPending}>
          {review.isPending ? "审查中..." : "运行投标审查"}
        </ClayButton>
      </div>

      {blocking.length > 0 && (
        <div className="warning-banner">
          {blocking.length} 条阻断性问题（P0/P1），导出将被阻断
        </div>
      )}

      {isLoading && <div className="spinner" />}

      <div className="requirement-list">
        {issues.map((issue) => (
          <Card
            key={issue.id}
            style={issue.resolved ? { opacity: 0.7 } : undefined}
          >
            <div className="requirement-header">
              <Badge variant={SEVERITY_VARIANT[issue.severity] ?? "info"}>
                {issue.severity}
              </Badge>
              {issue.resolved ? (
                <Badge variant="success">已解决</Badge>
              ) : (
                <ClayButton
                  size="sm"
                  onClick={() => resolve.mutate(issue.id)}
                  disabled={resolve.isPending}
                >
                  标记已解决
                </ClayButton>
              )}
            </div>
            <h3 style={{ margin: "var(--space-2) 0 var(--space-1)" }}>{issue.title}</h3>
            {issue.detail && <p className="source-text">{issue.detail}</p>}
            {qualityMetrics(issue) && (
              <div className="review-metric-strip" aria-label="章节质量指标">
                <span>策略章节覆盖 {percent(qualityMetrics(issue)?.required_section_coverage)}</span>
                <span>约束响应覆盖 {percent(qualityMetrics(issue)?.confirmed_constraint_coverage)}</span>
                <span>
                  实质段落 {Number(qualityMetrics(issue)?.substantive_paragraph_count || 0)}/
                  {Number(qualityMetrics(issue)?.minimum_substantive_paragraph_count || 0)}
                </span>
                <span>泛化密度 {Number(qualityMetrics(issue)?.generic_phrase_density || 0)}</span>
              </div>
            )}
          </Card>
        ))}
        {!isLoading && issues.length === 0 && (
          <p className="empty-state">暂无审校问题</p>
        )}
      </div>
    </div>
  );
}
