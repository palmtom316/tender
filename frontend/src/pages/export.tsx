import { useQuery } from "@tanstack/react-query";

interface ExportPageProps {
  projectId: string;
}

interface ExportGates {
  gates: {
    veto_confirmed: boolean;
    unconfirmed_veto_count: number;
    review_passed: boolean;
    blocking_issue_count: number;
    format_passed: boolean;
  };
  can_export: boolean;
}

interface ExportRecord {
  id: string;
  status: string;
  template_name: string | null;
  export_key: string | null;
  created_at: string;
}

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const TOKEN = localStorage.getItem("tender_token") ?? "dev-token";
const headers = { Authorization: `Bearer ${TOKEN}` };

async function fetchGates(projectId: string): Promise<ExportGates> {
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/export-gates`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function fetchExports(projectId: string): Promise<ExportRecord[]> {
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/exports`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function GateIndicator({ passed, label, detail }: { passed: boolean; label: string; detail: string }) {
  return (
    <div className="card" style={{ padding: "12px 16px", borderColor: passed ? "#16a34a" : "#dc2626" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 18 }}>{passed ? "\u2705" : "\u274C"}</span>
        <strong>{label}</strong>
      </div>
      <p style={{ margin: "4px 0 0", fontSize: 13, color: "#64748b" }}>{detail}</p>
    </div>
  );
}

export function ExportPage({ projectId }: ExportPageProps) {
  const { data: gatesData, isLoading: gatesLoading } = useQuery({
    queryKey: ["export-gates", projectId],
    queryFn: () => fetchGates(projectId),
  });

  const { data: exports = [] } = useQuery({
    queryKey: ["exports", projectId],
    queryFn: () => fetchExports(projectId),
  });

  const gates = gatesData?.gates;

  return (
    <div className="page">
      <div className="page-header">
        <a href={`/projects/${projectId}/review`} className="back-link">&larr; 返回审校</a>
        <h1>导出</h1>
      </div>

      <h2>导出门禁检查</h2>
      {gatesLoading && <p>检查中...</p>}
      {gates && (
        <div style={{ display: "flex", gap: 12, marginBottom: 24, flexWrap: "wrap" }}>
          <GateIndicator
            passed={gates.veto_confirmed}
            label="否决项确认"
            detail={gates.veto_confirmed ? "全部已确认" : `${gates.unconfirmed_veto_count} 条未确认`}
          />
          <GateIndicator
            passed={gates.review_passed}
            label="审校通过"
            detail={gates.review_passed ? "无阻断问题" : `${gates.blocking_issue_count} 条 P0/P1 问题`}
          />
          <GateIndicator
            passed={gates.format_passed}
            label="格式校验"
            detail={gates.format_passed ? "格式合规" : "格式不合规"}
          />
        </div>
      )}

      {gatesData && (
        <button
          className="btn-primary"
          disabled={!gatesData.can_export}
          style={{ marginBottom: 32, padding: "12px 32px", fontSize: 16 }}
        >
          {gatesData.can_export ? "开始导出" : "门禁未通过，无法导出"}
        </button>
      )}

      <h2>导出历史</h2>
      {exports.length === 0 ? (
        <p className="empty">暂无导出记录</p>
      ) : (
        <table className="file-table">
          <thead>
            <tr>
              <th>状态</th>
              <th>模板</th>
              <th>导出时间</th>
            </tr>
          </thead>
          <tbody>
            {exports.map((e) => (
              <tr key={e.id}>
                <td>
                  <span className="badge" style={{
                    background: e.status === "completed" ? "#dcfce7" : "#fef2f2",
                    color: e.status === "completed" ? "#166534" : "#dc2626",
                  }}>
                    {e.status === "completed" ? "成功" : e.status}
                  </span>
                </td>
                <td>{e.template_name ?? "-"}</td>
                <td>{new Date(e.created_at).toLocaleString("zh-CN")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
