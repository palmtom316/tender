import type { CompanyAssetType, CompanyAssetWithAttachments, EvidenceAsset } from "../../../../lib/api";
import { Badge } from "../../../../components/ui/Badge";
import { ClayButton } from "../../../../components/ui/ClayButton";
import { ASSET_TYPE_SCHEMAS } from "../../schemas/assetTypeSchemas";
import { ExpiryBadge } from "./expiryBadge";

function ownershipLabel(value: CompanyAssetWithAttachments["ownership"]): string {
  if (value === "self") return "自有";
  if (value === "leased") return "租赁";
  return "第三方";
}

function statusVariant(value: CompanyAssetWithAttachments["status"]): "default" | "warning" | "success" {
  if (value === "maintenance") return "warning";
  if (value === "retired") return "default";
  return "success";
}

function statusLabel(value: CompanyAssetWithAttachments["status"]): string {
  if (value === "maintenance") return "检修中";
  if (value === "retired") return "已退役";
  return "在用";
}

function extraValue(asset: CompanyAssetWithAttachments, key: string): string {
  const value = asset.extras[key];
  if (value == null || value === "") return "—";
  if (value === "yes") return "是";
  if (value === "no") return "否";
  return String(value);
}

type AssetTableProps = {
  assetType: CompanyAssetType;
  assets: CompanyAssetWithAttachments[];
  onEdit: (asset: CompanyAssetWithAttachments) => void;
  onRetire: (asset: CompanyAssetWithAttachments) => void;
  onDelete: (asset: CompanyAssetWithAttachments) => void;
  onOpenAttachment: (attachment: EvidenceAsset) => Promise<void> | void;
};

export function AssetTable({ assetType, assets, onEdit, onRetire, onDelete, onOpenAttachment }: AssetTableProps) {
  const schema = ASSET_TYPE_SCHEMAS[assetType];

  if (assets.length === 0) {
    return <div className="template-strip-empty">当前分类还没有资产记录。</div>;
  }

  return (
    <div className="asset-table-wrap">
      <table className="asset-table">
        <thead>
          <tr>
            <th>名称</th>
            <th>规格型号</th>
            <th>数量</th>
            <th>所有权</th>
            {schema.columns.map((column) => (
              <th key={column.key}>{column.label}</th>
            ))}
            <th>附件</th>
            <th>有效期</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {assets.map((asset) => (
            <tr key={asset.id}>
              <td>{asset.name}</td>
              <td>{asset.spec_model || "—"}</td>
              <td>{asset.quantity} {asset.unit}</td>
              <td>{ownershipLabel(asset.ownership)}</td>
              {schema.columns.map((column) => (
                <td key={column.key}>
                  {column.key === "serial_no"
                    ? asset.serial_no || "—"
                    : column.key === "technical_condition"
                      ? asset.technical_condition || "—"
                      : extraValue(asset, column.key)}
                </td>
              ))}
              <td>
                {asset.attachments.length > 0 ? (
                  <div className="asset-table__attachments">
                    {asset.attachments.map((attachment) => (
                      <button
                        key={attachment.id}
                        type="button"
                        className="asset-table__attachment-link"
                        onClick={() => void onOpenAttachment(attachment)}
                      >
                        {attachment.file_name}
                      </button>
                    ))}
                  </div>
                ) : "—"}
              </td>
              <td><ExpiryBadge value={asset.expires_at} /></td>
              <td><Badge variant={statusVariant(asset.status)}>{statusLabel(asset.status)}</Badge></td>
              <td>
                <div className="asset-table__actions">
                  <ClayButton type="button" variant="outline" size="sm" onClick={() => onEdit(asset)}>编辑</ClayButton>
                  {asset.status !== "retired" && (
                    <ClayButton type="button" variant="ghost" size="sm" onClick={() => onRetire(asset)}>退役</ClayButton>
                  )}
                  <ClayButton type="button" variant="danger" size="sm" onClick={() => onDelete(asset)}>删除</ClayButton>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
