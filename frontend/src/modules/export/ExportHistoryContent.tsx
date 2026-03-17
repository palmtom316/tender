import { useQuery } from "@tanstack/react-query";
import { fetchExports } from "../../lib/api";
import { useNavigation } from "../../lib/NavigationContext";
import { Badge } from "../../components/ui/Badge";

export function ExportHistoryContent() {
  const { projectId } = useNavigation();

  const { data: exports = [], isLoading } = useQuery({
    queryKey: ["exports", projectId],
    queryFn: () => fetchExports(projectId!),
    enabled: !!projectId,
  });

  if (!projectId) {
    return <p className="empty-state">请先从「投标项目」模块选择一个项目</p>;
  }

  return (
    <div>
      <h1 className="section-heading">导出历史</h1>

      {isLoading && <div className="spinner" />}

      {exports.length === 0 ? (
        <p className="empty-state">暂无导出记录</p>
      ) : (
        <table className="data-table">
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
                  <Badge variant={e.status === "completed" ? "success" : "danger"}>
                    {e.status === "completed" ? "成功" : e.status}
                  </Badge>
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
