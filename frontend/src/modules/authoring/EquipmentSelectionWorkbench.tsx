import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge } from "../../components/ui/Badge";
import { ClayButton } from "../../components/ui/ClayButton";
import { SegmentedTabs } from "../../components/ui/SegmentedTabs";
import type { CompanyAssetType } from "../../lib/api";
import {
  confirmProjectEquipmentSelections,
  createProjectEquipmentSelection,
  deleteProjectEquipmentSelection,
  downloadProjectEquipmentXlsx,
  fetchProjectEquipmentPreview,
  fetchProjectEquipmentAssets,
  fetchProjectEquipmentSelections,
  updateProjectEquipmentSelection,
} from "../../lib/api";

const ASSET_TABS: Array<{ key: CompanyAssetType; label: string }> = [
  { key: "vehicle", label: "车辆" },
  { key: "machine", label: "施工机械" },
  { key: "tool", label: "施工工器具" },
  { key: "safety", label: "安全设施" },
];

type EquipmentSelectionWorkbenchProps = {
  projectId: string;
};

export function EquipmentSelectionWorkbench({ projectId }: EquipmentSelectionWorkbenchProps) {
  const queryClient = useQueryClient();
  const [assetType, setAssetType] = useState<CompanyAssetType>("vehicle");
  const [search, setSearch] = useState("");
  const [validOnly, setValidOnly] = useState(false);
  const [savingRoleId, setSavingRoleId] = useState("");
  const [downloading, setDownloading] = useState(false);

  const candidatesQuery = useQuery({
    queryKey: ["equipment-assets", projectId, assetType, search, validOnly],
    queryFn: ({ signal }) => fetchProjectEquipmentAssets({
      projectId,
      assetType,
      q: search,
      validOnly,
      signal,
    }),
    enabled: !!projectId,
  });

  const selectionsQuery = useQuery({
    queryKey: ["equipment-selections", projectId],
    queryFn: ({ signal }) => fetchProjectEquipmentSelections(projectId, { signal }),
    enabled: !!projectId,
  });

  const previewQuery = useQuery({
    queryKey: ["equipment-preview", projectId],
    queryFn: ({ signal }) => fetchProjectEquipmentPreview(projectId, { signal }),
    enabled: !!projectId,
  });

  const createSelection = useMutation({
    mutationFn: (assetId: string) => createProjectEquipmentSelection(projectId, { asset_id: assetId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["equipment-selections", projectId] });
    },
  });

  const deleteSelection = useMutation({
    mutationFn: (selectionId: string) => deleteProjectEquipmentSelection(projectId, selectionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["equipment-selections", projectId] });
    },
  });

  const confirmSelections = useMutation({
    mutationFn: () => confirmProjectEquipmentSelections(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["equipment-selections", projectId] });
      queryClient.invalidateQueries({ queryKey: ["equipment-preview", projectId] });
    },
  });

  const selectedByAssetId = useMemo(() => {
    const map = new Map<string, string>();
    for (const row of selectionsQuery.data ?? []) {
      map.set(row.asset_id, row.id);
    }
    return map;
  }, [selectionsQuery.data]);

  const currentSelections = useMemo(
    () => (selectionsQuery.data ?? []).filter((row) => row.asset_type === assetType),
    [selectionsQuery.data, assetType],
  );

  const saveRole = async (selectionId: string, intendedRole: string) => {
    setSavingRoleId(selectionId);
    try {
      await updateProjectEquipmentSelection(projectId, selectionId, { intended_role: intendedRole || null });
      await queryClient.invalidateQueries({ queryKey: ["equipment-selections", projectId] });
    } finally {
      setSavingRoleId("");
    }
  };

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const blob = await downloadProjectEquipmentXlsx(projectId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "主要施工设备一览表.xlsx";
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } finally {
      setDownloading(false);
    }
  };

  const previewRows = previewQuery.data?.[assetType] ?? [];
  const previewColumns = previewRows[0] ? Object.keys(previewRows[0]) : [];

  return (
    <section className="equipment-workbench" aria-label="设备清单工作台">
      <div className="template-panel__header">
        <div>
          <div className="template-panel__eyebrow">Manual Selection</div>
          <h2>投标设备清单</h2>
          <p className="template-panel__description">当前阶段先手动从公司资产库选择设备，确认后冻结快照，供后续预览和导出使用。</p>
        </div>
        <div className="equipment-workbench__header-actions">
          <ClayButton type="button" variant="outline" onClick={() => void handleDownload()} disabled={downloading}>
            {downloading ? "下载中..." : "下载 Excel"}
          </ClayButton>
          <ClayButton type="button" onClick={() => confirmSelections.mutate()} disabled={confirmSelections.isPending || (selectionsQuery.data?.length ?? 0) === 0}>
            {confirmSelections.isPending ? "确认中..." : "确认并冻结快照"}
          </ClayButton>
        </div>
      </div>

      <div className="asset-toolbar">
        <SegmentedTabs
          ariaLabel="设备分类"
          value={assetType}
          onChange={setAssetType}
          items={ASSET_TABS.map((tab) => ({
            id: tab.key,
            label: tab.label,
            count: (selectionsQuery.data ?? []).filter((row) => row.asset_type === tab.key).length,
          }))}
        />
        <div className="asset-toolbar__filters">
          <input
            className="clay-input"
            aria-label="搜索设备资产"
            placeholder="搜索名称、规格型号、编号"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <label className="equipment-workbench__toggle">
            <input type="checkbox" checked={validOnly} onChange={(event) => setValidOnly(event.target.checked)} />
            <span>仅看当前有效</span>
          </label>
          <div />
        </div>
      </div>

      <div className="equipment-workbench__grid">
        <div className="equipment-workbench__panel">
          <div className="equipment-workbench__panel-header">
            <h3 className="panel-title-tight">候选资产</h3>
            <Badge variant="info">{candidatesQuery.data?.length ?? 0}</Badge>
          </div>
          <div className="stack-sm">
            {(candidatesQuery.data ?? []).map((asset) => {
              const selectedId = selectedByAssetId.get(asset.id);
              return (
                <div key={asset.id} className="template-list__item">
                  <div className="equipment-workbench__item-head">
                    <strong>{asset.name}</strong>
                    {asset.expires_at && <Badge>{asset.expires_at}</Badge>}
                  </div>
                  <span className="template-list__meta">
                    {[asset.spec_model, asset.serial_no, asset.quantity ? `${asset.quantity}${asset.unit}` : null].filter(Boolean).join(" / ") || "—"}
                  </span>
                  <div className="equipment-workbench__item-actions">
                    {selectedId ? (
                      <ClayButton type="button" variant="ghost" size="sm" onClick={() => deleteSelection.mutate(selectedId)} disabled={deleteSelection.isPending}>
                        移除
                      </ClayButton>
                    ) : (
                      <ClayButton type="button" size="sm" onClick={() => createSelection.mutate(asset.id)} disabled={createSelection.isPending}>
                        加入
                      </ClayButton>
                    )}
                  </div>
                </div>
              );
            })}
            {!candidatesQuery.isLoading && (candidatesQuery.data?.length ?? 0) === 0 && (
              <div className="template-strip-empty">当前没有可选资产。</div>
            )}
          </div>
        </div>

        <div className="equipment-workbench__panel">
          <div className="equipment-workbench__panel-header">
            <h3 className="panel-title-tight">已选清单</h3>
            <Badge variant="primary">{currentSelections.length}</Badge>
          </div>
          <div className="stack-sm">
            {currentSelections.map((row) => (
              <div key={row.id} className="template-list__item">
                <div className="equipment-workbench__item-head">
                  <strong>{String(row.snapshot_json?.name ?? row.asset_id)}</strong>
                  {row.confirmed ? <Badge variant="success">已确认</Badge> : <Badge variant="warning">未确认</Badge>}
                </div>
                <input
                  className="clay-input"
                  aria-label="用途"
                  defaultValue={row.intended_role ?? ""}
                  placeholder="用途/拟用阶段"
                  onBlur={(event) => void saveRole(row.id, event.target.value)}
                  disabled={savingRoleId === row.id}
                />
                <div className="equipment-workbench__item-actions">
                  <ClayButton type="button" variant="ghost" size="sm" onClick={() => deleteSelection.mutate(row.id)} disabled={deleteSelection.isPending}>
                    移除
                  </ClayButton>
                </div>
              </div>
            ))}
            {!selectionsQuery.isLoading && currentSelections.length === 0 && (
              <div className="template-strip-empty">当前类别还没有已选设备。</div>
            )}
          </div>
        </div>
      </div>

      <div className="equipment-workbench__preview">
        <div className="equipment-workbench__panel-header">
          <h3 className="panel-title-tight">设备表预览</h3>
          <Badge variant="info">{previewRows.length}</Badge>
        </div>
        {previewRows.length === 0 ? (
          <div className="template-strip-empty">确认后可在这里预览当前分类的导出表格。</div>
        ) : (
          <div className="asset-table-wrap">
            <table className="asset-table">
              <thead>
                <tr>
                  {previewColumns.map((column) => (
                    <th key={column}>{column}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {previewRows.map((row, index) => (
                  <tr key={`${assetType}-${index}`}>
                    {previewColumns.map((column) => (
                      <td key={column}>{row[column]}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
