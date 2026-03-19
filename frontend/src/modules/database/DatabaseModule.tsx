import { useCallback, useEffect, useRef, useState } from "react";

import { Badge } from "../../components/ui/Badge";
import { Card } from "../../components/ui/Card";
import { ClayButton } from "../../components/ui/ClayButton";
import { Icon } from "../../components/ui/Icon";
import { useNavigation } from "../../lib/NavigationContext";
import type {
  BatchStandardUploadItem,
  Standard,
  StandardClauseNode,
  StandardDetail,
} from "../../lib/api";
import {
  fetchStandardDetail,
  listStandards,
  triggerStandardProcessing,
  uploadStandards,
} from "../../lib/api";

const TAB_DESCRIPTIONS: Record<string, string> = {
  history: "管理历史投标文件，支持按项目类型和时间筛选",
  excellent: "收集和标注优秀投标文件，供编制参考",
  company: "公司资质证书、业绩证明等企业资料",
  personnel: "项目团队成员简历、资质证书等",
};

type UploadRow = {
  id: string;
  file: File;
  standard_code: string;
  standard_name: string;
  version_year: string;
  specialty: string;
};

function statusVariant(
  status: string,
): "default" | "primary" | "success" | "warning" | "danger" {
  switch (status) {
    case "completed":
      return "success";
    case "parsing":
    case "processing":
      return "primary";
    case "queued_ocr":
    case "queued_ai":
    case "pending":
      return "warning";
    case "failed":
      return "danger";
    default:
      return "default";
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case "queued_ocr":
      return "OCR排队中";
    case "parsing":
      return "OCR处理中";
    case "queued_ai":
      return "AI排队中";
    case "processing":
      return "AI处理中";
    case "completed":
      return "已完成";
    case "failed":
      return "失败";
    case "pending":
      return "待处理";
    default:
      return status;
  }
}

function isActiveStatus(status: string): boolean {
  return ["queued_ocr", "parsing", "queued_ai", "processing"].includes(status);
}

function stageHint(std: Pick<Standard, "processing_status" | "ocr_status" | "ai_status">): string | null {
  switch (std.processing_status) {
    case "queued_ocr":
      return "等待 OCR 队列";
    case "parsing":
      return "正在执行 OCR";
    case "queued_ai":
      return "OCR 完成，等待 AI 解析";
    case "processing":
      return "正在执行 AI 条款解析";
    case "failed":
      if (std.ai_status === "failed") return "AI 解析失败，可重新入队";
      if (std.ocr_status === "failed") return "OCR 失败，可重新入队";
      return "处理失败，可重新入队";
    default:
      return null;
  }
}

function buildUploadRows(files: FileList | null, existingRows: UploadRow[]): { rows: UploadRow[]; error: string } {
  if (!files || files.length === 0) {
    return { rows: existingRows, error: "" };
  }

  const existingNames = new Set(existingRows.map((row) => row.file.name));
  const nextRows = [...existingRows];
  const duplicates: string[] = [];

  for (const file of Array.from(files)) {
    if (existingNames.has(file.name)) {
      duplicates.push(file.name);
      continue;
    }
    existingNames.add(file.name);
    nextRows.push({
      id: `${file.name}-${file.size}-${file.lastModified}`,
      file,
      standard_code: "",
      standard_name: "",
      version_year: "",
      specialty: "",
    });
  }

  return {
    rows: nextRows,
    error: duplicates.length > 0 ? `已忽略重复文件：${duplicates.join("、")}` : "",
  };
}

function UploadForm({ onUploaded }: { onUploaded: () => void }) {
  const [rows, setRows] = useState<UploadRow[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [fileInputKey, setFileInputKey] = useState(0);

  const handleFilesSelected = (event: React.ChangeEvent<HTMLInputElement>) => {
    const result = buildUploadRows(event.target.files, rows);
    setRows(result.rows);
    setError(result.error);
  };

  const updateRow = (id: string, field: keyof Omit<UploadRow, "id" | "file">, value: string) => {
    setRows((current) => current.map((row) => (
      row.id === id ? { ...row, [field]: value } : row
    )));
  };

  const removeRow = (id: string) => {
    setRows((current) => current.filter((row) => row.id !== id));
  };

  const canSubmit = rows.length > 0 && rows.every((row) => row.standard_code.trim() && row.standard_name.trim());

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;

    setUploading(true);
    setError("");
    try {
      const payload: BatchStandardUploadItem[] = rows.map((row) => ({
        file: row.file,
        standard_code: row.standard_code.trim(),
        standard_name: row.standard_name.trim(),
        version_year: row.version_year.trim() || undefined,
        specialty: row.specialty.trim() || undefined,
      }));
      await uploadStandards(payload);
      setRows([]);
      setFileInputKey((value) => value + 1);
      onUploaded();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "上传失败");
    } finally {
      setUploading(false);
    }
  };

  return (
    <Card>
      <form onSubmit={handleSubmit}>
        <div className="standard-upload-header">
          <div>
            <h3 style={{ marginBottom: "var(--space-1)", fontWeight: 600 }}>
              <Icon name="upload-cloud" size={18} /> 批量上传规范文件
            </h3>
            <p className="standard-upload-subtitle">一次可选多个 PDF，提交前必须逐条填写规范编号和规范名称。</p>
          </div>
          <label className="standard-upload-picker">
            <input
              key={fileInputKey}
              type="file"
              accept=".pdf"
              multiple
              onChange={handleFilesSelected}
            />
            <span>选择 PDF 文件</span>
          </label>
        </div>

        {rows.length > 0 ? (
          <div className="standard-upload-table">
            <div className="standard-upload-table__header">
              <span>文件名</span>
              <span>规范编号 *</span>
              <span>规范名称 *</span>
              <span>版本年份</span>
              <span>专业类别</span>
              <span>操作</span>
            </div>
            {rows.map((row) => (
              <div className="standard-upload-row" key={row.id}>
                <div className="standard-upload-file">
                  <strong>{row.file.name}</strong>
                  <span>{Math.max(1, Math.round(row.file.size / 1024))} KB</span>
                </div>
                <input
                  className="clay-input"
                  value={row.standard_code}
                  onChange={(event) => updateRow(row.id, "standard_code", event.target.value)}
                  placeholder="如 GB 50010-2010"
                />
                <input
                  className="clay-input"
                  value={row.standard_name}
                  onChange={(event) => updateRow(row.id, "standard_name", event.target.value)}
                  placeholder="如 混凝土结构设计规范"
                />
                <input
                  className="clay-input"
                  value={row.version_year}
                  onChange={(event) => updateRow(row.id, "version_year", event.target.value)}
                  placeholder="如 2010"
                />
                <input
                  className="clay-input"
                  value={row.specialty}
                  onChange={(event) => updateRow(row.id, "specialty", event.target.value)}
                  placeholder="如 结构"
                />
                <ClayButton type="button" variant="ghost" size="sm" onClick={() => removeRow(row.id)}>
                  移除
                </ClayButton>
              </div>
            ))}
          </div>
        ) : (
          <div className="standard-upload-empty">
            <Icon name="book" size={20} />
            <span>尚未选择文件</span>
          </div>
        )}

        {error && <p className="text-error" style={{ marginBottom: "var(--space-2)" }}>{error}</p>}

        <div className="standard-upload-actions">
          <ClayButton type="submit" disabled={!canSubmit || uploading}>
            {uploading ? "上传并入队中..." : "上传并自动入队"}
          </ClayButton>
          <span className="standard-upload-tip">上传后将自动进入 OCR/AI 流水线，不再需要手动开始处理。</span>
        </div>
      </form>
    </Card>
  );
}

function StandardCard({
  std,
  onClick,
  onRetry,
}: {
  std: Standard;
  onClick: () => void;
  onRetry: () => void;
}) {
  const hint = stageHint(std);
  const active = isActiveStatus(std.processing_status);

  return (
    <Card style={{ cursor: "pointer" }} onClick={onClick}>
      <div className="standard-card-header">
        <span className="standard-card-code">{std.standard_code}</span>
        <Badge variant={statusVariant(std.processing_status)}>
          {statusLabel(std.processing_status)}
        </Badge>
      </div>
      <div className="standard-card-name">{std.standard_name}</div>
      <div className="standard-card-meta">
        {std.version_year && <span>{std.version_year}</span>}
        {std.specialty && <span>{std.specialty}</span>}
        <span>{std.clause_count} 条款</span>
      </div>
      {hint && <div className="standard-stage-hint">{hint}</div>}
      {active && (
        <div className="flex items-center gap-2" style={{ marginTop: "var(--space-3)" }}>
          <div className="spinner spinner--sm" />
          <span style={{ fontSize: "var(--text-sm)", color: "var(--color-text-muted)" }}>
            队列正在推进...
          </span>
        </div>
      )}
      {std.processing_status === "failed" && (
        <div style={{ marginTop: "var(--space-3)" }}>
          <ClayButton
            size="sm"
            variant="secondary"
            onClick={(event) => {
              event.stopPropagation();
              onRetry();
            }}
          >
            <Icon name="refresh" size={14} /> 重新入队
          </ClayButton>
        </div>
      )}
    </Card>
  );
}

function ClauseTreeNode({
  node,
  depth,
}: {
  node: StandardClauseNode;
  depth: number;
}) {
  const [expanded, setExpanded] = useState(depth < 2);
  const hasChildren = node.children && node.children.length > 0;
  const isCommentary = node.clause_type === "commentary";

  return (
    <div className={`clause-node ${depth === 0 ? "clause-node--root" : ""} ${isCommentary ? "clause-commentary" : ""}`}>
      <div className="clause-node-header" onClick={() => setExpanded(!expanded)}>
        {hasChildren ? (
          <Icon name={expanded ? "chevron-down" : "chevron-right"} size={16} />
        ) : (
          <span style={{ width: 16, display: "inline-block" }} />
        )}
        {node.clause_no && <span className="clause-node-no">{node.clause_no}</span>}
        <span className="clause-node-title">
          {node.clause_title || (node.clause_text?.slice(0, 60) ?? "")}
          {isCommentary && <span style={{ fontSize: "var(--text-xs)", marginLeft: "var(--space-1)", color: "var(--color-info)" }}>[说明]</span>}
        </span>
        {node.page_start != null && (
          <Badge variant="default" className="clause-node-page">
            P{node.page_start}
          </Badge>
        )}
      </div>

      {expanded && (
        <>
          <div className="clause-detail">
            {node.clause_text && <div className="clause-detail-text">{node.clause_text}</div>}
            {node.summary && <div className="clause-detail-summary">{node.summary}</div>}
            {node.tags && node.tags.length > 0 && (
              <div className="clause-tags">
                {node.tags.map((tag, index) => (
                  <Badge key={index} variant="info">{tag}</Badge>
                ))}
              </div>
            )}
          </div>

          {hasChildren && node.children.map((child) => (
            <ClauseTreeNode key={child.id} node={child} depth={depth + 1} />
          ))}
        </>
      )}
    </div>
  );
}

function StandardDetailView({
  standardId,
  onBack,
}: {
  standardId: string;
  onBack: () => void;
}) {
  const [detail, setDetail] = useState<StandardDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadDetail = useCallback(() => {
    setLoading(true);
    fetchStandardDetail(standardId)
      .then((data) => {
        setDetail(data);
        setError("");
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "加载失败"))
      .finally(() => setLoading(false));
  }, [standardId]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  useEffect(() => {
    if (!detail || !isActiveStatus(detail.processing_status)) return undefined;
    const interval = window.setInterval(loadDetail, 5000);
    return () => window.clearInterval(interval);
  }, [detail, loadDetail]);

  if (loading && !detail) {
    return (
      <div className="empty-state">
        <div className="spinner" />
        <p>加载中...</p>
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div>
        <ClayButton variant="secondary" size="sm" onClick={onBack}>
          <Icon name="arrow-left" size={16} /> 返回列表
        </ClayButton>
        <p className="text-error" style={{ marginTop: "var(--space-3)" }}>
          {error || "未找到规范"}
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center gap-3" style={{ marginBottom: "var(--space-4)" }}>
        <ClayButton variant="secondary" size="sm" onClick={onBack}>
          <Icon name="arrow-left" size={16} /> 返回
        </ClayButton>
        <div style={{ flex: 1 }}>
          <h2 style={{ fontSize: "var(--text-lg)", fontWeight: 600 }}>
            {detail.standard_code} {detail.standard_name}
          </h2>
          <div className="flex gap-3" style={{ fontSize: "var(--text-sm)", color: "var(--color-text-muted)" }}>
            {detail.version_year && <span>{detail.version_year}版</span>}
            {detail.specialty && <span>{detail.specialty}</span>}
            <span>{detail.clause_count} 条款</span>
          </div>
        </div>
        <Badge variant={statusVariant(detail.processing_status)}>
          {statusLabel(detail.processing_status)}
        </Badge>
      </div>

      {detail.error_message && (
        <div className="warning-banner" style={{ marginBottom: "var(--space-4)" }}>
          {detail.error_message}
        </div>
      )}

      {detail.clause_tree && detail.clause_tree.length > 0 ? (
        <Card>
          <div className="clause-tree">
            {detail.clause_tree.map((node) => (
              <ClauseTreeNode key={node.id} node={node} depth={0} />
            ))}
          </div>
        </Card>
      ) : (
        <Card>
          <div className="empty-state">
            <Icon name="book" size={32} />
            <p style={{ marginTop: "var(--space-2)" }}>
              {detail.processing_status === "completed"
                ? "未提取到条款"
                : "当前文件正在排队或处理中，完成后会在这里显示条款。"}
            </p>
          </div>
        </Card>
      )}
    </div>
  );
}

function StandardsContent() {
  const [standards, setStandards] = useState<Standard[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [processError, setProcessError] = useState("");
  const pollingRef = useRef<number | null>(null);

  const loadStandards = useCallback(() => {
    listStandards()
      .then(setStandards)
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadStandards();
  }, [loadStandards]);

  useEffect(() => {
    const shouldPoll = standards.some((std) => isActiveStatus(std.processing_status));
    if (!shouldPoll) return undefined;

    pollingRef.current = window.setInterval(() => {
      listStandards().then(setStandards).catch(() => undefined);
    }, 5000);

    return () => {
      if (pollingRef.current !== null) {
        window.clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [standards]);

  const handleRetry = async (id: string) => {
    setProcessError("");
    try {
      await triggerStandardProcessing(id);
      loadStandards();
    } catch (err: unknown) {
      setProcessError(err instanceof Error ? err.message : "重新入队失败");
    }
  };

  if (selectedId) {
    return (
      <StandardDetailView
        standardId={selectedId}
        onBack={() => {
          setSelectedId(null);
          loadStandards();
        }}
      />
    );
  }

  return (
    <div>
      <UploadForm onUploaded={loadStandards} />

      <h2 className="section-heading" style={{ marginTop: "var(--space-6)" }}>
        <Icon name="book" size={20} /> 规范列表
      </h2>

      {processError && (
        <div className="warning-banner" style={{ marginTop: "var(--space-3)" }}>
          {processError}
        </div>
      )}

      {loading ? (
        <div className="empty-state">
          <div className="spinner" />
        </div>
      ) : standards.length === 0 ? (
        <Card>
          <div className="empty-state">
            <p>暂无规范，请先批量上传规范 PDF 文件</p>
          </div>
        </Card>
      ) : (
        <div className="standard-grid">
          {standards.map((std) => (
            <StandardCard
              key={std.id}
              std={std}
              onClick={() => setSelectedId(std.id)}
              onRetry={() => handleRetry(std.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function DatabaseModule() {
  const { tab } = useNavigation();

  if (tab === "standards") {
    return (
      <div>
        <h1 className="section-heading">规范规程库</h1>
        <StandardsContent />
      </div>
    );
  }

  return (
    <div>
      <h1 className="section-heading">投标资料库</h1>
      <Card>
        <div className="empty-state" style={{ padding: "var(--space-12)" }}>
          <p style={{ fontSize: "var(--text-lg)", marginBottom: "var(--space-2)", color: "var(--color-text)" }}>
            {TAB_DESCRIPTIONS[tab] ?? "资料库"}
          </p>
          <p style={{ color: "var(--color-text-muted)" }}>
            此模块正在开发中，敬请期待
          </p>
        </div>
      </Card>
    </div>
  );
}
