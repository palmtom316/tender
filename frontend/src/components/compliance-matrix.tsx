import { useQuery } from "@tanstack/react-query";

interface ComplianceMatrixProps {
  projectId: string;
}

interface ComplianceEntry {
  requirement_id: string;
  requirement_title: string;
  category: string;
  chapter_code: string | null;
  coverage: string;
}

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const TOKEN = localStorage.getItem("tender_token") ?? "dev-token";
const headers = { Authorization: `Bearer ${TOKEN}` };

const COVERAGE_STYLES: Record<string, { bg: string; color: string; label: string }> = {
  covered: { bg: "#dcfce7", color: "#166534", label: "已覆盖" },
  partial: { bg: "#fef9c3", color: "#854d0e", label: "部分覆盖" },
  uncovered: { bg: "#fef2f2", color: "#dc2626", label: "未覆盖" },
};

async function fetchMatrix(projectId: string): Promise<ComplianceEntry[]> {
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/compliance-matrix`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function ComplianceMatrix({ projectId }: ComplianceMatrixProps) {
  const { data: entries = [], isLoading } = useQuery({
    queryKey: ["compliance-matrix", projectId],
    queryFn: () => fetchMatrix(projectId),
  });

  if (isLoading) return <p>加载中...</p>;
  if (entries.length === 0) return <p className="empty">暂无响应矩阵数据</p>;

  return (
    <table className="file-table">
      <thead>
        <tr>
          <th>类别</th>
          <th>招标要求</th>
          <th>对应章节</th>
          <th>覆盖状态</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((e) => {
          const style = COVERAGE_STYLES[e.coverage] ?? COVERAGE_STYLES.uncovered;
          return (
            <tr key={e.requirement_id}>
              <td>{e.category}</td>
              <td>{e.requirement_title}</td>
              <td>{e.chapter_code ?? "-"}</td>
              <td>
                <span className="badge" style={{ background: style.bg, color: style.color }}>
                  {style.label}
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
