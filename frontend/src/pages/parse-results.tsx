import { useQuery } from "@tanstack/react-query";

interface ParseResultsPageProps {
  projectId: string;
  documentId: string;
}

interface Section {
  id: string;
  section_code: string | null;
  title: string;
  level: number;
  page_start: number | null;
  page_end: number | null;
  text: string | null;
}

interface Table {
  id: string;
  page: number | null;
  raw_json: unknown;
}

interface ParseSummary {
  document_id: string;
  parsed: boolean;
  section_count: number;
  table_count: number;
  latest_parse_job_id: string | null;
}

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

async function fetchParseSummary(documentId: string): Promise<ParseSummary> {
  const res = await fetch(`${BASE_URL}/api/documents/${documentId}/parse-result`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function fetchSections(documentId: string): Promise<Section[]> {
  const res = await fetch(`${BASE_URL}/api/documents/${documentId}/sections`);
  if (!res.ok) return [];
  return res.json();
}

async function fetchTables(documentId: string): Promise<Table[]> {
  const res = await fetch(`${BASE_URL}/api/documents/${documentId}/tables`);
  if (!res.ok) return [];
  return res.json();
}

export function ParseResultsPage({ projectId, documentId }: ParseResultsPageProps) {
  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ["parse-summary", documentId],
    queryFn: () => fetchParseSummary(documentId),
    refetchInterval: 5000,
  });

  const { data: sections = [] } = useQuery({
    queryKey: ["sections", documentId],
    queryFn: () => fetchSections(documentId),
    enabled: !!summary?.parsed,
  });

  const { data: tables = [] } = useQuery({
    queryKey: ["tables", documentId],
    queryFn: () => fetchTables(documentId),
    enabled: !!summary?.parsed,
  });

  return (
    <div className="page">
      <div className="page-header">
        <a href={`/projects/${projectId}/upload`} className="back-link">
          &larr; 返回上传页
        </a>
        <h1>解析结果</h1>
      </div>

      {summaryLoading && <p>加载中...</p>}

      {summary && !summary.parsed && (
        <div className="card parse-status">
          <p>文档正在解析中，请稍候...</p>
          <div className="spinner" />
        </div>
      )}

      {summary?.parsed && (
        <div className="parse-stats">
          <div className="card stat-card">
            <span className="stat-value">{summary.section_count}</span>
            <span className="stat-label">章节</span>
          </div>
          <div className="card stat-card">
            <span className="stat-value">{summary.table_count}</span>
            <span className="stat-label">表格</span>
          </div>
        </div>
      )}

      {sections.length > 0 && (
        <>
          <h2>文档结构</h2>
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
          <h2>表格列表</h2>
          <div className="table-list">
            {tables.map((t, idx) => (
              <div key={t.id} className="card table-card">
                <span className="table-index">表 {idx + 1}</span>
                {t.page != null && <span className="table-page">第 {t.page} 页</span>}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
