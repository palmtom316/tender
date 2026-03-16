import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

interface RequirementsConfirmationPageProps {
  projectId: string;
}

interface Requirement {
  id: string;
  category: string;
  title: string;
  source_text: string | null;
  human_confirmed: boolean;
  confirmed_by: string | null;
}

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const TOKEN = localStorage.getItem("tender_token") ?? "dev-token";
const headers = { Authorization: `Bearer ${TOKEN}` };

const CATEGORY_LABELS: Record<string, string> = {
  veto: "否决项",
  qualification: "资质要求",
  personnel: "人员要求",
  performance: "业绩要求",
  technical: "技术要求",
  scoring: "评分标准",
  format: "格式要求",
};

async function fetchRequirements(projectId: string, category?: string): Promise<Requirement[]> {
  const params = category ? `?category=${category}` : "";
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/requirements${params}`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function confirmRequirement(id: string): Promise<Requirement> {
  const res = await fetch(`${BASE_URL}/api/requirements/${id}/confirm`, {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify({ confirmed: true }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function RequirementsConfirmationPage({ projectId }: RequirementsConfirmationPageProps) {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<string>("");

  const { data: requirements = [], isLoading } = useQuery({
    queryKey: ["requirements", projectId, filter],
    queryFn: () => fetchRequirements(projectId, filter || undefined),
  });

  const confirm = useMutation({
    mutationFn: confirmRequirement,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["requirements", projectId] });
    },
  });

  const vetoUnconfirmed = requirements.filter(
    (r) => r.category === "veto" && !r.human_confirmed
  ).length;

  return (
    <div className="page">
      <div className="page-header">
        <a href={`/projects/${projectId}/upload`} className="back-link">&larr; 返回</a>
        <h1>要求确认</h1>
      </div>

      {vetoUnconfirmed > 0 && (
        <div className="card" style={{ borderColor: "#dc2626", background: "#fef2f2", marginBottom: 16 }}>
          <p style={{ margin: 0, color: "#dc2626", fontWeight: 600 }}>
            {vetoUnconfirmed} 条否决项未确认，导出将被阻断
          </p>
        </div>
      )}

      <div className="filter-bar">
        <button
          className={`filter-btn ${filter === "" ? "active" : ""}`}
          onClick={() => setFilter("")}
        >
          全部
        </button>
        {Object.entries(CATEGORY_LABELS).map(([key, label]) => (
          <button
            key={key}
            className={`filter-btn ${filter === key ? "active" : ""}`}
            onClick={() => setFilter(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {isLoading && <p>加载中...</p>}

      <div className="requirement-list">
        {requirements.map((r) => (
          <div key={r.id} className={`card requirement-card ${r.human_confirmed ? "confirmed" : ""}`}>
            <div className="requirement-header">
              <span className="badge">{CATEGORY_LABELS[r.category] ?? r.category}</span>
              {r.human_confirmed ? (
                <span className="badge" style={{ background: "#dcfce7", color: "#166534" }}>
                  已确认 ({r.confirmed_by})
                </span>
              ) : (
                <button
                  className="btn-primary"
                  onClick={() => confirm.mutate(r.id)}
                  disabled={confirm.isPending}
                >
                  确认
                </button>
              )}
            </div>
            <h3 style={{ margin: "8px 0 4px" }}>{r.title}</h3>
            {r.source_text && (
              <p className="source-text">{r.source_text}</p>
            )}
          </div>
        ))}
        {!isLoading && requirements.length === 0 && (
          <p className="empty">暂无要求记录</p>
        )}
      </div>
    </div>
  );
}
