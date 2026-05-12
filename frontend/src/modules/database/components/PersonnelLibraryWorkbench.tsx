import { useEffect, useMemo, useState } from "react";

import { Badge } from "../../../components/ui/Badge";
import { Card } from "../../../components/ui/Card";
import { ClayButton } from "../../../components/ui/ClayButton";
import { ConfirmDialog } from "../../../components/ui/ConfirmDialog";
import type {
  EvidenceAsset,
  LibraryCompany,
  PersonProfile,
  PersonProfilePayload,
  PersonProfileWithAttachments,
} from "../../../lib/api";
import {
  createPerson,
  deleteEvidenceAsset,
  deletePerson,
  evidenceAssetDownloadUrl,
  fetchAssetTaxonomy,
  fetchEvidenceAssets,
  fetchLibraryCompanies,
  fetchPeople,
  getAuthHeaders,
  replaceEvidenceAssetFile,
  updatePerson,
  uploadEvidenceAsset,
} from "../../../lib/api";

type PersonFormState = {
  full_name: string;
  gender: string;
  age: string;
  education: string;
  title: string;
  role_name: string;
  specialty: string;
  years_experience: string;
  phone: string;
  email: string;
  resume_text: string;
  tags: string;
};

const EMPTY_PERSON_FORM: PersonFormState = {
  full_name: "",
  gender: "",
  age: "",
  education: "",
  title: "",
  role_name: "",
  specialty: "",
  years_experience: "",
  phone: "",
  email: "",
  resume_text: "",
  tags: "",
};

const PERSONNEL_ATTACHMENT_CATEGORIES = [
  ["performance_table", "业绩表"],
  ["id_card", "身份证"],
  ["graduation_certificate", "毕业证"],
  ["title_certificate", "职称证"],
  ["practice_certificate", "执业资格证"],
  ["safety_certificate", "安全生产合格证"],
  ["special_operation_certificate", "特种作业操作证"],
  ["social_security_proof", "社保参保证明"],
  ["labor_contract", "劳动合同书"],
] as const;

const CATEGORY_LABELS = Object.fromEntries(PERSONNEL_ATTACHMENT_CATEGORIES) as Record<string, string>;

function formFromPerson(person: PersonProfile | null): PersonFormState {
  const profile = person?.profile_json ?? {};
  const tags = Array.isArray(profile.tags) ? profile.tags.join("，") : "";
  return {
    full_name: person?.full_name ?? "",
    gender: person?.gender ?? "",
    age: person?.age == null ? "" : String(person.age),
    education: person?.education ?? "",
    title: person?.title ?? "",
    role_name: person?.role_name ?? "",
    specialty: person?.specialty ?? "",
    years_experience: person?.years_experience == null ? "" : String(person.years_experience),
    phone: person?.phone ?? "",
    email: person?.email ?? "",
    resume_text: person?.resume_text ?? "",
    tags,
  };
}

function nullableText(value: string): string | null {
  const cleaned = value.trim();
  return cleaned ? cleaned : null;
}

function nullableNumber(value: string): number | null {
  const cleaned = value.trim();
  if (!cleaned) return null;
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}

function buildPersonPayload(libraryCompanyId: string, form: PersonFormState): PersonProfilePayload {
  return {
    library_company_id: libraryCompanyId,
    full_name: form.full_name.trim(),
    gender: nullableText(form.gender),
    age: nullableNumber(form.age),
    education: nullableText(form.education),
    title: nullableText(form.title),
    role_name: nullableText(form.role_name),
    specialty: nullableText(form.specialty),
    years_experience: nullableNumber(form.years_experience),
    phone: nullableText(form.phone),
    email: nullableText(form.email),
    resume_text: nullableText(form.resume_text),
    profile_json: {
      tags: form.tags
        .split(/[，,]/u)
        .map((item) => item.trim())
        .filter(Boolean),
    },
  };
}

function certStatus(attachments: EvidenceAsset[]): { label: string; variant: "default" | "warning" | "danger" | "success" } {
  const expiring = attachments.some((asset) => {
    if (!asset.expires_on) return false;
    const diff = new Date(asset.expires_on).getTime() - Date.now();
    return diff >= 0 && diff <= 1000 * 60 * 60 * 24 * 60;
  });
  const expired = attachments.some((asset) => asset.expires_on && new Date(asset.expires_on).getTime() < Date.now());
  if (expired) return { label: "有过期", variant: "danger" };
  if (expiring) return { label: "临期", variant: "warning" };
  if (attachments.length > 0) return { label: "已上传", variant: "success" };
  return { label: "无附件", variant: "default" };
}

export function PersonnelLibraryWorkbench() {
  const [libraries, setLibraries] = useState<LibraryCompany[]>([]);
  const [people, setPeople] = useState<PersonProfileWithAttachments[]>([]);
  const [selectedLibraryId, setSelectedLibraryId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingPerson, setEditingPerson] = useState<PersonProfileWithAttachments | null>(null);
  const [form, setForm] = useState<PersonFormState>(EMPTY_PERSON_FORM);
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<PersonProfileWithAttachments | null>(null);
  const [attachmentCategory, setAttachmentCategory] = useState("id_card");
  const [attachmentName, setAttachmentName] = useState("");
  const [attachmentFile, setAttachmentFile] = useState<File | null>(null);
  const [attachmentIssuer, setAttachmentIssuer] = useState("");
  const [attachmentIssuedOn, setAttachmentIssuedOn] = useState("");
  const [attachmentExpiresOn, setAttachmentExpiresOn] = useState("");
  const [attachmentCertNo, setAttachmentCertNo] = useState("");
  const [attachmentDeleteTarget, setAttachmentDeleteTarget] = useState<EvidenceAsset | null>(null);
  const [replacingAttachmentId, setReplacingAttachmentId] = useState("");

  const loadPeople = async (libraryCompanyId: string) => {
    const [personRows, assetRows] = await Promise.all([
      fetchPeople({ libraryCompanyId }),
      fetchEvidenceAssets({ libraryCompanyId, assetDomain: "personnel" }),
    ]);
    const attachmentsByPerson = new Map<string, EvidenceAsset[]>();
    for (const asset of assetRows) {
      if (asset.owner_type !== "person_profile" || !asset.owner_id) continue;
      const bucket = attachmentsByPerson.get(asset.owner_id) ?? [];
      bucket.push(asset);
      attachmentsByPerson.set(asset.owner_id, bucket);
    }
    setPeople(personRows.map((person) => ({ ...person, attachments: attachmentsByPerson.get(person.id) ?? [] })));
  };

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
      return;
    }
    void loadPeople(selectedLibraryId).catch((err: unknown) => setError(err instanceof Error ? err.message : "加载人员资料失败"));
  }, [selectedLibraryId]);

  const roleOptions = useMemo(() => {
    return Array.from(new Set(people.map((person) => person.role_name).filter(Boolean) as string[]));
  }, [people]);

  const filteredPeople = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return people.filter((person) => {
      if (roleFilter && person.role_name !== roleFilter) return false;
      if (!keyword) return true;
      return [person.full_name, person.role_name, person.specialty, person.title, person.phone]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword));
    });
  }, [people, roleFilter, search]);

  const resetDrawer = () => {
    setDrawerOpen(false);
    setEditingPerson(null);
    setForm(EMPTY_PERSON_FORM);
    setAttachmentCategory("id_card");
    setAttachmentName("");
    setAttachmentFile(null);
    setAttachmentIssuer("");
    setAttachmentIssuedOn("");
    setAttachmentExpiresOn("");
    setAttachmentCertNo("");
    setAttachmentDeleteTarget(null);
    setReplacingAttachmentId("");
  };

  const openCreateDrawer = () => {
    setEditingPerson(null);
    setForm(EMPTY_PERSON_FORM);
    setDrawerOpen(true);
  };

  const openEditDrawer = (person: PersonProfileWithAttachments) => {
    setEditingPerson(person);
    setForm(formFromPerson(person));
    setDrawerOpen(true);
  };

  const uploadPersonAttachment = async (person: PersonProfile, file: File) => {
    await uploadEvidenceAsset({
      library_company_id: selectedLibraryId,
      owner_type: "person_profile",
      owner_id: person.id,
      asset_name: attachmentName.trim() || `${person.full_name}-${CATEGORY_LABELS[attachmentCategory] ?? "附件"}`,
      asset_domain: "personnel",
      asset_category: attachmentCategory,
      issuer_name: nullableText(attachmentIssuer) ?? undefined,
      issued_on: attachmentIssuedOn || undefined,
      expires_on: attachmentExpiresOn || undefined,
      metadata_json: { cert_no: nullableText(attachmentCertNo) },
      file,
    });
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!selectedLibraryId || !form.full_name.trim()) return;
    setSaving(true);
    try {
      const payload = buildPersonPayload(selectedLibraryId, form);
      const saved = editingPerson ? await updatePerson(editingPerson.id, payload) : await createPerson(payload);
      if (attachmentFile) {
        await uploadPersonAttachment(saved, attachmentFile);
      }
      await loadPeople(selectedLibraryId);
      resetDrawer();
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "保存人员资料失败");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget || !selectedLibraryId) return;
    try {
      await deletePerson(deleteTarget.id);
      await loadPeople(selectedLibraryId);
      setDeleteTarget(null);
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "删除人员失败");
    }
  };

  const handleDeleteAttachment = async () => {
    if (!attachmentDeleteTarget || !selectedLibraryId) return;
    try {
      await deleteEvidenceAsset(attachmentDeleteTarget.id);
      await loadPeople(selectedLibraryId);
      if (editingPerson) {
        setEditingPerson((current) => {
          if (!current) return current;
          return {
            ...current,
            attachments: current.attachments.filter((asset) => asset.id !== attachmentDeleteTarget.id),
          };
        });
      }
      setAttachmentDeleteTarget(null);
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "删除人员附件失败");
    }
  };

  const handleReplaceAttachment = async (asset: EvidenceAsset, file: File | null) => {
    if (!file || !selectedLibraryId) return;
    setReplacingAttachmentId(asset.id);
    try {
      const updated = await replaceEvidenceAssetFile(asset.id, file);
      await loadPeople(selectedLibraryId);
      setEditingPerson((current) => {
        if (!current) return current;
        return {
          ...current,
          attachments: current.attachments.map((item) => (item.id === updated.id ? updated : item)),
        };
      });
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "替换人员附件失败");
    } finally {
      setReplacingAttachmentId("");
    }
  };

  const openAttachment = async (asset: EvidenceAsset) => {
    try {
      const response = await fetch(evidenceAssetDownloadUrl(asset.id), { headers: getAuthHeaders() });
      if (!response.ok) throw new Error(await response.text());
      const blob = await response.blob();
      const blobUrl = URL.createObjectURL(blob);
      window.open(blobUrl, "_blank", "noopener,noreferrer");
      window.setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "打开人员附件失败");
    }
  };

  const updateForm = (key: keyof PersonFormState, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  return (
    <div className="stack">
      <Card>
        <div className="panel-header-split panel-header-split--center">
          <div>
            <h3 className="panel-title-tight">人员资料库</h3>
            <p className="subtle-copy">按公司维护人员台账，人员信息和证件附件归到同一条记录下。</p>
          </div>
          <div className="personnel-toolbar-actions">
            <select className="clay-input min-w-company-select" aria-label="选择公司库" value={selectedLibraryId} onChange={(event) => setSelectedLibraryId(event.target.value)}>
              <option value="">选择公司库</option>
              {libraries.map((row) => (
                <option key={row.id} value={row.id}>{row.company_name}</option>
              ))}
            </select>
            <ClayButton type="button" onClick={openCreateDrawer} disabled={!selectedLibraryId}>新增人员</ClayButton>
          </div>
        </div>

        <div className="asset-toolbar__filters personnel-toolbar-filters">
          <input className="clay-input" aria-label="搜索人员" placeholder="搜索姓名、岗位、专业、电话" value={search} onChange={(event) => setSearch(event.target.value)} />
          <select className="clay-input" aria-label="岗位筛选" value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}>
            <option value="">全部岗位</option>
            {roleOptions.map((role) => <option key={role} value={role}>{role}</option>)}
          </select>
          <ClayButton type="button" variant="outline" onClick={() => selectedLibraryId && void loadPeople(selectedLibraryId)}>刷新</ClayButton>
        </div>

        {loading ? (
          <div className="skeleton-stack" aria-label="人员资料库加载中">
            <div className="skeleton-card" />
            <div className="skeleton-card" />
          </div>
        ) : (
          <div className="personnel-table-wrap">
            <table className="asset-table personnel-table">
              <thead>
                <tr>
                  <th>姓名</th>
                  <th>拟任岗位</th>
                  <th>专业</th>
                  <th>职称</th>
                  <th>学历</th>
                  <th>年限</th>
                  <th>联系方式</th>
                  <th>附件</th>
                  <th>证件状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {filteredPeople.map((person) => {
                  const status = certStatus(person.attachments);
                  return (
                    <tr key={person.id}>
                      <td>{person.full_name}</td>
                      <td>{person.role_name || "—"}</td>
                      <td>{person.specialty || "—"}</td>
                      <td>{person.title || "—"}</td>
                      <td>{person.education || "—"}</td>
                      <td>{person.years_experience == null ? "—" : `${person.years_experience} 年`}</td>
                      <td>{person.phone || person.email || "—"}</td>
                      <td>
                        {person.attachments.length > 0 ? (
                          <div className="asset-table__attachments">
                            {person.attachments.map((asset) => (
                              <button key={asset.id} type="button" className="attachment-link asset-table__attachment-link" onClick={() => void openAttachment(asset)}>
                                {CATEGORY_LABELS[asset.asset_category] ?? asset.asset_category}: {asset.file_name}
                              </button>
                            ))}
                          </div>
                        ) : "—"}
                      </td>
                      <td><Badge variant={status.variant}>{status.label}</Badge></td>
                      <td>
                        <div className="asset-table__actions">
                          <ClayButton type="button" variant="outline" size="sm" onClick={() => openEditDrawer(person)}>编辑</ClayButton>
                          <ClayButton type="button" variant="danger" size="sm" onClick={() => setDeleteTarget(person)}>删除</ClayButton>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {filteredPeople.length === 0 && <div className="template-strip-empty">当前公司库还没有匹配的人员记录。</div>}
          </div>
        )}

        {error && <p className="text-error">{error}</p>}
      </Card>

      {drawerOpen ? (
        <div className="asset-drawer-backdrop" role="presentation" onClick={resetDrawer}>
          <div className="asset-drawer personnel-drawer" role="dialog" aria-modal="true" aria-label="人员资料表单" onClick={(event) => event.stopPropagation()}>
            <div className="asset-drawer__header">
              <div>
                <h3 className="panel-title-tight">{editingPerson ? "编辑人员" : "新增人员"}</h3>
                <p className="subtle-copy">维护人员信息，并上传身份证、证书、社保或劳动合同等附件。</p>
              </div>
              <ClayButton type="button" variant="ghost" onClick={resetDrawer}>关闭</ClayButton>
            </div>

            <form className="asset-drawer__form" onSubmit={handleSubmit}>
              <div className="asset-drawer__section">
                <h4 className="panel-title-tight">基础信息</h4>
                <div className="form-grid-two">
                  <input className="clay-input" aria-label="姓名" placeholder="姓名" value={form.full_name} onChange={(event) => updateForm("full_name", event.target.value)} />
                  <select className="clay-input" aria-label="性别" value={form.gender} onChange={(event) => updateForm("gender", event.target.value)}>
                    <option value="">性别</option>
                    <option value="男">男</option>
                    <option value="女">女</option>
                  </select>
                  <input className="clay-input" aria-label="年龄" inputMode="numeric" placeholder="年龄" value={form.age} onChange={(event) => updateForm("age", event.target.value)} />
                  <input className="clay-input" aria-label="学历" placeholder="学历" value={form.education} onChange={(event) => updateForm("education", event.target.value)} />
                  <input className="clay-input" aria-label="职称" placeholder="职称" value={form.title} onChange={(event) => updateForm("title", event.target.value)} />
                  <input className="clay-input" aria-label="拟任岗位" placeholder="拟任岗位" value={form.role_name} onChange={(event) => updateForm("role_name", event.target.value)} />
                  <input className="clay-input" aria-label="专业" placeholder="专业" value={form.specialty} onChange={(event) => updateForm("specialty", event.target.value)} />
                  <input className="clay-input" aria-label="从业年限" inputMode="numeric" placeholder="从业年限" value={form.years_experience} onChange={(event) => updateForm("years_experience", event.target.value)} />
                  <input className="clay-input" aria-label="电话" placeholder="电话" value={form.phone} onChange={(event) => updateForm("phone", event.target.value)} />
                  <input className="clay-input" aria-label="邮箱" placeholder="邮箱" value={form.email} onChange={(event) => updateForm("email", event.target.value)} />
                </div>
              </div>

              <div className="asset-drawer__section">
                <h4 className="panel-title-tight">附件</h4>
                {editingPerson?.attachments.length ? (
                  <div className="asset-drawer__attachment-list">
                    {editingPerson.attachments.map((asset) => (
                      <div key={asset.id} className="asset-drawer__attachment-row">
                        <button type="button" className="attachment-link asset-drawer__attachment-link" onClick={() => void openAttachment(asset)}>
                          {CATEGORY_LABELS[asset.asset_category] ?? asset.asset_category}: {asset.file_name}
                        </button>
                        <div className="asset-drawer__attachment-actions">
                          <label className="asset-drawer__attachment-action">
                            <input
                              type="file"
                              accept=".pdf,image/*"
                              onChange={(event) => void handleReplaceAttachment(asset, event.target.files?.[0] ?? null)}
                              disabled={replacingAttachmentId === asset.id}
                            />
                            <span>{replacingAttachmentId === asset.id ? "替换中..." : "替换"}</span>
                          </label>
                          <button type="button" className="asset-drawer__attachment-danger" onClick={() => setAttachmentDeleteTarget(asset)}>
                            删除
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : <p className="subtle-copy">当前还没有人员附件。</p>}
                <div className="form-grid-two">
                  <input className="clay-input" aria-label="人员附件名称" placeholder="附件名称" value={attachmentName} onChange={(event) => setAttachmentName(event.target.value)} />
                  <select className="clay-input" aria-label="人员附件分类" value={attachmentCategory} onChange={(event) => setAttachmentCategory(event.target.value)}>
                    {PERSONNEL_ATTACHMENT_CATEGORIES.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
                  </select>
                  <input className="clay-input" aria-label="发证机构" placeholder="发证机构" value={attachmentIssuer} onChange={(event) => setAttachmentIssuer(event.target.value)} />
                  <input className="clay-input" aria-label="证书编号" placeholder="证书编号" value={attachmentCertNo} onChange={(event) => setAttachmentCertNo(event.target.value)} />
                  <input className="clay-input" type="date" aria-label="发证日期" value={attachmentIssuedOn} onChange={(event) => setAttachmentIssuedOn(event.target.value)} />
                  <input className="clay-input" type="date" aria-label="有效期" value={attachmentExpiresOn} onChange={(event) => setAttachmentExpiresOn(event.target.value)} />
                  <input className="personnel-file-input" type="file" accept=".pdf,image/*" aria-label="选择人员附件文件" onChange={(event) => setAttachmentFile(event.target.files?.[0] ?? null)} />
                </div>
              </div>

              <div className="asset-drawer__section">
                <h4 className="panel-title-tight">补充信息</h4>
                <input className="clay-input" aria-label="能力标签" placeholder="能力标签，用逗号分隔" value={form.tags} onChange={(event) => updateForm("tags", event.target.value)} />
                <textarea className="clay-input asset-drawer__notes" aria-label="简历说明" placeholder="简历、项目经历或备注" value={form.resume_text} onChange={(event) => updateForm("resume_text", event.target.value)} />
              </div>

              <div className="asset-drawer__actions">
                <ClayButton type="button" variant="outline" onClick={resetDrawer}>取消</ClayButton>
                <ClayButton type="submit" disabled={saving || !form.full_name.trim()}>
                  {saving ? "保存中..." : editingPerson ? "保存修改" : "创建人员"}
                </ClayButton>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      <ConfirmDialog
        open={deleteTarget != null}
        title="删除人员"
        description={deleteTarget ? `确认删除人员“${deleteTarget.full_name}”？关联附件会保留在资料库中，后续可做附件清理。` : ""}
        confirmLabel="删除"
        confirmVariant="danger"
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => void handleDelete()}
      />

      <ConfirmDialog
        open={attachmentDeleteTarget != null}
        title="删除人员附件"
        description={attachmentDeleteTarget ? `确认删除附件“${attachmentDeleteTarget.file_name}”？文件记录会从资料库移除。` : ""}
        confirmLabel="删除"
        confirmVariant="danger"
        onCancel={() => setAttachmentDeleteTarget(null)}
        onConfirm={() => void handleDeleteAttachment()}
      />
    </div>
  );
}
