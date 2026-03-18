import { useCallback, useEffect, useRef, useState } from "react";

import { Badge } from "../../components/ui/Badge";
import { Card } from "../../components/ui/Card";
import { ClayButton } from "../../components/ui/ClayButton";
import { Icon } from "../../components/ui/Icon";
import { useNavigation } from "../../lib/NavigationContext";
import type {
  Standard,
  StandardClauseNode,
  StandardDetail,
} from "../../lib/api";
import {
  fetchStandardDetail,
  fetchStandardStatus,
  listStandards,
  triggerStandardProcessing,
  uploadStandard,
} from "../../lib/api";

// ── Tab descriptions for non-standards tabs ──

const TAB_DESCRIPTIONS: Record<string, string> = {
  history: "管理历史投标文件，支持按项目类型和时间筛选",
  excellent: "收集和标注优秀投标文件，供编制参考",
  company: "公司资质证书、业绩证明等企业资料",
  personnel: "项目团队成员简历、资质证书等",
};

// ── Processing status badge helpers ──

function statusVariant(
  s: string,
): "default" | "primary" | "success" | "warning" | "danger" {
  switch (s) {
    case "completed":
      return "success";
    case "processing":
      return "primary";
    case "failed":
      return "danger";
    case "pending":
      return "warning";
    default:
      return "default";
  }
}

function statusLabel(s: string): string {
  switch (s) {
    case "pending":
      return "待处理";
    case "parsing":
      return "解析中";
    case "processing":
      return "AI处理中";
    case "completed":
      return "已完成";
    case "failed":
      return "失败";
    default:
      return s;
  }
}

// ── Upload Form ──

function UploadForm({ onUploaded }: { onUploaded: () => void }) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [year, setYear] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !code.trim() || !name.trim()) return;

    setUploading(true);
    setError("");
    try {
      await uploadStandard(file, {
        standard_code: code.trim(),
        standard_name: name.trim(),
        version_year: year.trim() || undefined,
        specialty: specialty.trim() || undefined,
      });
      setCode("");
      setName("");
      setYear("");
      setSpecialty("");
      setFile(null);
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
        <h3 style={{ marginBottom: "var(--space-3)", fontWeight: 600 }}>
          <Icon name="upload-cloud" size={18} /> 上传规范文件
        </h3>
        <div className="standard-upload-form">
          <label>
            <span style={{ fontSize: "var(--text-sm)", color: "var(--color-text-secondary)" }}>
              规范编号 *
            </span>
            <input
              className="clay-input"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="如 GB 50010-2010"
              required
            />
          </label>
          <label>
            <span style={{ fontSize: "var(--text-sm)", color: "var(--color-text-secondary)" }}>
              规范名称 *
            </span>
            <input
              className="clay-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="如 混凝土结构设计规范"
              required
            />
          </label>
          <label>
            <span style={{ fontSize: "var(--text-sm)", color: "var(--color-text-secondary)" }}>
              版本年份
            </span>
            <input
              className="clay-input"
              value={year}
              onChange={(e) => setYear(e.target.value)}
              placeholder="如 2010"
            />
          </label>
          <label>
            <span style={{ fontSize: "var(--text-sm)", color: "var(--color-text-secondary)" }}>
              专业类别
            </span>
            <input
              className="clay-input"
              value={specialty}
              onChange={(e) => setSpecialty(e.target.value)}
              placeholder="如 结构"
            />
          </label>
          <label className="full-width">
            <span style={{ fontSize: "var(--text-sm)", color: "var(--color-text-secondary)" }}>
              PDF 文件 *
            </span>
            <input
              type="file"
              accept=".pdf"
              className="clay-input"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              required
            />
          </label>
        </div>
        {error && <p className="text-error" style={{ marginBottom: "var(--space-2)" }}>{error}</p>}
        <ClayButton type="submit" disabled={uploading || !file || !code || !name}>
          {uploading ? "上传中..." : "上传规范"}
        </ClayButton>
      </form>
    </Card>
  );
}

// ── Standard Card ──

function StandardCard({
  std,
  onClick,
  onProcess,
}: {
  std: Standard;
  onClick: () => void;
  onProcess: () => void;
}) {
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
      {(std.processing_status === "processing" || std.processing_status === "parsing") && (
        <div className="flex items-center gap-2" style={{ marginTop: "var(--space-3)" }}>
          <div className="spinner spinner--sm" />
          <span style={{ fontSize: "var(--text-sm)", color: "var(--color-text-muted)" }}>
            AI处理中...
          </span>
        </div>
      )}
      {std.processing_status === "pending" && (
        <div style={{ marginTop: "var(--space-3)" }}>
          <ClayButton
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              onProcess();
            }}
          >
            <Icon name="sparkles" size={14} /> 开始AI处理
          </ClayButton>
        </div>
      )}
      {std.processing_status === "failed" && (
        <div style={{ marginTop: "var(--space-3)" }}>
          <ClayButton
            size="sm"
            variant="secondary"
            onClick={(e) => {
              e.stopPropagation();
              onProcess();
            }}
          >
            <Icon name="refresh" size={14} /> 重新处理
          </ClayButton>
        </div>
      )}
    </Card>
  );
}

// ── Clause Tree Node (recursive) ──

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
      <div
        className="clause-node-header"
        onClick={() => setExpanded(!expanded)}
      >
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
            {node.clause_text && (
              <div className="clause-detail-text">{node.clause_text}</div>
            )}
            {node.summary && (
              <div className="clause-detail-summary">{node.summary}</div>
            )}
            {node.tags && node.tags.length > 0 && (
              <div className="clause-tags">
                {node.tags.map((tag, i) => (
                  <Badge key={i} variant="info">{tag}</Badge>
                ))}
              </div>
            )}
          </div>

          {hasChildren &&
            node.children.map((child) => (
              <ClauseTreeNode key={child.id} node={child} depth={depth + 1} />
            ))}
        </>
      )}
    </div>
  );
}

// ── Standard Detail View ──

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

  useEffect(() => {
    setLoading(true);
    fetchStandardDetail(standardId)
      .then(setDetail)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [standardId]);

  if (loading) {
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
                : "请先执行AI处理以提取条款"}
            </p>
          </div>
        </Card>
      )}
    </div>
  );
}

// ── Standards Content (main tab view) ──

function StandardsContent() {
  const [standards, setStandards] = useState<Standard[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [processError, setProcessError] = useState("");
  const [processingId, setProcessingId] = useState<string | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadStandards = useCallback(() => {
    listStandards()
      .then(setStandards)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadStandards();
  }, [loadStandards]);

  // Poll for processing standards every 5s
  useEffect(() => {
    const hasProcessing = standards.some(
      (s) => s.processing_status === "processing" || s.processing_status === "parsing",
    ) || processingId !== null;
    if (hasProcessing) {
      pollingRef.current = setInterval(() => {
        listStandards().then((data) => {
          setStandards(data);
          // Stop tracking processingId once it's no longer processing
          if (processingId) {
            const target = data.find((s) => s.id === processingId);
            if (target && target.processing_status !== "processing" && target.processing_status !== "parsing") {
              setProcessingId(null);
            }
          }
        }).catch(() => {});
      }, 5000);
    }
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [standards, loadStandards, processingId]);

  const handleProcess = async (id: string) => {
    setProcessError("");
    setProcessingId(id);
    try {
      await triggerStandardProcessing(id);
      // Immediately refresh to show "processing" status and start polling
      loadStandards();
    } catch (err: unknown) {
      setProcessError(err instanceof Error ? err.message : "处理请求失败");
      setProcessingId(null);
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
            <p>暂无规范，请上传规范 PDF 文件</p>
          </div>
        </Card>
      ) : (
        <div className="standard-grid">
          {standards.map((std) => (
            <StandardCard
              key={std.id}
              std={std}
              onClick={() => setSelectedId(std.id)}
              onProcess={() => handleProcess(std.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main Module ──

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
