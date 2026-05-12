import { useEffect, useMemo, useState } from "react";

import { Card } from "../../../components/ui/Card";
import { ClayButton } from "../../../components/ui/ClayButton";
import { SegmentedTabs } from "../../../components/ui/SegmentedTabs";
import { ConfirmDialog } from "../../../components/ui/ConfirmDialog";
import type { CompanyAsset, CompanyAssetPayload, CompanyAssetStatus, CompanyAssetType, CompanyAssetWithAttachments, EvidenceAsset } from "../../../lib/api";
import {
  createCompanyAsset,
  deleteCompanyAsset,
  evidenceAssetDownloadUrl,
  fetchCompanyAssets,
  fetchEvidenceAssets,
  getAuthHeaders,
  retireCompanyAsset,
  updateCompanyAsset,
  uploadEvidenceAsset,
} from "../../../lib/api";
import { ASSET_TYPE_SCHEMAS } from "../schemas/assetTypeSchemas";
import { AssetFormDrawer } from "./asset/AssetFormDrawer";
import { AssetTable } from "./asset/AssetTable";

type CompanyAssetSectionProps = {
  libraryCompanyId: string;
  companyName: string;
  onError: (message: string) => void;
};

const ASSET_TABS: CompanyAssetType[] = ["vehicle", "machine", "tool", "safety"];

export function CompanyAssetSection({ libraryCompanyId, companyName, onError }: CompanyAssetSectionProps) {
  const [activeType, setActiveType] = useState<CompanyAssetType>("vehicle");
  const [statusFilter, setStatusFilter] = useState<CompanyAssetStatus | "">("");
  const [search, setSearch] = useState("");
  const [assets, setAssets] = useState<CompanyAssetWithAttachments[]>([]);
  const [loading, setLoading] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingAsset, setEditingAsset] = useState<CompanyAssetWithAttachments | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<CompanyAssetWithAttachments | null>(null);

  const loadAssets = async () => {
    setLoading(true);
    try {
      const [rows, attachmentRows] = await Promise.all([
        fetchCompanyAssets({
          libraryCompanyId,
          assetType: activeType,
          status: statusFilter,
          q: search,
        }),
        fetchEvidenceAssets({ libraryCompanyId, assetDomain: "company_asset" }),
      ]);
      const attachmentsByOwner = new Map<string, EvidenceAsset[]>();
      for (const attachment of attachmentRows) {
        if (attachment.owner_type !== "company_asset" || !attachment.owner_id) continue;
        const bucket = attachmentsByOwner.get(attachment.owner_id) ?? [];
        bucket.push(attachment);
        attachmentsByOwner.set(attachment.owner_id, bucket);
      }
      setAssets(rows.map((row) => ({ ...row, attachments: attachmentsByOwner.get(row.id) ?? [] })));
      onError("");
    } catch (err: unknown) {
      onError(err instanceof Error ? err.message : "加载公司资产失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAssets();
  }, [libraryCompanyId, activeType, statusFilter]);

  const counts = useMemo(() => {
    const base = Object.fromEntries(ASSET_TABS.map((type) => [type, 0])) as Record<CompanyAssetType, number>;
    for (const asset of assets) {
      base[asset.asset_type] = (base[asset.asset_type] ?? 0) + 1;
    }
    return base;
  }, [assets]);

  const uploadAssetAttachment = async (asset: CompanyAsset, file: File) => {
    await uploadEvidenceAsset({
      library_company_id: libraryCompanyId,
      owner_type: "company_asset",
      owner_id: asset.id,
      asset_name: `${asset.name}-附件`,
      asset_domain: "company_asset",
      asset_category: "construction_equipment_certificate",
      file,
    });
  };

  const openAssetAttachment = async (attachment: EvidenceAsset) => {
    const response = await fetch(evidenceAssetDownloadUrl(attachment.id), {
      headers: getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    window.open(blobUrl, "_blank", "noopener,noreferrer");
    window.setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
  };

  const handleSubmit = async (payload: CompanyAssetPayload, attachmentFile: File | null) => {
    setSaving(true);
    try {
      let saved: CompanyAsset;
      if (editingAsset) {
        saved = await updateCompanyAsset(editingAsset.id, payload);
      } else {
        saved = await createCompanyAsset(libraryCompanyId, payload);
      }
      if (attachmentFile) {
        await uploadAssetAttachment(saved, attachmentFile);
      }
      setDrawerOpen(false);
      setEditingAsset(null);
      await loadAssets();
    } catch (err: unknown) {
      onError(err instanceof Error ? err.message : "保存公司资产失败");
    } finally {
      setSaving(false);
    }
  };

  const handleRetire = async (asset: CompanyAsset) => {
    try {
      await retireCompanyAsset(asset.id);
      await loadAssets();
    } catch (err: unknown) {
      onError(err instanceof Error ? err.message : "退役资产失败");
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteCompanyAsset(deleteTarget.id);
      setDeleteTarget(null);
      await loadAssets();
    } catch (err: unknown) {
      onError(err instanceof Error ? err.message : "删除资产失败");
    }
  };

  return (
    <Card>
      <div className="template-panel__header">
        <div>
          <div className="template-panel__eyebrow">公司资产台账</div>
          <h2>公司资产</h2>
          <p className="template-panel__description">{companyName} 的设备、车辆和工器具台账。当前阶段以手工维护和可导出为主。</p>
        </div>
        <ClayButton
          type="button"
          onClick={() => {
            setEditingAsset(null);
            setDrawerOpen(true);
          }}
        >
          新增{ASSET_TYPE_SCHEMAS[activeType].label}
        </ClayButton>
      </div>

      <div className="asset-toolbar">
        <SegmentedTabs
          ariaLabel="资产分类"
          value={activeType}
          onChange={setActiveType}
          items={ASSET_TABS.map((type) => ({
            id: type,
            label: ASSET_TYPE_SCHEMAS[type].label,
            count: counts[type],
          }))}
        />

        <div className="asset-toolbar__filters">
          <input
            className="clay-input"
            aria-label="搜索资产"
            placeholder="搜索名称、规格型号、编号"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <select className="clay-input" aria-label="状态筛选" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as CompanyAssetStatus | "")}>
            <option value="">全部状态</option>
            <option value="active">在用</option>
            <option value="maintenance">检修中</option>
            <option value="retired">已退役</option>
          </select>
          <ClayButton type="button" variant="outline" onClick={() => void loadAssets()}>查询</ClayButton>
        </div>
      </div>

      {loading ? (
        <div className="skeleton-stack" aria-label="资产加载中">
          <div className="skeleton-card" />
          <div className="skeleton-card" />
        </div>
      ) : (
        <AssetTable
          assetType={activeType}
          assets={assets}
          onEdit={(asset) => {
            setEditingAsset(asset);
            setDrawerOpen(true);
          }}
          onRetire={(asset) => void handleRetire(asset)}
          onDelete={setDeleteTarget}
          onOpenAttachment={(attachment) => void openAssetAttachment(attachment).catch((err: unknown) => {
            onError(err instanceof Error ? err.message : "打开资产附件失败");
          })}
        />
      )}

      <AssetFormDrawer
        open={drawerOpen}
        assetType={activeType}
        asset={editingAsset}
        attachments={editingAsset?.attachments ?? []}
        saving={saving}
        onClose={() => {
          setDrawerOpen(false);
          setEditingAsset(null);
        }}
        onOpenAttachment={(attachment) => void openAssetAttachment(attachment).catch((err: unknown) => {
          onError(err instanceof Error ? err.message : "打开资产附件失败");
        })}
        onSubmit={handleSubmit}
      />

      <ConfirmDialog
        open={deleteTarget != null}
        title="删除资产"
        description={deleteTarget ? `确认删除资产“${deleteTarget.name}”？如果该资产已被项目引用，系统会阻止删除。` : ""}
        confirmLabel="删除"
        confirmVariant="danger"
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => void handleDelete()}
      />
    </Card>
  );
}
