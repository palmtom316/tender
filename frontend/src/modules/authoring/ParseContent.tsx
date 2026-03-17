import { useQuery } from "@tanstack/react-query";
import { fetchParseSummary, fetchSections, fetchTables } from "../../lib/api";
import { useNavigation } from "../../lib/NavigationContext";
import { Card } from "../../components/ui/Card";

export function ParseContent() {
  const { projectId, documentId } = useNavigation();

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ["parse-summary", documentId],
    queryFn: () => fetchParseSummary(documentId!),
    enabled: !!documentId,
    refetchInterval: 5000,
  });

  const { data: sections = [] } = useQuery({
    queryKey: ["sections", documentId],
    queryFn: () => fetchSections(documentId!),
    enabled: !!summary?.parsed,
  });

  const { data: tables = [] } = useQuery({
    queryKey: ["tables", documentId],
    queryFn: () => fetchTables(documentId!),
    enabled: !!summary?.parsed,
  });

  if (!projectId) {
    return <p className="empty-state">请先从「投标项目」模块选择一个项目</p>;
  }

  if (!documentId) {
    return <p className="empty-state">请先在「文件上传」标签中上传并选择文档</p>;
  }

  return (
    <div>
      <h1 className="section-heading">解析结果</h1>

      {summaryLoading && <div className="spinner" />}

      {summary && !summary.parsed && (
        <Card>
          <p style={{ textAlign: "center", padding: "var(--space-4)" }}>
            文档正在解析中，请稍候...
          </p>
          <div className="spinner" />
        </Card>
      )}

      {summary?.parsed && (
        <div className="parse-stats">
          <Card>
            <div className="stat-card">
              <span className="stat-value">{summary.section_count}</span>
              <span className="stat-label">章节</span>
            </div>
          </Card>
          <Card>
            <div className="stat-card">
              <span className="stat-value">{summary.table_count}</span>
              <span className="stat-label">表格</span>
            </div>
          </Card>
        </div>
      )}

      {sections.length > 0 && (
        <>
          <h2 className="section-heading" style={{ fontSize: "var(--text-lg)" }}>文档结构</h2>
          <div className="section-tree">
            {sections.map((s) => (
              <div
                key={s.id}
                className="section-node"
                style={{ paddingLeft: `${(s.level - 1) * 24}px` }}
              >
                <span className="section-code">{s.section_code ?? ""}</span>
                <span className="section-title">{s.title}</span>
                {s.page_start != null && (
                  <span className="section-page">P{s.page_start}</span>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {tables.length > 0 && (
        <>
          <h2 className="section-heading" style={{ fontSize: "var(--text-lg)" }}>表格列表</h2>
          <div className="table-list">
            {tables.map((t, idx) => (
              <Card key={t.id}>
                <div className="flex items-center justify-between">
                  <span style={{ fontWeight: 600 }}>表 {idx + 1}</span>
                  {t.page != null && (
                    <span style={{ color: "var(--color-text-muted)", fontSize: "var(--text-sm)" }}>
                      第 {t.page} 页
                    </span>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
