import { useCallback, useEffect, useState } from "react";

import { Card } from "../../../components/ui/Card";
import { ClayButton } from "../../../components/ui/ClayButton";
import type {
  AssetTaxonomyDomain,
  CompanyProfile,
  EvidenceAsset,
  LibraryCompany,
} from "../../../lib/api";
import {
  createLibraryCompany,
  fetchAssetTaxonomy,
  fetchCompanyProfiles,
  fetchEvidenceAssets,
  fetchLibraryCompanies,
  uploadEvidenceAsset,
} from "../../../lib/api";

export function CompanyLibraryWorkbench() {
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
          <div className="panel-header-split">
            <div>
              <h3 className="panel-title-tight">{selectedLibrary?.company_name || "未选择公司库"}</h3>
              <p className="subtle-copy">公司资料、业绩、资质、履约评价统一归档到本地复用库。</p>
            </div>
            <div className="summary-pill-row">
              <div className="template-summary__pill"><span>公司档案</span><strong>{profiles.length}</strong></div>
              <div className="template-summary__pill"><span>已上传资料</span><strong>{assets.length}</strong></div>
            </div>
          </div>

          <form onSubmit={handleUpload} className="form-grid-two">
            <input className="clay-input" aria-label="公司资料名称" placeholder="资料名称" value={uploadName} onChange={(event) => setUploadName(event.target.value)} />
            <select className="clay-input" aria-label="公司资料领域" value={uploadDomain} onChange={(event) => setUploadDomain(event.target.value)}>
              {taxonomy.filter((row) => row.domain !== "personnel").map((row) => (
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

          {error && <p className="text-error">{error}</p>}

          <div className="form-grid-two">
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
      </div>
    </div>
  );
}
