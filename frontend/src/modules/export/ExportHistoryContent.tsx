import { useQuery } from "@tanstack/react-query";
import { deliveryPackageDownloadUrl, fetchDeliveryPackages, fetchExports } from "../../lib/api";
import { useNavigation } from "../../lib/NavigationContext";
import { Badge } from "../../components/ui/Badge";
import { EmptyState } from "../../components/ui/EmptyState";

export function ExportHistoryContent() {
  const { projectId } = useNavigation();

  const { data: exports = [], isLoading } = useQuery({
    queryKey: ["exports", projectId],
    queryFn: ({ signal }) => {
      if (!projectId) throw new Error("No project selected");
      return fetchExports(projectId, { signal });
    },
    enabled: !!projectId,
  });

  const { data: packages = [] } = useQuery({
    queryKey: ["delivery-packages", projectId],
    queryFn: ({ signal }) => {
      if (!projectId) throw new Error("No project selected");
      return fetchDeliveryPackages(projectId, { signal });
    },
    enabled: !!projectId,
  });

  if (!projectId) {
    return <EmptyState icon="项" title="请先选择投标项目" description="选择项目后，可查看审校、合规或导出状态。" />;
  }

  return (
    <div>
      <h1 className="section-heading">导出历史</h1>
      <h2 className="subsection-heading">交付包</h2>
      {packages.length === 0 ? (
        <EmptyState icon="包" title="暂无交付包" description="满足导出门禁后，可生成投标交付包。" />
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>版本</th>
              <th>文件名</th>
              <th>生成时间</th>
              <th>下载</th>
            </tr>
          </thead>
          <tbody>
            {packages.map((item) => (
              <tr key={item.id}>
                <td>v{item.version_no}</td>
                <td>{item.package_name}</td>
                <td>{new Date(item.created_at).toLocaleString("zh-CN")}</td>
                <td><a href={deliveryPackageDownloadUrl(item.id)}>下载</a></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {isLoading && <div className="spinner" />}

      {exports.length === 0 ? (
        <EmptyState icon="导" title="暂无导出记录" description="导出完成后会在这里保留历史记录。" />
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
