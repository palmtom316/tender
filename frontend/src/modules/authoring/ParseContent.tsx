import { useQuery } from "@tanstack/react-query";
import type { CSSProperties } from "react";
import { fetchParseSummary, fetchSections, fetchTables } from "../../lib/api";
import { useNavigation } from "../../lib/NavigationContext";
import { Card } from "../../components/ui/Card";

type SectionNodeStyle = CSSProperties & {
  "--section-depth-indent": string;
};

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
    return (
      <div className="empty-state">
        <span className="empty-state__icon">项</span>
        <p className="empty-state__title">先选择投标项目</p>
        <p className="empty-state__description">选择项目后，可查看招标文件解析结果。</p>
      </div>
    );
  }

  if (!documentId) {
    return (
      <div className="empty-state">
        <span className="empty-state__icon">文</span>
        <p className="empty-state__title">先上传并选择文档</p>
        <p className="empty-state__description">在「文件上传」标签上传招标文件后，可在这里查看章节和表格解析结果。</p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="section-heading">解析结果</h1>

      {summaryLoading && (
        <div className="skeleton-stack" aria-label="解析摘要加载中">
          <div className="skeleton-card" />
          <div className="skeleton-line" />
        </div>
      )}

      {summary && !summary.parsed && (
        <Card>
          <p className="parse-status">
            文档正在解析中，请稍候...
          </p>
          <div className="skeleton-stack" aria-label="文档解析中">
            <div className="skeleton-line" />
            <div className="skeleton-line" />
          </div>
        </Card>
      )}

      {summary?.parsed && (
        <div className="parse-summary">
          <Card className="parse-summary__item">
            <span className="parse-summary__label">章节</span>
            <strong className="parse-summary__value">{summary.section_count}</strong>
          </Card>
          <Card className="parse-summary__item">
            <span className="parse-summary__label">表格</span>
            <strong className="parse-summary__value">{summary.table_count}</strong>
          </Card>
        </div>
      )}

      {sections.length > 0 && (
        <>
          <h2 className="section-heading section-heading--sm">文档结构</h2>
          <div className="section-tree">
            {sections.map((s) => (
              <div
                key={s.id}
                className="section-node"
                style={{ "--section-depth-indent": `${(s.level - 1) * 24}px` } as SectionNodeStyle}
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
          <h2 className="section-heading section-heading--sm">表格列表</h2>
          <div className="table-list">
            {tables.map((t, idx) => (
              <Card key={t.id}>
                <div className="flex items-center justify-between">
                  <span className="table-list__header">表 {idx + 1}</span>
                  {t.page != null && (
                    <span className="table-list__page">
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
