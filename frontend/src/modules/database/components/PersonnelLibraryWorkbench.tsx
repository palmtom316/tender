import { useEffect, useState } from "react";

import { Card } from "../../../components/ui/Card";
import { ClayButton } from "../../../components/ui/ClayButton";
import type { EvidenceAsset, LibraryCompany, PersonProfile } from "../../../lib/api";
import {
  fetchAssetTaxonomy,
  fetchEvidenceAssets,
  fetchLibraryCompanies,
  fetchPeople,
  uploadEvidenceAsset,
} from "../../../lib/api";

export function PersonnelLibraryWorkbench() {
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
    <div className="stack">
      <Card>
        <div className="panel-header-split panel-header-split--center">
          <div>
            <h3 className="panel-title-tight">人员资料库</h3>
            <p className="subtle-copy">按公司维度管理人员档案，并把身份证、资格证、社保、劳动合同等文件直接归到个人名下。</p>
          </div>
          <select className="clay-input min-w-company-select" aria-label="选择公司库" value={selectedLibraryId} onChange={(event) => setSelectedLibraryId(event.target.value)}>
            <option value="">选择公司库</option>
            {libraries.map((row) => (
              <option key={row.id} value={row.id}>{row.company_name}</option>
            ))}
          </select>
        </div>

        {loading ? (
          <div className="skeleton-stack" aria-label="人员资料库加载中">
            <div className="skeleton-card" />
            <div className="skeleton-card" />
          </div>
        ) : (
          <div className="split-panel-grid split-panel-grid--wide-rail">
            <div>
              <h4 className="panel-title-tight">人员清单</h4>
              <div className="stack-sm">
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
              <form onSubmit={handleUpload} className="form-grid-two">
                <input className="clay-input" aria-label="人员资料名称" placeholder="资料名称" value={uploadName} onChange={(event) => setUploadName(event.target.value)} />
                <select className="clay-input" aria-label="选择人员" value={selectedPersonId} onChange={(event) => setSelectedPersonId(event.target.value)}>
                  <option value="">选择人员</option>
                  {people.map((row) => (
                    <option key={row.id} value={row.id}>{row.full_name}</option>
                  ))}
                </select>
                <select className="clay-input" aria-label="人员资料分类" value={uploadCategory} onChange={(event) => setUploadCategory(event.target.value)}>
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
                <input type="file" accept=".pdf,image/*" aria-label="选择人员资料文件" onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)} />
                <div className="form-grid-full">
                  <ClayButton type="submit" disabled={!selectedPersonId || !uploadFile || !uploadName.trim()}>
                    上传人员资料
                  </ClayButton>
                </div>
              </form>

              {error && <p className="text-error">{error}</p>}

              <div className="stack-sm">
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
