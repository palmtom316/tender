import { useQuery } from "@tanstack/react-query";
import { fetchTenderDocumentParseStatus, fetchTenderSourceChunks, type SourceChunk } from "../../lib/api";
import { useNavigation } from "../../lib/NavigationContext";
import { Card } from "../../components/ui/Card";

type ReadableSection = {
  id: string;
  heading: SourceChunk | null;
  paragraphs: SourceChunk[];
};

function chunkLabel(chunk: SourceChunk): string {
  return chunk.title ?? chunk.section_title ?? chunk.text ?? chunk.source_locator;
}

function buildReadableSections(chunks: SourceChunk[]): ReadableSection[] {
  const sections: ReadableSection[] = [];
  let currentSection: ReadableSection | null = null;

  for (const chunk of chunks.filter((item) => item.chunk_type !== "table")) {
    if (chunk.chunk_type === "heading") {
      currentSection = {
        id: chunk.id,
        heading: chunk,
        paragraphs: [],
      };
      sections.push(currentSection);
      continue;
    }

    if (!currentSection) {
      currentSection = {
        id: `intro-${chunk.id}`,
        heading: null,
        paragraphs: [],
      };
      sections.push(currentSection);
    }

    currentSection.paragraphs.push(chunk);
  }

  return sections;
}

export function ParseContent() {
  const { projectId, documentId } = useNavigation();

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ["tender-document-parse-status", documentId],
    queryFn: ({ signal }) => fetchTenderDocumentParseStatus(documentId!, { signal }),
    enabled: !!documentId,
    refetchInterval: 5000,
  });

  const { data: chunks = [] } = useQuery({
    queryKey: ["tender-source-chunks", documentId],
    queryFn: ({ signal }) => fetchTenderSourceChunks(documentId!, { signal }),
    enabled: !!documentId && summary?.chunk_count !== 0,
  });

  const readableSections = buildReadableSections(chunks);

  if (!projectId) {
    return (
      <div className="empty-state">
        <span className="empty-state__icon">项</span>
        <p className="empty-state__title">先选择投标项目</p>
        <p className="empty-state__description">选择项目后，可查看已上传招标文档的解析结果。</p>
      </div>
    );
  }

  if (!documentId) {
    return (
      <div className="empty-state">
        <span className="empty-state__icon">文</span>
        <p className="empty-state__title">先上传并选择文档</p>
        <p className="empty-state__description">在「文件上传」标签上传 ZIP 文件包或 PDF 后，可在这里查看结构化解析结果。</p>
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

      {summary && summary.chunk_count === 0 && (
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

      {summary && summary.chunk_count > 0 && (
        <div className="parse-summary">
          <Card className="parse-summary__item">
            <span className="parse-summary__label">已解析文件</span>
            <strong className="parse-summary__value">{summary.completed_file_count}</strong>
          </Card>
          <Card className="parse-summary__item">
            <span className="parse-summary__label">片段</span>
            <strong className="parse-summary__value">{summary.chunk_count}</strong>
          </Card>
        </div>
      )}

      {readableSections.length > 0 && (
        <>
          <h2 className="section-heading section-heading--sm">文档结构</h2>
          <div className="readable-structure">
            {readableSections.map((section, index) => (
              <Card key={section.id} className="readable-section">
                <div className="readable-section__header">
                  <div className="readable-section__eyebrow">
                    {section.heading ? "章节" : "导读"}
                  </div>
                  <div className="readable-section__meta">
                    {section.heading?.page_start != null ? `P${section.heading.page_start}` : `#${index + 1}`}
                  </div>
                </div>
                <h3 className="readable-section__title">
                  {section.heading ? chunkLabel(section.heading) : "文档引言"}
                </h3>
                {section.paragraphs.length > 0 ? (
                  <div className="readable-section__body">
                    {section.paragraphs.map((paragraph) => (
                      <p key={paragraph.id} className="readable-section__paragraph">
                        {paragraph.text ?? chunkLabel(paragraph)}
                      </p>
                    ))}
                  </div>
                ) : (
                  <p className="readable-section__placeholder">该章节当前只有标题，未抽取到正文段落。</p>
                )}
              </Card>
            ))}
          </div>
        </>
      )}

      {chunks.filter((chunk) => chunk.chunk_type === "table").length > 0 && (
        <>
          <h2 className="section-heading section-heading--sm">表格列表</h2>
          <div className="table-list">
            {chunks
              .filter((chunk) => chunk.chunk_type === "table")
              .map((t, idx) => (
              <Card key={t.id}>
                <div className="flex items-center justify-between">
                  <span className="table-list__header">{t.title || `表 ${idx + 1}`}</span>
                  {t.page_start != null && (
                    <span className="table-list__page">
                      第 {t.page_start} 页
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
