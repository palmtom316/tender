import { useCallback, useEffect, useRef, useState } from "react";

import { Card } from "../../components/ui/Card";
import { ClayButton } from "../../components/ui/ClayButton";
import { Icon } from "../../components/ui/Icon";
import { useNavigation } from "../../lib/NavigationContext";
import type {
  AssetTaxonomyDomain,
  BatchStandardUploadItem,
  CompanyProfile,
  EvidenceAsset,
  LibraryCompany,
  PersonProfile,
  Standard,
  StandardParseAssets,
  StandardQualityReportResponse,
  StandardSearchHit,
  StandardViewerData,
} from "../../lib/api";
import {
  createLibraryCompany,
  deleteStandard,
  fetchAssetTaxonomy,
  fetchCompanyProfiles,
  fetchEvidenceAssets,
  fetchLibraryCompanies,
  fetchPeople,
  fetchStandardParseAssets,
  fetchStandardQualityReport,
  fetchStandardViewer,
  listStandards,
  triggerStandardProcessing,
  uploadEvidenceAsset,
  uploadStandards,
} from "../../lib/api";
import { StandardSearchCard } from "./components/StandardSearchCard";
import { StandardsTableCard } from "./components/StandardsTableCard";
import { StandardViewerModal } from "./components/StandardViewerModal";
import { TemplateFieldWorkbench } from "./components/TemplateFieldWorkbench";

const TAB_DESCRIPTIONS: Record<string, string> = {
  history: "管理历史投标文件，支持按项目类型和时间筛选",
  excellent: "收集和标注优秀投标文件，供编制参考",
  templates: "配置模板包、模板项字段映射和渲染上下文",
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
  const [viewerQualityReport, setViewerQualityReport] = useState<StandardQualityReportResponse | null>(null);
  const [viewerQualityReportLoading, setViewerQualityReportLoading] = useState(false);
  const [viewerQualityReportError, setViewerQualityReportError] = useState("");
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
    setViewerQualityReport(null);
    setViewerQualityReportError("");
    setViewerQualityReportLoading(true);

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
      const qualityReportPromise = fetchStandardQualityReport(standardId, { signal: controller.signal })
        .then((report) => {
          if (viewerRequestRef.current !== requestId || controller.signal.aborted) return;
          setViewerQualityReport(report);
          setViewerQualityReportError("");
        })
        .catch((err: unknown) => {
          if (viewerRequestRef.current !== requestId || controller.signal.aborted) return;
          setViewerQualityReport(null);
          setViewerQualityReportError(err instanceof Error ? err.message : "加载质量报告失败");
        })
        .finally(() => {
          if (viewerRequestRef.current !== requestId || controller.signal.aborted) return;
          setViewerQualityReportLoading(false);
        });

      const data = await fetchStandardViewer(standardId, { signal: controller.signal });
      if (viewerRequestRef.current !== requestId) return;
      setViewerData(data);
      setViewerMode(mode);
      setInitialClauseId(clauseId);
      setViewerOpen(true);
      setActionError("");
      await parseAssetsPromise;
      await qualityReportPromise;
    } catch (err: unknown) {
      if (controller.signal.aborted) return;
      if (viewerRequestRef.current !== requestId) return;
      setViewerParseAssetsLoading(false);
      setViewerQualityReportLoading(false);
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
        setViewerQualityReport(null);
        setViewerQualityReportError("");
        setViewerQualityReportLoading(false);
      }
      loadStandards();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "删除规范失败");
    }
  };

  const handleOpenSearchHit = (hit: StandardSearchHit) => {
    void openViewer(hit.standard_id, "search-hit", hit.clause_id);
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
        qualityReport={viewerQualityReport?.report ?? null}
        qualityReportLoading={viewerQualityReportLoading}
        qualityReportError={viewerQualityReportError}
        initialClauseId={initialClauseId}
        onClose={() => {
          viewerAbortRef.current?.abort();
          viewerAbortRef.current = null;
          setViewerOpen(false);
          setViewerParseAssetsLoading(false);
          setViewerParseAssetsError("");
          setViewerQualityReport(null);
          setViewerQualityReportError("");
          setViewerQualityReportLoading(false);
        }}
      />
    </div>
  );
}

function CompanyLibraryWorkbench() {
  const [libraries, setLibraries] = useState<LibraryCompany[]>([]);
  const [taxonomy, setTaxonomy] = useState<AssetTaxonomyDomain[]>([]);
  const [profiles, setProfiles] = useState<CompanyProfile[]>([]);
  const [assets, setAssets] = useState<EvidenceAsset[]>([]);
  const [selectedLibraryId, setSelectedLibraryId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [newCompanyName, setNewCompanyName] = useState("");
  const [newCompanyType, setNewCompanyType] = useState("");
  const [creating, setCreating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadDomain, setUploadDomain] = useState("company_qualification");
  const [uploadCategory, setUploadCategory] = useState("business_license");
  const [uploadName, setUploadName] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);

  const loadLibraries = useCallback(async () => {
    const rows = await fetchLibraryCompanies();
    setLibraries(rows);
    setSelectedLibraryId((current) => current || rows[0]?.id || "");
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [libraryRows, taxonomyRes] = await Promise.all([
        fetchLibraryCompanies(),
        fetchAssetTaxonomy(),
      ]);
      setLibraries(libraryRows);
      setTaxonomy(taxonomyRes.domains);
      setSelectedLibraryId((current) => current || libraryRows[0]?.id || "");
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "加载公司资料库失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (!selectedLibraryId) {
      setProfiles([]);
      setAssets([]);
      return;
    }
    Promise.all([
      fetchCompanyProfiles({ libraryCompanyId: selectedLibraryId }),
      fetchEvidenceAssets({ libraryCompanyId: selectedLibraryId }),
    ])
      .then(([profileRows, assetRows]) => {
        setProfiles(profileRows);
        setAssets(assetRows.filter((row) => row.asset_domain !== "personnel"));
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "加载公司资料失败"));
  }, [selectedLibraryId]);

  const categoriesForDomain = taxonomy.find((domain) => domain.domain === uploadDomain)?.categories ?? [];

  useEffect(() => {
    if (categoriesForDomain.length > 0) {
      setUploadCategory(categoriesForDomain[0][0]);
    }
  }, [uploadDomain, categoriesForDomain]);

  const selectedLibrary = libraries.find((row) => row.id === selectedLibraryId) ?? null;

  const groupedAssets = taxonomy
    .filter((domain) => domain.domain !== "personnel")
    .map((domain) => ({
      ...domain,
      count: assets.filter((asset) => asset.asset_domain === domain.domain).length,
    }));

  const handleCreateLibrary = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!newCompanyName.trim()) return;
    setCreating(true);
    try {
      const created = await createLibraryCompany({
        company_name: newCompanyName.trim(),
        company_type: newCompanyType.trim() || undefined,
      });
      setNewCompanyName("");
      setNewCompanyType("");
      await loadLibraries();
      setSelectedLibraryId(created.id);
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "创建公司资料库失败");
    } finally {
      setCreating(false);
    }
  };

  const handleUpload = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!selectedLibraryId || !uploadFile || !uploadName.trim()) return;
    setUploading(true);
    try {
      await uploadEvidenceAsset({
        library_company_id: selectedLibraryId,
        owner_type: "library_company",
        owner_id: selectedLibraryId,
        asset_name: uploadName.trim(),
        asset_domain: uploadDomain,
        asset_category: uploadCategory,
        file: uploadFile,
      });
      setUploadName("");
      setUploadFile(null);
      const assetRows = await fetchEvidenceAssets({ libraryCompanyId: selectedLibraryId });
      setAssets(assetRows.filter((row) => row.asset_domain !== "personnel"));
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "上传资料失败");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div style={{ display: "grid", gap: "var(--space-5)" }}>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 340px) minmax(0, 1fr)", gap: "var(--space-5)" }}>
        <Card>
          <h3 style={{ marginBottom: "var(--space-3)" }}>公司库</h3>
          <form onSubmit={handleCreateLibrary} style={{ display: "grid", gap: "var(--space-2)", marginBottom: "var(--space-4)" }}>
            <input className="clay-input" placeholder="公司名称" value={newCompanyName} onChange={(event) => setNewCompanyName(event.target.value)} />
            <input className="clay-input" placeholder="公司类型" value={newCompanyType} onChange={(event) => setNewCompanyType(event.target.value)} />
            <ClayButton type="submit" disabled={creating}>{creating ? "创建中..." : "新建公司库"}</ClayButton>
          </form>
          {loading ? <div className="spinner" /> : (
            <div style={{ display: "grid", gap: "var(--space-2)" }}>
              {libraries.map((row) => (
                <button
                  key={row.id}
                  type="button"
                  className={`template-list__item ${selectedLibraryId === row.id ? "is-active" : ""}`}
                  onClick={() => setSelectedLibraryId(row.id)}
                >
                  <span className="template-list__title">{row.company_name}</span>
                  <span className="template-list__meta">{row.company_type || row.company_key}</span>
                </button>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-4)", marginBottom: "var(--space-4)", flexWrap: "wrap" }}>
            <div>
              <h3 style={{ marginBottom: "var(--space-1)" }}>{selectedLibrary?.company_name || "未选择公司库"}</h3>
              <p style={{ color: "var(--color-text-muted)" }}>公司资料、业绩、资质、履约评价统一归档到本地复用库。</p>
            </div>
            <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}>
              <div className="template-summary__pill"><span>公司档案</span><strong>{profiles.length}</strong></div>
              <div className="template-summary__pill"><span>已上传资料</span><strong>{assets.length}</strong></div>
            </div>
          </div>

          <form onSubmit={handleUpload} style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "var(--space-3)", marginBottom: "var(--space-4)" }}>
            <input className="clay-input" placeholder="资料名称" value={uploadName} onChange={(event) => setUploadName(event.target.value)} />
            <select className="clay-input" value={uploadDomain} onChange={(event) => setUploadDomain(event.target.value)}>
              {taxonomy.filter((row) => row.domain !== "personnel").map((row) => (
                <option key={row.domain} value={row.domain}>{row.label}</option>
              ))}
            </select>
            <select className="clay-input" value={uploadCategory} onChange={(event) => setUploadCategory(event.target.value)}>
              {categoriesForDomain.map(([code, label]) => (
                <option key={code} value={code}>{label}</option>
              ))}
            </select>
            <input type="file" accept=".pdf,image/*" onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)} />
            <div style={{ gridColumn: "1 / -1" }}>
              <ClayButton type="submit" disabled={!selectedLibraryId || !uploadFile || !uploadName.trim() || uploading}>
                {uploading ? "上传中..." : "上传公司资料"}
              </ClayButton>
            </div>
          </form>

          {error && <p className="text-error">{error}</p>}

          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "var(--space-4)" }}>
            <div>
              <h4 style={{ marginBottom: "var(--space-2)" }}>资料分类</h4>
              <div style={{ display: "grid", gap: "var(--space-2)" }}>
                {groupedAssets.map((row) => (
                  <div key={row.domain} className="template-list__item">
                    <span className="template-list__title">{row.label}</span>
                    <span className="template-list__meta">{row.count} 份资料</span>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h4 style={{ marginBottom: "var(--space-2)" }}>最近上传</h4>
              <div style={{ display: "grid", gap: "var(--space-2)" }}>
                {assets.slice(0, 8).map((row) => (
                  <div key={row.id} className="template-list__item">
                    <span className="template-list__title">{row.asset_name}</span>
                    <span className="template-list__meta">{row.file_name} / {row.asset_category}</span>
                  </div>
                ))}
                {assets.length === 0 && <div className="template-strip-empty">当前公司库还没有上传资料。</div>}
              </div>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}

function PersonnelLibraryWorkbench() {
  const [libraries, setLibraries] = useState<LibraryCompany[]>([]);
  const [people, setPeople] = useState<PersonProfile[]>([]);
  const [assets, setAssets] = useState<EvidenceAsset[]>([]);
  const [selectedLibraryId, setSelectedLibraryId] = useState<string>("");
  const [selectedPersonId, setSelectedPersonId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploadCategory, setUploadCategory] = useState("id_card");
  const [uploadName, setUploadName] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);

  useEffect(() => {
    Promise.all([fetchLibraryCompanies(), fetchAssetTaxonomy()])
      .then(([libraryRows]) => {
        setLibraries(libraryRows);
        setSelectedLibraryId(libraryRows[0]?.id ?? "");
        setError("");
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "加载人员资料库失败"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedLibraryId) {
      setPeople([]);
      setAssets([]);
      setSelectedPersonId("");
      return;
    }
    Promise.all([
      fetchPeople({ libraryCompanyId: selectedLibraryId }),
      fetchEvidenceAssets({ libraryCompanyId: selectedLibraryId, assetDomain: "personnel" }),
    ])
      .then(([personRows, assetRows]) => {
        setPeople(personRows);
        setAssets(assetRows);
        setSelectedPersonId((current) => current || personRows[0]?.id || "");
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "加载人员资料失败"));
  }, [selectedLibraryId]);

  const handleUpload = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!selectedLibraryId || !selectedPersonId || !uploadFile || !uploadName.trim()) return;
    try {
      await uploadEvidenceAsset({
        library_company_id: selectedLibraryId,
        owner_type: "person_profile",
        owner_id: selectedPersonId,
        asset_name: uploadName.trim(),
        asset_domain: "personnel",
        asset_category: uploadCategory,
        file: uploadFile,
      });
      const assetRows = await fetchEvidenceAssets({ libraryCompanyId: selectedLibraryId, assetDomain: "personnel" });
      setAssets(assetRows);
      setUploadName("");
      setUploadFile(null);
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "上传人员资料失败");
    }
  };

  const personAssetCount = people.map((person) => ({
    ...person,
    assetCount: assets.filter((asset) => asset.owner_id === person.id).length,
  }));

  return (
    <div style={{ display: "grid", gap: "var(--space-5)" }}>
      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-4)", flexWrap: "wrap", marginBottom: "var(--space-4)" }}>
          <div>
            <h3 style={{ marginBottom: "var(--space-1)" }}>人员资料库</h3>
            <p style={{ color: "var(--color-text-muted)" }}>按公司维度管理人员档案，并把身份证、资格证、社保、劳动合同等文件直接归到个人名下。</p>
          </div>
          <select className="clay-input" value={selectedLibraryId} onChange={(event) => setSelectedLibraryId(event.target.value)} style={{ minWidth: 240 }}>
            <option value="">选择公司库</option>
            {libraries.map((row) => (
              <option key={row.id} value={row.id}>{row.company_name}</option>
            ))}
          </select>
        </div>

        {loading ? <div className="spinner" /> : (
          <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 360px) minmax(0, 1fr)", gap: "var(--space-5)" }}>
            <div>
              <h4 style={{ marginBottom: "var(--space-2)" }}>人员清单</h4>
              <div style={{ display: "grid", gap: "var(--space-2)" }}>
                {personAssetCount.map((row) => (
                  <button
                    key={row.id}
                    type="button"
                    className={`template-list__item ${selectedPersonId === row.id ? "is-active" : ""}`}
                    onClick={() => setSelectedPersonId(row.id)}
                  >
                    <span className="template-list__title">{row.full_name}</span>
                    <span className="template-list__meta">{row.role_name || "未设置角色"} / {row.assetCount} 份资料</span>
                  </button>
                ))}
                {people.length === 0 && <div className="template-strip-empty">当前公司库还没有人员档案。后续补充独立的人员创建面板。</div>}
              </div>
            </div>

            <div>
              <form onSubmit={handleUpload} style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "var(--space-3)", marginBottom: "var(--space-4)" }}>
                <input className="clay-input" placeholder="资料名称" value={uploadName} onChange={(event) => setUploadName(event.target.value)} />
                <select className="clay-input" value={selectedPersonId} onChange={(event) => setSelectedPersonId(event.target.value)}>
                  <option value="">选择人员</option>
                  {people.map((row) => (
                    <option key={row.id} value={row.id}>{row.full_name}</option>
                  ))}
                </select>
                <select className="clay-input" value={uploadCategory} onChange={(event) => setUploadCategory(event.target.value)}>
                  <option value="performance_table">业绩表</option>
                  <option value="id_card">身份证</option>
                  <option value="graduation_certificate">毕业证</option>
                  <option value="title_certificate">职称证</option>
                  <option value="practice_certificate">执业资格证</option>
                  <option value="safety_certificate">安全生产合格证</option>
                  <option value="special_operation_certificate">特种作业操作证</option>
                  <option value="social_security_proof">社保参保证明</option>
                  <option value="labor_contract">劳动合同书</option>
                </select>
                <input type="file" accept=".pdf,image/*" onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)} />
                <div style={{ gridColumn: "1 / -1" }}>
                  <ClayButton type="submit" disabled={!selectedPersonId || !uploadFile || !uploadName.trim()}>
                    上传人员资料
                  </ClayButton>
                </div>
              </form>

              {error && <p className="text-error">{error}</p>}

              <div style={{ display: "grid", gap: "var(--space-2)" }}>
                {assets
                  .filter((row) => !selectedPersonId || row.owner_id === selectedPersonId)
                  .slice(0, 12)
                  .map((row) => (
                    <div key={row.id} className="template-list__item">
                      <span className="template-list__title">{row.asset_name}</span>
                      <span className="template-list__meta">{row.file_name} / {row.asset_category}</span>
                    </div>
                  ))}
                {assets.length === 0 && <div className="template-strip-empty">当前没有人员附件。</div>}
              </div>
            </div>
          </div>
        )}
      </Card>
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

  if (tab === "templates") {
    return (
      <div>
        <h1 className="section-heading">模板包字段面板</h1>
        <TemplateFieldWorkbench />
      </div>
    );
  }

  if (tab === "company") {
    return (
      <div>
        <h1 className="section-heading">公司资料库</h1>
        <CompanyLibraryWorkbench />
      </div>
    );
  }

  if (tab === "personnel") {
    return (
      <div>
        <h1 className="section-heading">人员资料库</h1>
        <PersonnelLibraryWorkbench />
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
