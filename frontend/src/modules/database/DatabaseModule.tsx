import { useCallback, useEffect, useRef, useState } from "react";

import { Card } from "../../components/ui/Card";
import { ClayButton } from "../../components/ui/ClayButton";
import { Icon } from "../../components/ui/Icon";
import { useNavigation } from "../../lib/NavigationContext";
import type {
  BatchStandardUploadItem,
  Standard,
  StandardParseAssets,
  StandardSearchHit,
  StandardViewerData,
} from "../../lib/api";
import {
  deleteStandard,
  fetchStandardParseAssets,
  fetchStandardViewer,
  listStandards,
  triggerStandardProcessing,
  triggerVisionProcessing,
  uploadStandards,
} from "../../lib/api";
import { StandardSearchCard } from "./components/StandardSearchCard";
import { StandardsTableCard } from "./components/StandardsTableCard";
import { StandardViewerModal } from "./components/StandardViewerModal";

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

function isActiveStatus(status: string): boolean {
  return ["queued_ocr", "parsing", "queued_ai", "processing"].includes(status);
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

function StandardsWorkbench() {
  const [standards, setStandards] = useState<Standard[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionError, setActionError] = useState("");
  const [showDevArtifacts, setShowDevArtifacts] = useState(false);
  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewerMode, setViewerMode] = useState<"browse" | "search-hit">("browse");
  const [viewerData, setViewerData] = useState<StandardViewerData | null>(null);
  const [viewerParseAssets, setViewerParseAssets] = useState<StandardParseAssets | null>(null);
  const [viewerParseAssetsLoading, setViewerParseAssetsLoading] = useState(false);
  const [viewerParseAssetsError, setViewerParseAssetsError] = useState("");
  const [initialClauseId, setInitialClauseId] = useState<string | null>(null);
  const pollingRef = useRef<number | null>(null);
  const viewerRequestRef = useRef(0);
  const viewerAbortRef = useRef<AbortController | null>(null);

  const loadStandards = useCallback(() => {
    listStandards()
      .then((data) => {
        setStandards(data);
        setActionError("");
      })
      .catch((err: unknown) => setActionError(err instanceof Error ? err.message : "加载规范失败"))
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

  useEffect(() => () => {
    viewerAbortRef.current?.abort();
  }, []);

  const openViewer = async (
    standardId: string,
    mode: "browse" | "search-hit",
    clauseId: string | null = null,
  ) => {
    const requestId = viewerRequestRef.current + 1;
    viewerRequestRef.current = requestId;
    viewerAbortRef.current?.abort();
    const controller = new AbortController();
    viewerAbortRef.current = controller;
    setViewerParseAssets(null);
    setViewerParseAssetsError("");
    setViewerParseAssetsLoading(true);

    try {
      const parseAssetsPromise = fetchStandardParseAssets(standardId, { signal: controller.signal })
        .then((assets) => {
          if (viewerRequestRef.current !== requestId || controller.signal.aborted) return;
          setViewerParseAssets(assets);
          setViewerParseAssetsError("");
        })
        .catch((err: unknown) => {
          if (viewerRequestRef.current !== requestId || controller.signal.aborted) return;
          setViewerParseAssets(null);
          setViewerParseAssetsError(err instanceof Error ? err.message : "加载解析诊断失败");
        })
        .finally(() => {
          if (viewerRequestRef.current !== requestId || controller.signal.aborted) return;
          setViewerParseAssetsLoading(false);
        });

      const data = await fetchStandardViewer(standardId, { signal: controller.signal });
      if (viewerRequestRef.current !== requestId) return;
      setViewerData(data);
      setViewerMode(mode);
      setInitialClauseId(clauseId);
      setViewerOpen(true);
      setActionError("");
      await parseAssetsPromise;
    } catch (err: unknown) {
      if (controller.signal.aborted) return;
      if (viewerRequestRef.current !== requestId) return;
      setViewerParseAssetsLoading(false);
      setActionError(err instanceof Error ? err.message : "加载查阅数据失败");
    } finally {
      if (viewerAbortRef.current === controller) {
        viewerAbortRef.current = null;
      }
    }
  };

  const handleRetry = async (id: string) => {
    try {
      await triggerStandardProcessing(id);
      loadStandards();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "重新入队失败");
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm("删除后将移除整份规范、解析结果与源 PDF，是否继续？")) {
      return;
    }

    try {
      await deleteStandard(id);
      if (viewerOpen && viewerData?.id === id) {
        setViewerOpen(false);
        setViewerData(null);
        setViewerParseAssets(null);
        setViewerParseAssetsError("");
        setViewerParseAssetsLoading(false);
      }
      loadStandards();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "删除规范失败");
    }
  };

  const handleOpenSearchHit = (hit: StandardSearchHit) => {
    void openViewer(hit.standard_id, "search-hit", hit.clause_id);
  };

  const handleVisionProcess = async (id: string) => {
    setActionError("");
    try {
      await triggerVisionProcessing(id);
      loadStandards();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "VL 解析触发失败");
    }
  };

  const isDevMode = import.meta.env.DEV;
  const hiddenDevArtifactCount = isDevMode
    ? standards.filter((std) => std.is_dev_artifact).length
    : 0;
  const visibleStandards = isDevMode && !showDevArtifacts
    ? standards.filter((std) => !std.is_dev_artifact)
    : standards;

  return (
    <div className="standards-workbench">
      <UploadForm onUploaded={loadStandards} />

      <div className="standards-workbench__cards">
        <StandardsTableCard
          standards={visibleStandards}
          loading={loading}
          error={actionError}
          isDevMode={isDevMode}
          showDevArtifacts={showDevArtifacts}
          hiddenDevArtifactCount={!showDevArtifacts ? hiddenDevArtifactCount : 0}
          onToggleShowDevArtifacts={setShowDevArtifacts}
          onRetry={(id) => void handleRetry(id)}
          onDelete={(id) => void handleDelete(id)}
          onOpenViewer={(id) => void openViewer(id, "browse")}
          onVisionProcess={(id) => void handleVisionProcess(id)}
        />

        <StandardSearchCard onOpenHit={handleOpenSearchHit} />
      </div>

      <StandardViewerModal
        open={viewerOpen}
        mode={viewerMode}
        viewerData={viewerData}
        parseAssets={viewerParseAssets}
        parseAssetsLoading={viewerParseAssetsLoading}
        parseAssetsError={viewerParseAssetsError}
        initialClauseId={initialClauseId}
        onClose={() => {
          viewerAbortRef.current?.abort();
          viewerAbortRef.current = null;
          setViewerOpen(false);
          setViewerParseAssetsLoading(false);
          setViewerParseAssetsError("");
        }}
      />
    </div>
  );
}

export function DatabaseModule() {
  const { tab } = useNavigation();

  if (tab === "standards") {
    return (
      <div>
        <h1 className="section-heading">规范规程库</h1>
        <StandardsWorkbench />
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
