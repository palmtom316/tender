import { useCallback, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchTenderDocumentParseStatus,
  listTenderDocuments,
  parseTenderDocument,
  uploadTenderDocument,
  type TenderDocument,
} from "../../lib/api";
import { useNavigation } from "../../lib/NavigationContext";
import { ClayButton } from "../../components/ui/ClayButton";
import { Badge } from "../../components/ui/Badge";
import { Card } from "../../components/ui/Card";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function statusTone(status: string | undefined): "info" | "success" | "warning" | "danger" | "default" {
  switch (status) {
    case "completed":
      return "success";
    case "extracting":
    case "parsing":
      return "info";
    case "failed":
      return "danger";
    case "uploaded":
    case "pending":
      return "warning";
    default:
      return "default";
  }
}

function statusLabel(status: string | undefined) {
  if (!status) return "未开始";
  return status;
}

export function UploadContent() {
  const { projectId, documentId, setDocumentId } = useNavigation();
  const queryClient = useQueryClient();
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const { data: documents = [], isLoading } = useQuery({
    queryKey: ["tender-documents", projectId],
    queryFn: ({ signal }) => {
      if (!projectId) throw new Error("No project selected");
      return listTenderDocuments(projectId, { signal });
    },
    enabled: !!projectId,
  });

  const { data: parseStatus } = useQuery({
    queryKey: ["tender-document-parse-status", documentId],
    queryFn: ({ signal }) => {
      if (!documentId) throw new Error("No tender document selected");
      return fetchTenderDocumentParseStatus(documentId, { signal });
    },
    enabled: !!documentId,
    refetchInterval: (query) => {
      const status = query.state.data?.document_status;
      return status === "completed" || status === "failed" ? false : 5000;
    },
  });

  const parse = useMutation({
    mutationFn: (tenderDocumentId: string) => parseTenderDocument(tenderDocumentId),
    onSuccess: (_, tenderDocumentId) => {
      queryClient.invalidateQueries({ queryKey: ["tender-document-parse-status", tenderDocumentId] });
      queryClient.invalidateQueries({ queryKey: ["tender-source-chunks", tenderDocumentId] });
      queryClient.invalidateQueries({ queryKey: ["requirements", projectId] });
      queryClient.invalidateQueries({ queryKey: ["tender-summary", projectId] });
    },
  });

  const upload = useMutation({
    mutationFn: (file: File) => {
      if (!projectId) throw new Error("No project selected");
      return uploadTenderDocument(projectId, file);
    },
    onSuccess: async (document) => {
      queryClient.invalidateQueries({ queryKey: ["tender-documents", projectId] });
      setDocumentId(document.id);
      await parse.mutateAsync(document.id);
    },
  });

  const handleFiles = useCallback(
    (fileList: FileList | null) => {
      if (!fileList) return;
      Array.from(fileList).forEach((f) => upload.mutate(f));
    },
    [upload],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles],
  );

  if (!projectId) {
    return (
      <div className="empty-state">
        <span className="empty-state__icon">项</span>
        <p className="empty-state__title">先选择投标项目</p>
        <p className="empty-state__description">选择项目后，可上传 ZIP 招标文件包或单个 PDF，并启动解析。</p>
      </div>
    );
  }

  return (
    <div className="document-upload-workbench">
      <div className="document-upload-workbench__hero">
        <div className="document-upload-workbench__hero-copy">
          <span className="tender-summary-card__eyebrow">Tender Source Desk</span>
          <h1 className="section-heading">招标文档上传与解析</h1>
          <p className="document-upload-workbench__lead">
            选择当前工作文档、监控解析状态，并集中管理已上传的招标原件。
          </p>
        </div>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept=".zip,.pdf,application/zip,application/pdf"
        aria-label="上传招标文件"
        className="visually-hidden"
        onChange={(event) => handleFiles(event.target.files)}
      />

      <section className="document-upload-workbench__top">
        <Card className="document-upload-panel document-upload-panel--drop">
          <div
            className={`drop-zone drop-zone--embedded ${dragging ? "drop-zone--active" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
          >
            <div className="document-upload-panel__drop-copy">
              <span className="document-upload-panel__drop-tag">上传入口</span>
              <p className="drop-zone-text">
                {upload.isPending ? "上传并启动解析中..." : "拖拽文件到此处，或点击选择 ZIP / PDF"}
              </p>
              <p className="drop-zone-hint">支持 ZIP 招标文件包，或单个 PDF 招标文件</p>
            </div>
          </div>
        </Card>

        <Card className="document-upload-panel document-upload-panel--status">
          <div className="document-upload-panel__header">
            <div>
              <span className="document-upload-panel__eyebrow">当前文档</span>
              <h2>解析概览</h2>
            </div>
            {documentId && (
              <ClayButton
                variant="outline"
                size="sm"
                onClick={() => parse.mutate(documentId)}
                disabled={parse.isPending}
              >
                {parse.isPending ? "重新解析中..." : "重新解析"}
              </ClayButton>
            )}
          </div>

          {documents.length > 0 ? (
            <div className="document-upload-panel__selector">
              <label className="form-label" htmlFor="current-tender-document">当前招标文档</label>
              <select
                id="current-tender-document"
                className="clay-input"
                aria-label="选择招标文档"
                value={documentId ?? ""}
                onChange={(event) => setDocumentId(event.target.value || null)}
              >
                <option value="">选择一个已上传的招标文档</option>
                {documents.map((document) => (
                  <option key={document.id} value={document.id}>
                    {document.original_filename}
                  </option>
                ))}
              </select>
            </div>
          ) : null}

          {documentId && parseStatus ? (
            <>
              <div className="document-upload-panel__status-row">
                <div className="document-upload-panel__status-copy">
                  <span className="document-upload-panel__status-label">当前状态</span>
                  <strong>{statusLabel(parseStatus.document_status)}</strong>
                </div>
                <Badge variant={statusTone(parseStatus.document_status)}>{statusLabel(parseStatus.document_status)}</Badge>
              </div>
              <div className="parse-summary parse-summary--workbench">
                <div className="card parse-summary__item">
                  <span className="parse-summary__label">已解析文件</span>
                  <strong className="parse-summary__value">{parseStatus.completed_file_count}</strong>
                </div>
                <div className="card parse-summary__item">
                  <span className="parse-summary__label">解析中</span>
                  <strong className="parse-summary__value">{parseStatus.parsing_file_count}</strong>
                </div>
                <div className="card parse-summary__item">
                  <span className="parse-summary__label">待处理</span>
                  <strong className="parse-summary__value">{parseStatus.pending_file_count}</strong>
                </div>
                <div className="card parse-summary__item">
                  <span className="parse-summary__label">片段数</span>
                  <strong className="parse-summary__value">{parseStatus.chunk_count}</strong>
                </div>
              </div>
            </>
          ) : (
            <div className="document-upload-panel__empty">
              <p className="empty-state__title">还没有选定当前文档</p>
              <p className="empty-state__description">上传后可在这里查看解析状态、文件数和片段数。</p>
            </div>
          )}
        </Card>
      </section>

      {upload.isError && (
        <p className="text-error">上传失败: {(upload.error as Error).message}</p>
      )}
      {parse.isError && (
        <p className="text-error">解析启动失败: {(parse.error as Error).message}</p>
      )}

      <section className="document-upload-ledger">
        <div className="document-upload-ledger__header">
          <div>
            <span className="document-upload-panel__eyebrow">文档台账</span>
            <h2 className="section-heading section-heading--sm">已上传招标文档</h2>
          </div>
          <span className="document-upload-ledger__count">{documents.length} 份</span>
        </div>

        {isLoading ? (
          <div className="skeleton-stack" aria-label="文件列表加载中">
            <div className="skeleton-card" />
            <div className="skeleton-card" />
          </div>
        ) : documents.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__icon">文</span>
            <p className="empty-state__title">还没有上传招标文档</p>
            <p className="empty-state__description">上传 ZIP 招标文件包或单个 PDF 后，会在这里列出；完成解析后可再手动提交 AI 抽取。</p>
          </div>
        ) : (
          <div className="document-upload-ledger__table-wrap">
            <table className="data-table document-upload-ledger__table">
              <thead>
                <tr>
                  <th>文件名</th>
                  <th>类型</th>
                  <th>大小</th>
                  <th>上传方式</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((document: TenderDocument) => (
                  <tr
                    key={document.id}
                    onClick={() => setDocumentId(document.id)}
                    aria-selected={document.id === documentId}
                    className={document.id === documentId ? "is-selected-row" : ""}
                  >
                    <td className="document-upload-ledger__filename">{document.original_filename}</td>
                    <td>{document.content_type}</td>
                    <td>{formatBytes(document.size_bytes)}</td>
                    <td>{document.upload_type.toUpperCase()}</td>
                    <td>
                      <Badge variant={statusTone(document.status)}>{statusLabel(document.status)}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
