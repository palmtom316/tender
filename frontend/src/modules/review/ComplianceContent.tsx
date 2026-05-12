import { useQuery } from "@tanstack/react-query";
import { fetchComplianceMatrix } from "../../lib/api";
import { useNavigation } from "../../lib/NavigationContext";
import { Badge } from "../../components/ui/Badge";
import { EmptyState } from "../../components/ui/EmptyState";

const COVERAGE_MAP: Record<string, { variant: "success" | "warning" | "danger"; label: string }> = {
  covered: { variant: "success", label: "已覆盖" },
  partial: { variant: "warning", label: "部分覆盖" },
  uncovered: { variant: "danger", label: "未覆盖" },
};

export function ComplianceContent() {
  const { projectId } = useNavigation();

  const { data: entries = [], isLoading } = useQuery({
    queryKey: ["compliance-matrix", projectId],
    queryFn: ({ signal }) => {
      if (!projectId) throw new Error("No project selected");
      return fetchComplianceMatrix(projectId, { signal });
    },
    enabled: !!projectId,
  });

  if (!projectId) {
    return <EmptyState icon="项" title="请先选择投标项目" description="选择项目后，可查看审校、合规或导出状态。" />;
  }

  if (isLoading) return <div className="spinner" />;
  if (entries.length === 0) return <EmptyState icon="矩" title="暂无响应矩阵数据" description="生成响应矩阵后，可在这里核对条款响应状态。" />;

  return (
    <div>
      <h1 className="section-heading">合规矩阵</h1>
      <table className="data-table">
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
            const coverage = COVERAGE_MAP[e.coverage] ?? COVERAGE_MAP.uncovered;
            return (
              <tr key={e.requirement_id}>
                <td>{e.category}</td>
                <td>{e.requirement_title}</td>
                <td>{e.chapter_code ?? "-"}</td>
                <td>
                  <Badge variant={coverage.variant}>{coverage.label}</Badge>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
