import { useCallback, useEffect, useMemo, useState } from "react";

import { Icon } from "../../../components/ui/Icon";
import { Card } from "../../../components/ui/Card";
import { ClayButton } from "../../../components/ui/ClayButton";
import { CompanyAssetSection } from "./CompanyAssetSection";
import type {
  AssetTaxonomyDomain,
  CompanyContractPerformance,
  CompanyProfile,
  EvidenceAsset,
  LibraryCompany,
} from "../../../lib/api";
import {
  companyContractPerformanceExportUrl,
  createCompanyContractPerformance,
  createLibraryCompany,
  deleteLibraryCompany,
  deleteCompanyContractPerformance,
  evidenceAssetDownloadUrl,
  fetchAssetTaxonomy,
  fetchCompanyContractPerformances,
  fetchCompanyProfiles,
  fetchEvidenceAssets,
  fetchLibraryCompanies,
  getAuthHeaders,
  updateCompanyContractPerformance,
  uploadEvidenceAsset,
} from "../../../lib/api";

type UploadFieldKey =
  | "signature"
  | "invoice"
  | "invoiceVerification"
  | "performanceEvaluation";

type UploadFieldState = {
  file: File | null;
  uploading: boolean;
  assetId: string;
  assetName: string;
  fileName: string;
  cleared: boolean;
};

type ContractFormState = {
  contractName: string;
  partyACompany: string;
  contractCategory: string;
  engineeringCategory: string;
  contractAmount: string;
  contractSignedDate: string;
  contractCompletedDate: string;
  contractStatus: string;
};

const EMPTY_UPLOAD_FIELD: UploadFieldState = {
  file: null,
  uploading: false,
  assetId: "",
  assetName: "",
  fileName: "",
  cleared: false,
};

const EMPTY_CONTRACT_FORM: ContractFormState = {
  contractName: "",
  partyACompany: "",
  contractCategory: "",
  engineeringCategory: "",
  contractAmount: "",
  contractSignedDate: "",
  contractCompletedDate: "",
  contractStatus: "",
};

const UPLOAD_FIELD_CONFIG: Array<{
  key: UploadFieldKey;
  label: string;
  category: string;
  assetName: string;
}> = [
  {
    key: "signature",
    label: "合同主要签署页面",
    category: "contract_document",
    assetName: "合同主要签署页面",
  },
  {
    key: "invoice",
    label: "合同发票",
    category: "invoice_document",
    assetName: "合同发票",
  },
  {
    key: "invoiceVerification",
    label: "合同发票验证",
    category: "invoice_verification",
    assetName: "合同发票验证",
  },
  {
    key: "performanceEvaluation",
    label: "合同履约评价",
    category: "performance_evaluation",
    assetName: "合同履约评价",
  },
];

function createEmptyUploadFields(): Record<UploadFieldKey, UploadFieldState> {
  return {
    signature: { ...EMPTY_UPLOAD_FIELD },
    invoice: { ...EMPTY_UPLOAD_FIELD },
    invoiceVerification: { ...EMPTY_UPLOAD_FIELD },
    performanceEvaluation: { ...EMPTY_UPLOAD_FIELD },
  };
}

function formatDateCell(value: string | null): string {
  return value || "未填";
}

function formatAmountCell(value: string | null): string {
  if (!value) return "未填";
  return `${value} 元`;
}

export function CompanyLibraryWorkbench() {
  const [libraries, setLibraries] = useState<LibraryCompany[]>([]);
  const [taxonomy, setTaxonomy] = useState<AssetTaxonomyDomain[]>([]);
  const [profiles, setProfiles] = useState<CompanyProfile[]>([]);
  const [assets, setAssets] = useState<EvidenceAsset[]>([]);
  const [performances, setPerformances] = useState<CompanyContractPerformance[]>([]);
  const [selectedLibraryId, setSelectedLibraryId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [newCompanyName, setNewCompanyName] = useState("");
  const [newCompanyType, setNewCompanyType] = useState("");
  const [creating, setCreating] = useState(false);
  const [deletingLibraryId, setDeletingLibraryId] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadDomain, setUploadDomain] = useState("company_qualification");
  const [uploadCategory, setUploadCategory] = useState("business_license");
  const [uploadName, setUploadName] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [contractForm, setContractForm] = useState<ContractFormState>(EMPTY_CONTRACT_FORM);
  const [contractUploads, setContractUploads] = useState<Record<UploadFieldKey, UploadFieldState>>(
    createEmptyUploadFields,
  );
  const [editingPerformanceId, setEditingPerformanceId] = useState<string>("");
  const [savingContract, setSavingContract] = useState(false);
  const [deletingPerformanceId, setDeletingPerformanceId] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [previewingAssetId, setPreviewingAssetId] = useState("");

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
      setPerformances([]);
      return;
    }
    Promise.all([
      fetchCompanyProfiles({ libraryCompanyId: selectedLibraryId }),
      fetchEvidenceAssets({ libraryCompanyId: selectedLibraryId }),
      fetchCompanyContractPerformances({ libraryCompanyId: selectedLibraryId }),
    ])
      .then(([profileRows, assetRows, performanceRows]) => {
        setProfiles(profileRows);
        setAssets(assetRows.filter((row) => row.asset_domain !== "personnel"));
        setPerformances(performanceRows);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "加载公司资料失败"));
  }, [selectedLibraryId]);

  const uploadDomains = useMemo(
    () => taxonomy.filter((domain) => domain.domain !== "personnel" && domain.domain !== "company_performance"),
    [taxonomy],
  );
  const categoriesForDomain = uploadDomains.find((domain) => domain.domain === uploadDomain)?.categories ?? [];

  useEffect(() => {
    if (categoriesForDomain.length > 0) {
      setUploadCategory(categoriesForDomain[0][0]);
    }
  }, [uploadDomain, categoriesForDomain]);

  const selectedLibrary = libraries.find((row) => row.id === selectedLibraryId) ?? null;

  const groupedAssets = uploadDomains.map((domain) => ({
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

  const handleDeleteLibrary = async (library: LibraryCompany) => {
    const confirmed = window.confirm(`确认删除公司库“${library.company_name}”？关联的公司资料、资产和业绩会一并删除。`);
    if (!confirmed) return;
    setDeletingLibraryId(library.id);
    try {
      await deleteLibraryCompany(library.id);
      const rows = await fetchLibraryCompanies();
      setLibraries(rows);
      setSelectedLibraryId((current) => {
        if (current !== library.id) return current || rows[0]?.id || "";
        return rows[0]?.id || "";
      });
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "删除公司资料库失败");
    } finally {
      setDeletingLibraryId("");
    }
  };

  const handleContractFieldChange = (key: keyof ContractFormState, value: string) => {
    setContractForm((current) => ({ ...current, [key]: value }));
  };

  const resetContractEditor = () => {
    setEditingPerformanceId("");
    setContractForm(EMPTY_CONTRACT_FORM);
    setContractUploads(createEmptyUploadFields());
  };

  const handleContractFileChange = (key: UploadFieldKey, file: File | null) => {
    setContractUploads((current) => ({
      ...current,
      [key]: {
        ...current[key],
        file,
        cleared: false,
      },
    }));
  };

  const clearContractAttachment = (key: UploadFieldKey) => {
    setContractUploads((current) => ({
      ...current,
      [key]: {
        file: null,
        uploading: false,
        assetId: "",
        assetName: "",
        fileName: "",
        cleared: true,
      },
    }));
  };

  const uploadContractAttachment = async (key: UploadFieldKey) => {
    const fieldConfig = UPLOAD_FIELD_CONFIG.find((item) => item.key === key);
    const fieldState = contractUploads[key];
    if (!selectedLibraryId || !fieldConfig || !fieldState.file) return;
    setContractUploads((current) => ({
      ...current,
      [key]: { ...current[key], uploading: true },
    }));
    try {
      const asset = await uploadEvidenceAsset({
        library_company_id: selectedLibraryId,
        owner_type: "library_company",
        owner_id: selectedLibraryId,
        asset_name: `${contractForm.contractName || "未命名合同"}-${fieldConfig.assetName}`,
        asset_domain: "company_performance",
        asset_category: fieldConfig.category,
        file: fieldState.file,
      });
      setContractUploads((current) => ({
        ...current,
        [key]: {
          file: null,
          uploading: false,
          assetId: asset.id,
          assetName: asset.asset_name,
          fileName: asset.file_name,
          cleared: false,
        },
      }));
      const assetRows = await fetchEvidenceAssets({ libraryCompanyId: selectedLibraryId });
      setAssets(assetRows.filter((row) => row.asset_domain !== "personnel"));
      setError("");
    } catch (err: unknown) {
      setContractUploads((current) => ({
        ...current,
        [key]: { ...current[key], uploading: false },
      }));
      setError(err instanceof Error ? err.message : "上传合同附件失败");
    }
  };

  const handleCreateContract = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!selectedLibraryId || !contractForm.contractName.trim() || !contractForm.partyACompany.trim()) return;
    setSavingContract(true);
    try {
      const payload = {
        contract_name: contractForm.contractName.trim(),
        party_a_company: contractForm.partyACompany.trim(),
        contract_category: contractForm.contractCategory.trim() || null,
        engineering_category: contractForm.engineeringCategory.trim() || null,
        contract_amount: contractForm.contractAmount.trim() || null,
        contract_signed_date: contractForm.contractSignedDate || null,
        contract_completed_date: contractForm.contractCompletedDate || null,
        contract_status: contractForm.contractStatus.trim() || null,
        signature_asset_id: contractUploads.signature.assetId || null,
        signature_asset_name: contractUploads.signature.fileName || null,
        invoice_asset_id: contractUploads.invoice.assetId || null,
        invoice_asset_name: contractUploads.invoice.fileName || null,
        invoice_verification_asset_id: contractUploads.invoiceVerification.assetId || null,
        invoice_verification_asset_name: contractUploads.invoiceVerification.fileName || null,
        performance_evaluation_asset_id: contractUploads.performanceEvaluation.assetId || null,
        performance_evaluation_asset_name: contractUploads.performanceEvaluation.fileName || null,
      };
      if (editingPerformanceId) {
        await updateCompanyContractPerformance(editingPerformanceId, payload);
      } else {
        await createCompanyContractPerformance({
          library_company_id: selectedLibraryId,
          ...payload,
        });
      }
      const performanceRows = await fetchCompanyContractPerformances({ libraryCompanyId: selectedLibraryId });
      setPerformances(performanceRows);
      resetContractEditor();
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : editingPerformanceId ? "更新合同业绩失败" : "新增合同业绩失败");
    } finally {
      setSavingContract(false);
    }
  };

  const handleEditPerformance = (row: CompanyContractPerformance) => {
    setEditingPerformanceId(row.id);
    setContractForm({
      contractName: row.contract_name,
      partyACompany: row.party_a_company,
      contractCategory: row.contract_category || "",
      engineeringCategory: row.engineering_category || "",
      contractAmount: row.contract_amount || "",
      contractSignedDate: row.contract_signed_date || "",
      contractCompletedDate: row.contract_completed_date || "",
      contractStatus: row.contract_status || "",
    });
    setContractUploads({
      signature: {
        ...EMPTY_UPLOAD_FIELD,
        assetId: row.signature_asset_id || "",
        assetName: row.signature_asset_name || "",
        fileName: row.signature_asset_name || "",
        cleared: false,
      },
      invoice: {
        ...EMPTY_UPLOAD_FIELD,
        assetId: row.invoice_asset_id || "",
        assetName: row.invoice_asset_name || "",
        fileName: row.invoice_asset_name || "",
        cleared: false,
      },
      invoiceVerification: {
        ...EMPTY_UPLOAD_FIELD,
        assetId: row.invoice_verification_asset_id || "",
        assetName: row.invoice_verification_asset_name || "",
        fileName: row.invoice_verification_asset_name || "",
        cleared: false,
      },
      performanceEvaluation: {
        ...EMPTY_UPLOAD_FIELD,
        assetId: row.performance_evaluation_asset_id || "",
        assetName: row.performance_evaluation_asset_name || "",
        fileName: row.performance_evaluation_asset_name || "",
        cleared: false,
      },
    });
  };

  const handleDeletePerformance = async (recordId: string) => {
    if (!selectedLibraryId) return;
    const confirmed = window.confirm("确认删除这条合同业绩记录？");
    if (!confirmed) return;
    setDeletingPerformanceId(recordId);
    try {
      await deleteCompanyContractPerformance(recordId);
      const performanceRows = await fetchCompanyContractPerformances({ libraryCompanyId: selectedLibraryId });
      setPerformances(performanceRows);
      if (editingPerformanceId === recordId) {
        resetContractEditor();
      }
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "删除合同业绩失败");
    } finally {
      setDeletingPerformanceId("");
    }
  };

  const handleDownload = async () => {
    if (!selectedLibraryId) return;
    setDownloading(true);
    try {
      const response = await fetch(companyContractPerformanceExportUrl(selectedLibraryId), {
        headers: getAuthHeaders(),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "合同业绩表.csv";
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "下载合同业绩表失败");
    } finally {
      setDownloading(false);
    }
  };

  const openEvidenceAsset = async (assetId: string, filename: string) => {
    setPreviewingAssetId(assetId);
    try {
      const response = await fetch(evidenceAssetDownloadUrl(assetId), {
        headers: getAuthHeaders(),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const blob = await response.blob();
      const blobUrl = URL.createObjectURL(blob);
      window.open(blobUrl, "_blank", "noopener,noreferrer");
      window.setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? `打开附件失败: ${filename}` : "打开附件失败");
    } finally {
      setPreviewingAssetId("");
    }
  };

  return (
    <div className="stack">
      <div className="split-panel-grid">
        <Card>
          <h3 className="section-heading section-heading--sm">公司库</h3>
          <form onSubmit={handleCreateLibrary} className="form-grid-compact">
            <input className="clay-input" aria-label="公司名称" placeholder="公司名称" value={newCompanyName} onChange={(event) => setNewCompanyName(event.target.value)} />
            <input className="clay-input" aria-label="公司类型" placeholder="公司类型" value={newCompanyType} onChange={(event) => setNewCompanyType(event.target.value)} />
            <ClayButton type="submit" disabled={creating}>{creating ? "创建中..." : "新建公司库"}</ClayButton>
          </form>
          {loading ? (
            <div className="skeleton-stack" aria-label="公司库加载中">
              <div className="skeleton-card" />
              <div className="skeleton-card" />
            </div>
          ) : (
            <div className="stack-sm">
              {libraries.map((row) => (
                <div key={row.id} className={`template-list__item ${selectedLibraryId === row.id ? "is-active" : ""}`}>
                  <div className="template-list__split">
                    <button
                      type="button"
                      className="template-list__content-button"
                      onClick={() => setSelectedLibraryId(row.id)}
                    >
                      <span className="template-list__title">{row.company_name}</span>
                      <span className="template-list__meta">{row.company_type || row.company_key}</span>
                    </button>
                    <ClayButton
                      type="button"
                      variant="danger"
                      size="sm"
                      onClick={() => void handleDeleteLibrary(row)}
                      disabled={deletingLibraryId === row.id}
                      aria-label={`删除公司库 ${row.company_name}`}
                    >
                      {deletingLibraryId === row.id ? "删除中..." : "删除"}
                    </ClayButton>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <div className="stack">
          <Card>
            <div className="panel-header-split">
              <div>
                <h3 className="panel-title-tight">{selectedLibrary?.company_name || "未选择公司库"}</h3>
                <p className="subtle-copy">公司资料、资质和合同业绩统一沉淀到本地复用库，合同业绩以台账表单管理。</p>
              </div>
              <div className="summary-pill-row">
                <div className="template-summary__pill"><span>公司档案</span><strong>{profiles.length}</strong></div>
                <div className="template-summary__pill"><span>合同业绩</span><strong>{performances.length}</strong></div>
                <div className="template-summary__pill"><span>已上传资料</span><strong>{assets.length}</strong></div>
              </div>
            </div>

            <form onSubmit={handleUpload} className="form-grid-two">
              <input className="clay-input" aria-label="公司资料名称" placeholder="资料名称" value={uploadName} onChange={(event) => setUploadName(event.target.value)} />
              <select className="clay-input" aria-label="公司资料领域" value={uploadDomain} onChange={(event) => setUploadDomain(event.target.value)}>
                {uploadDomains.map((row) => (
                  <option key={row.domain} value={row.domain}>{row.label}</option>
                ))}
              </select>
              <select className="clay-input" aria-label="公司资料分类" value={uploadCategory} onChange={(event) => setUploadCategory(event.target.value)}>
                {categoriesForDomain.map(([code, label]) => (
                  <option key={code} value={code}>{label}</option>
                ))}
              </select>
              <input type="file" accept=".pdf,image/*" aria-label="选择公司资料文件" onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)} />
              <div className="form-grid-full">
                <ClayButton type="submit" disabled={!selectedLibraryId || !uploadFile || !uploadName.trim() || uploading}>
                  {uploading ? "上传中..." : "上传公司资料"}
                </ClayButton>
              </div>
            </form>

            <div className="company-library-dashboard">
              <div>
                <h4 className="panel-title-tight">资料分类</h4>
                <div className="stack-sm">
                  {groupedAssets.map((row) => (
                    <div key={row.domain} className="template-list__item">
                      <span className="template-list__title">{row.label}</span>
                      <span className="template-list__meta">{row.count} 份资料</span>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <h4 className="panel-title-tight">最近上传</h4>
                <div className="stack-sm">
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

          {selectedLibraryId ? (
            <CompanyAssetSection
              libraryCompanyId={selectedLibraryId}
              companyName={selectedLibrary?.company_name || "当前公司库"}
              onError={setError}
            />
          ) : null}

          <Card>
            <div className="template-panel__header">
              <div>
                <div className="template-panel__eyebrow">合同业绩台账</div>
                <h2>公司业绩表</h2>
                <p className="template-panel__description">通过表单录入合同业绩，并上传关键合同附件。下载的合同业绩表不包含 PDF 附件列。</p>
              </div>
              <ClayButton variant="outline" onClick={handleDownload} disabled={!selectedLibraryId || downloading}>
                {downloading ? "导出中..." : "下载合同业绩表"}
              </ClayButton>
            </div>

            <form onSubmit={handleCreateContract} className="company-contract-workbench">
              <div className="company-contract-form-grid">
                <label className="company-contract-field">
                  <span>自动编号</span>
                  <input className="clay-input" value={editingPerformanceId ? "编辑现有记录" : performances.length + 1} disabled aria-label="自动编号" />
                </label>
                <label className="company-contract-field">
                  <span>合同名称</span>
                  <input className="clay-input" aria-label="合同名称" value={contractForm.contractName} onChange={(event) => handleContractFieldChange("contractName", event.target.value)} />
                </label>
                <label className="company-contract-field">
                  <span>合同甲方单位</span>
                  <input className="clay-input" aria-label="合同甲方单位" value={contractForm.partyACompany} onChange={(event) => handleContractFieldChange("partyACompany", event.target.value)} />
                </label>
                <label className="company-contract-field">
                  <span>合同类别</span>
                  <input className="clay-input" aria-label="合同类别" value={contractForm.contractCategory} onChange={(event) => handleContractFieldChange("contractCategory", event.target.value)} />
                </label>
                <label className="company-contract-field">
                  <span>工程类别</span>
                  <input className="clay-input" aria-label="工程类别" value={contractForm.engineeringCategory} onChange={(event) => handleContractFieldChange("engineeringCategory", event.target.value)} />
                </label>
                <label className="company-contract-field">
                  <span>合同金额</span>
                  <input className="clay-input" aria-label="合同金额" inputMode="decimal" value={contractForm.contractAmount} onChange={(event) => handleContractFieldChange("contractAmount", event.target.value)} />
                </label>
                <label className="company-contract-field">
                  <span>合同签订日期</span>
                  <input className="clay-input" aria-label="合同签订日期" type="date" value={contractForm.contractSignedDate} onChange={(event) => handleContractFieldChange("contractSignedDate", event.target.value)} />
                </label>
                <label className="company-contract-field">
                  <span>合同竣工日期</span>
                  <input className="clay-input" aria-label="合同竣工日期" type="date" value={contractForm.contractCompletedDate} onChange={(event) => handleContractFieldChange("contractCompletedDate", event.target.value)} />
                </label>
                <label className="company-contract-field">
                  <span>合同状态</span>
                  <input className="clay-input" aria-label="合同状态" value={contractForm.contractStatus} onChange={(event) => handleContractFieldChange("contractStatus", event.target.value)} />
                </label>
              </div>

              <div className="company-contract-upload-grid">
                {UPLOAD_FIELD_CONFIG.map((field) => {
                  const state = contractUploads[field.key];
                  const hasLinkedAsset = Boolean(state.assetId && state.fileName);
                  return (
                    <div key={field.key} className="company-contract-upload-card">
                      <div className="company-contract-upload-card__header">
                        <strong>{field.label}</strong>
                        {state.file ? (
                          <span>待替换: {state.file.name}</span>
                        ) : hasLinkedAsset ? (
                          <span className="company-contract-upload-card__linked-file">
                            <button
                              type="button"
                              className="company-contract-upload-card__file-link"
                              onClick={() => void openEvidenceAsset(state.assetId, state.fileName)}
                              disabled={previewingAssetId === state.assetId}
                            >
                              {previewingAssetId === state.assetId ? "打开中..." : state.fileName}
                            </button>
                            <a
                              className="company-contract-upload-card__file-download"
                              href={evidenceAssetDownloadUrl(state.assetId)}
                              target="_blank"
                              rel="noreferrer"
                            >
                              <Icon name="download" size={14} />
                              <span>下载</span>
                            </a>
                          </span>
                        ) : state.cleared ? (
                          <span>已清空附件</span>
                        ) : (
                          <span>仅支持 PDF</span>
                        )}
                      </div>
                      <input
                        type="file"
                        accept=".pdf"
                        aria-label={field.label}
                        onChange={(event) => handleContractFileChange(field.key, event.target.files?.[0] ?? null)}
                      />
                      <div className="company-contract-upload-card__actions">
                        <ClayButton
                          type="button"
                          variant="outline"
                          onClick={() => void uploadContractAttachment(field.key)}
                          disabled={!selectedLibraryId || !state.file || state.uploading}
                        >
                          {state.uploading ? "上传中..." : hasLinkedAsset ? "替换 PDF" : "上传 PDF"}
                        </ClayButton>
                        <ClayButton
                          type="button"
                          variant="ghost"
                          onClick={() => clearContractAttachment(field.key)}
                          disabled={state.uploading || (!state.file && !hasLinkedAsset && !state.cleared)}
                        >
                          清空附件
                        </ClayButton>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="company-contract-actions">
                <ClayButton type="submit" disabled={!selectedLibraryId || savingContract || !contractForm.contractName.trim() || !contractForm.partyACompany.trim()}>
                  {savingContract ? "保存中..." : editingPerformanceId ? "保存修改" : "新增合同业绩"}
                </ClayButton>
                {editingPerformanceId ? (
                  <ClayButton type="button" variant="ghost" onClick={resetContractEditor}>
                    取消编辑
                  </ClayButton>
                ) : null}
              </div>
            </form>

            {error && <p className="text-error">{error}</p>}

            <div className="company-contract-table-wrap">
              <table className="data-table company-contract-table">
                <thead>
                  <tr>
                    <th>自动编号</th>
                    <th>合同名称</th>
                    <th>合同甲方单位</th>
                    <th>合同类别</th>
                    <th>工程类别</th>
                    <th>合同金额</th>
                    <th>合同签订日期</th>
                    <th>合同竣工日期</th>
                    <th>合同状态</th>
                    <th>附件状态</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {performances.map((row) => {
                    const attachmentCount = [
                      row.signature_asset_id,
                      row.invoice_asset_id,
                      row.invoice_verification_asset_id,
                      row.performance_evaluation_asset_id,
                    ].filter(Boolean).length;
                    return (
                      <tr key={row.id}>
                        <td>{row.auto_number}</td>
                        <td>{row.contract_name}</td>
                        <td>{row.party_a_company}</td>
                        <td>{row.contract_category || "未填"}</td>
                        <td>{row.engineering_category || "未填"}</td>
                        <td>{formatAmountCell(row.contract_amount)}</td>
                        <td>{formatDateCell(row.contract_signed_date)}</td>
                        <td>{formatDateCell(row.contract_completed_date)}</td>
                        <td>{row.contract_status || "未填"}</td>
                        <td>{attachmentCount}/4 已上传</td>
                        <td>
                          <div className="company-contract-table__actions">
                            <ClayButton type="button" size="sm" variant="outline" onClick={() => handleEditPerformance(row)}>
                              编辑
                            </ClayButton>
                            <ClayButton
                              type="button"
                              size="sm"
                              variant="ghost"
                              disabled={deletingPerformanceId === row.id}
                              onClick={() => void handleDeletePerformance(row.id)}
                            >
                              {deletingPerformanceId === row.id ? "删除中..." : "删除"}
                            </ClayButton>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                  {performances.length === 0 && (
                    <tr>
                      <td colSpan={11}>
                        <div className="template-strip-empty">当前公司库还没有合同业绩台账记录。</div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
