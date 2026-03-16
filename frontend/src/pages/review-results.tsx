import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

interface ReviewResultsPageProps {
  projectId: string;
}

interface ReviewIssue {
  id: string;
  severity: string;
  title: string;
  detail: string | null;
  resolved: boolean;
}

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const TOKEN = localStorage.getItem("tender_token") ?? "dev-token";
const headers = { Authorization: `Bearer ${TOKEN}` };

const SEVERITY_COLORS: Record<string, { bg: string; color: string }> = {
  P0: { bg: "#fef2f2", color: "#dc2626" },
  P1: { bg: "#fff7ed", color: "#ea580c" },
  P2: { bg: "#fefce8", color: "#ca8a04" },
  P3: { bg: "#f0fdf4", color: "#16a34a" },
};

async function fetchIssues(projectId: string): Promise<ReviewIssue[]> {
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/review-issues`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function resolveIssue(issueId: string): Promise<ReviewIssue> {
  const res = await fetch(`${BASE_URL}/api/review-issues/${issueId}/resolve`, {
    method: "POST",
    headers,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function ReviewResultsPage({ projectId }: ReviewResultsPageProps) {
  const queryClient = useQueryClient();

  const { data: issues = [], isLoading } = useQuery({
    queryKey: ["review-issues", projectId],
    queryFn: () => fetchIssues(projectId),
  });

  const resolve = useMutation({
    mutationFn: resolveIssue,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["review-issues", projectId] });
    },
  });

  const blocking = issues.filter((i) => ["P0", "P1"].includes(i.severity) && !i.resolved);

  return (
    <div className="page">
      <div className="page-header">
        <a href={`/projects/${projectId}/editor`} className="back-link">&larr; 返回编辑</a>
        <h1>审校结果</h1>
      </div>

      {blocking.length > 0 && (
        <div className="card" style={{ borderColor: "#dc2626", background: "#fef2f2", marginBottom: 16 }}>
          <p style={{ margin: 0, color: "#dc2626", fontWeight: 600 }}>
            {blocking.length} 条阻断性问题（P0/P1），导出将被阻断
          </p>
        </div>
      )}

      {isLoading && <p>加载中...</p>}

      <div className="requirement-list">
        {issues.map((issue) => {
          const colors = SEVERITY_COLORS[issue.severity] ?? SEVERITY_COLORS.P3;
          return (
            <div key={issue.id} className={`card requirement-card ${issue.resolved ? "confirmed" : ""}`}>
              <div className="requirement-header">
                <span className="badge" style={{ background: colors.bg, color: colors.color }}>
                  {issue.severity}
                </span>
                {issue.resolved ? (
                  <span className="badge" style={{ background: "#dcfce7", color: "#166534" }}>已解决</span>
                ) : (
                  <button
                    className="btn-primary"
                    onClick={() => resolve.mutate(issue.id)}
                    disabled={resolve.isPending}
                  >
                    标记已解决
                  </button>
                )}
              </div>
              <h3 style={{ margin: "8px 0 4px" }}>{issue.title}</h3>
              {issue.detail && <p className="source-text">{issue.detail}</p>}
            </div>
          );
        })}
        {!isLoading && issues.length === 0 && (
          <p className="empty">暂无审校问题</p>
        )}
      </div>
    </div>
  );
}
