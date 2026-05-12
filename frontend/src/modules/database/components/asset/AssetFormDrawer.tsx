import { useEffect, useState } from "react";

import { ClayButton } from "../../../../components/ui/ClayButton";
import type {
  CompanyAsset,
  CompanyAssetOwnership,
  CompanyAssetPayload,
  CompanyAssetStatus,
  CompanyAssetType,
  EvidenceAsset,
} from "../../../../lib/api";
import { ASSET_TYPE_SCHEMAS } from "../../schemas/assetTypeSchemas";

type AssetFormDrawerProps = {
  open: boolean;
  assetType: CompanyAssetType;
  asset: CompanyAsset | null;
  attachments: EvidenceAsset[];
  saving: boolean;
  onClose: () => void;
  onOpenAttachment: (attachment: EvidenceAsset) => Promise<void> | void;
  onSubmit: (payload: CompanyAssetPayload, attachmentFile: File | null) => Promise<void> | void;
};

type FormState = {
  name: string;
  spec_model: string;
  serial_no: string;
  manufacturer: string;
  quantity: string;
  unit: string;
  ownership: CompanyAssetOwnership;
  acquired_at: string;
  expires_at: string;
  technical_condition: string;
  status: CompanyAssetStatus;
  location: string;
  notes: string;
  extras: Record<string, string>;
};

function buildInitialState(assetType: CompanyAssetType, asset: CompanyAsset | null): FormState {
  const schema = ASSET_TYPE_SCHEMAS[assetType];
  const extras = Object.fromEntries(schema.extras.map((field) => [field.key, String(asset?.extras[field.key] ?? "")]));
  return {
    name: asset?.name ?? "",
    spec_model: asset?.spec_model ?? "",
    serial_no: asset?.serial_no ?? "",
    manufacturer: asset?.manufacturer ?? "",
    quantity: asset?.quantity ?? "1",
    unit: asset?.unit ?? schema.unitDefault,
    ownership: asset?.ownership ?? "self",
    acquired_at: asset?.acquired_at ?? "",
    expires_at: asset?.expires_at ?? "",
    technical_condition: asset?.technical_condition ?? "",
    status: asset?.status ?? "active",
    location: asset?.location ?? "",
    notes: asset?.notes ?? "",
    extras,
  };
}

export function AssetFormDrawer({
  open,
  assetType,
  asset,
  attachments,
  saving,
  onClose,
  onOpenAttachment,
  onSubmit,
}: AssetFormDrawerProps) {
  const [form, setForm] = useState<FormState>(() => buildInitialState(assetType, asset));
  const [attachmentFile, setAttachmentFile] = useState<File | null>(null);
  const schema = ASSET_TYPE_SCHEMAS[assetType];

  useEffect(() => {
    setForm(buildInitialState(assetType, asset));
    setAttachmentFile(null);
  }, [assetType, asset, open]);

  if (!open) return null;

  const updateField = (key: keyof Omit<FormState, "extras">, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const updateExtra = (key: string, value: string) => {
    setForm((current) => ({
      ...current,
      extras: { ...current.extras, [key]: value },
    }));
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    await onSubmit({
      asset_type: assetType,
      name: form.name.trim(),
      spec_model: form.spec_model.trim() || null,
      serial_no: form.serial_no.trim() || null,
      manufacturer: form.manufacturer.trim() || null,
      quantity: form.quantity.trim() || "1",
      unit: form.unit.trim(),
      ownership: form.ownership,
      acquired_at: form.acquired_at || null,
      expires_at: form.expires_at || null,
      technical_condition: form.technical_condition.trim() || null,
      status: form.status,
      location: form.location.trim() || null,
      notes: form.notes.trim() || null,
      extras: Object.fromEntries(Object.entries(form.extras).filter(([, value]) => value.trim() !== "")),
    }, attachmentFile);
  };

  return (
    <div className="asset-drawer-backdrop" role="presentation" onClick={onClose}>
      <div className="asset-drawer" role="dialog" aria-modal="true" aria-label={`${schema.label}表单`} onClick={(event) => event.stopPropagation()}>
        <div className="asset-drawer__header">
          <div>
            <h3 className="panel-title-tight">{asset ? `编辑${schema.label}` : `新增${schema.label}`}</h3>
            <p className="subtle-copy">录入公共字段和当前类别的关键特化字段。</p>
          </div>
          <ClayButton type="button" variant="ghost" onClick={onClose}>关闭</ClayButton>
        </div>

        <form className="asset-drawer__form" onSubmit={handleSubmit}>
          <div className="form-grid-two">
            <input className="clay-input" aria-label="名称" placeholder="名称" value={form.name} onChange={(event) => updateField("name", event.target.value)} />
            <input className="clay-input" aria-label="规格型号" placeholder="规格型号" value={form.spec_model} onChange={(event) => updateField("spec_model", event.target.value)} />
            <input className="clay-input" aria-label="编号" placeholder="编号/车牌/出厂编号" value={form.serial_no} onChange={(event) => updateField("serial_no", event.target.value)} />
            <input className="clay-input" aria-label="生产厂家" placeholder="生产厂家" value={form.manufacturer} onChange={(event) => updateField("manufacturer", event.target.value)} />
            <input className="clay-input" aria-label="数量" inputMode="decimal" placeholder="数量" value={form.quantity} onChange={(event) => updateField("quantity", event.target.value)} />
            <input className="clay-input" aria-label="单位" placeholder="单位" value={form.unit} onChange={(event) => updateField("unit", event.target.value)} />
            <select className="clay-input" aria-label="所有权" value={form.ownership} onChange={(event) => updateField("ownership", event.target.value)}>
              <option value="self">自有</option>
              <option value="leased">租赁</option>
              <option value="third_party">第三方</option>
            </select>
            <select className="clay-input" aria-label="状态" value={form.status} onChange={(event) => updateField("status", event.target.value)}>
              <option value="active">在用</option>
              <option value="maintenance">检修中</option>
              <option value="retired">已退役</option>
            </select>
            <input className="clay-input" type="date" aria-label="购置日期" value={form.acquired_at} onChange={(event) => updateField("acquired_at", event.target.value)} />
            <input className="clay-input" type="date" aria-label="有效期" value={form.expires_at} onChange={(event) => updateField("expires_at", event.target.value)} />
            <input className="clay-input" aria-label="技术状况" placeholder="技术状况" value={form.technical_condition} onChange={(event) => updateField("technical_condition", event.target.value)} />
            <input className="clay-input" aria-label="存放地点" placeholder="存放地点" value={form.location} onChange={(event) => updateField("location", event.target.value)} />
          </div>

          <div className="asset-drawer__section">
            <h4 className="panel-title-tight">类别字段</h4>
            <div className="form-grid-two">
              {schema.extras.map((field) => (
                field.type === "select" ? (
                  <select key={field.key} className="clay-input" aria-label={field.label} value={form.extras[field.key] ?? ""} onChange={(event) => updateExtra(field.key, event.target.value)}>
                    <option value="">{field.label}</option>
                    {field.options?.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    key={field.key}
                    className="clay-input"
                    type={field.type === "date" ? "date" : "text"}
                    aria-label={field.label}
                    placeholder={field.label}
                    value={form.extras[field.key] ?? ""}
                    onChange={(event) => updateExtra(field.key, event.target.value)}
                  />
                )
              ))}
            </div>
          </div>

          <div className="asset-drawer__section">
            <h4 className="panel-title-tight">附件</h4>
            {attachments.length > 0 ? (
              <div className="asset-drawer__attachment-list">
                {attachments.map((attachment) => (
                  <button
                    key={attachment.id}
                    type="button"
                    className="asset-drawer__attachment-link"
                    onClick={() => void onOpenAttachment(attachment)}
                  >
                    {attachment.file_name}
                  </button>
                ))}
              </div>
            ) : (
              <p className="subtle-copy">当前还没有上传附件。</p>
            )}
            <input
              className="asset-drawer__file-input"
              type="file"
              accept=".pdf,image/*"
              aria-label="资产附件"
              onChange={(event) => setAttachmentFile(event.target.files?.[0] ?? null)}
            />
            <p className="subtle-copy">
              支持上传 PDF 或图片。{asset ? "保存后将追加为新的关联附件。" : "创建资产后会自动上传并关联该附件。"}
            </p>
          </div>

          <textarea className="clay-textarea asset-drawer__notes" aria-label="备注" placeholder="备注" value={form.notes} onChange={(event) => updateField("notes", event.target.value)} />

          <div className="asset-drawer__actions">
            <ClayButton type="button" variant="outline" onClick={onClose}>取消</ClayButton>
            <ClayButton type="submit" disabled={saving || !form.name.trim() || !form.unit.trim()}>
              {saving ? "保存中..." : asset ? "保存修改" : "创建资产"}
            </ClayButton>
          </div>
        </form>
      </div>
    </div>
  );
}
