import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchRequirements, confirmRequirement } from "../../lib/api";
import { useNavigation } from "../../lib/NavigationContext";
import { Card } from "../../components/ui/Card";
import { ClayButton } from "../../components/ui/ClayButton";
import { Badge } from "../../components/ui/Badge";

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
  const { projectId } = useNavigation();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<string>("");

  const { data: requirements = [], isLoading } = useQuery({
    queryKey: ["requirements", projectId, filter],
    queryFn: ({ signal }) => {
      if (!projectId) throw new Error("No project selected");
      return fetchRequirements(projectId, filter || undefined, { signal });
    },
    enabled: !!projectId,
  });

  const confirm = useMutation({
    mutationFn: confirmRequirement,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["requirements", projectId] });
    },
  });

  if (!projectId) {
    return <p className="empty-state">请先从「投标项目」模块选择一个项目</p>;
  }

  const vetoUnconfirmed = requirements.filter(
    (r) => r.category === "veto" && !r.human_confirmed,
  ).length;

  return (
    <div>
      <h1 className="section-heading">要求确认</h1>

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

      {isLoading && <div className="spinner" />}

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
            <h3 style={{ margin: "var(--space-2) 0 var(--space-1)" }}>{r.title}</h3>
            {r.source_text && <p className="source-text">{r.source_text}</p>}
          </Card>
        ))}
        {!isLoading && requirements.length === 0 && (
          <p className="empty-state">暂无要求记录</p>
        )}
      </div>
    </div>
  );
}
