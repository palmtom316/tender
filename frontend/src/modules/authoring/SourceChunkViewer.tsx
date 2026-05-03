import { useQuery } from "@tanstack/react-query";
import { fetchSourceChunk, type SourceChunk } from "../../lib/api";
import { ClayButton } from "../../components/ui/ClayButton";
import { Badge } from "../../components/ui/Badge";

interface SourceChunkViewerProps {
  chunkId: string | null;
  onClose: () => void;
}

function renderTable(chunk: SourceChunk) {
  const rows = chunk.table_json?.rows;
  if (!rows || rows.length === 0) return null;
  const [head, ...body] = rows;
  return (
    <div className="source-viewer__table-wrap">
      <table className="source-viewer__table">
        <thead>
          <tr>{head.map((cell, index) => <th key={index}>{cell || "-"}</th>)}</tr>
        </thead>
        <tbody>
          {body.map((row, rowIndex) => (
            <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell || "-"}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SourceChunkViewer({ chunkId, onClose }: SourceChunkViewerProps) {
  const { data: chunk, isLoading, isError, error } = useQuery({
    queryKey: ["source-chunk", chunkId],
    queryFn: ({ signal }) => fetchSourceChunk(chunkId!, { signal }),
    enabled: !!chunkId,
  });

  if (!chunkId) return null;

  return (
    <div className="source-viewer" role="dialog" aria-modal="true" aria-label="原文片段">
      <button className="source-viewer__backdrop" onClick={onClose} aria-label="关闭原文片段" />
      <aside className="source-viewer__panel">
        <div className="source-viewer__header">
          <div>
            <span className="source-viewer__eyebrow">Source Chunk</span>
            <h2 className="source-viewer__title">原文对照</h2>
          </div>
          <ClayButton variant="ghost" size="sm" onClick={onClose}>关闭</ClayButton>
        </div>

        {isLoading && <div className="skeleton-stack"><div className="skeleton-card" /><div className="skeleton-line" /></div>}
        {isError && <p className="text-error">原文加载失败: {(error as Error).message}</p>}
        {chunk && (
          <div className="source-viewer__body">
            <div className="source-viewer__meta">
              <Badge variant="info">{chunk.chunk_type}</Badge>
              {chunk.page_start != null && <Badge>第 {chunk.page_start} 页</Badge>}
              {chunk.paragraph_index != null && <Badge>段落 {chunk.paragraph_index}</Badge>}
              {chunk.sheet_name && <Badge>{chunk.sheet_name}</Badge>}
            </div>
            <p className="source-viewer__file">{chunk.source_file}</p>
            <p className="source-viewer__locator">{chunk.source_locator}</p>
            {chunk.title && <h3 className="source-viewer__chunk-title">{chunk.title}</h3>}
            {chunk.chunk_type === "table" ? renderTable(chunk) : null}
            {chunk.text && <pre className="source-viewer__text">{chunk.text}</pre>}
          </div>
        )}
      </aside>
    </div>
  );
}
