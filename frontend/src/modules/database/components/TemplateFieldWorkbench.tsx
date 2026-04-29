import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge } from "../../../components/ui/Badge";
import { ClayButton } from "../../../components/ui/ClayButton";
import { Icon } from "../../../components/ui/Icon";
import type {
  TemplateBindingPayload,
  TemplateBindingRule,
  TemplateFieldMapping,
  TemplateFieldMappingMode,
  TemplateFieldMappingSuggestionGroup,
  TemplateItem,
  TemplatePackageRenderContextItem,
  TemplateSelectionMode,
  TemplateSourceType,
} from "../../../lib/api";
import {
  createTemplateItemBinding,
  deleteTemplateBindingRule,
  fetchTemplateFieldMappingSuggestions,
  fetchTemplateItemBindings,
  fetchTemplateItemRenderContext,
  fetchTemplatePackageDetail,
  fetchTemplatePackageRenderContext,
  listTemplatePackages,
  updateTemplateBindingRule,
} from "../../../lib/api";

type BindingDraft = {
  binding_name: string;
  source_type: TemplateSourceType;
  selection_mode: TemplateSelectionMode;
  source_filters: string;
  field_mappings: string;
  field_mapping_mode: TemplateFieldMappingMode;
  output_key: string;
  required: boolean;
  sort_order: string;
};

const SOURCE_TYPE_OPTIONS: Array<{ value: TemplateSourceType; label: string }> = [
  { value: "company_profile", label: "公司资料" },
  { value: "person_profile", label: "人员资料" },
  { value: "project_performance", label: "项目业绩" },
  { value: "qualification_certificate", label: "资质证书" },
  { value: "financial_statement", label: "财务报表" },
  { value: "evidence_asset", label: "附件资产" },
];

const SELECTION_MODE_OPTIONS: Array<{ value: TemplateSelectionMode; label: string }> = [
  { value: "all", label: "全部记录" },
  { value: "latest", label: "最新一条" },
  { value: "first", label: "第一条" },
  { value: "by_id", label: "按记录 ID" },
];

const FIELD_MAPPING_MODE_OPTIONS: Array<{ value: TemplateFieldMappingMode; label: string }> = [
  { value: "augment", label: "追加字段" },
  { value: "replace", label: "仅输出映射字段" },
];

function defaultOutputKey(sourceType: TemplateSourceType): string {
  switch (sourceType) {
    case "company_profile":
      return "company";
    case "person_profile":
      return "people";
    case "project_performance":
      return "performances";
    case "qualification_certificate":
      return "certificates";
    case "financial_statement":
      return "financial_statements";
    case "evidence_asset":
      return "assets";
    default:
      return "data";
  }
}

function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function createEmptyDraft(item: TemplateItem | null): BindingDraft {
  return {
    binding_name: item ? `${item.item_code ?? "item"}_binding` : "",
    source_type: "company_profile",
    selection_mode: "latest",
    source_filters: "{}",
    field_mappings: "[]",
    field_mapping_mode: "augment",
    output_key: "company",
    required: true,
    sort_order: "0",
  };
}

function draftFromBinding(rule: TemplateBindingRule): BindingDraft {
  return {
    binding_name: rule.binding_name,
    source_type: rule.source_type,
    selection_mode: rule.selection_mode,
    source_filters: prettyJson(rule.source_filters),
    field_mappings: prettyJson(rule.field_mappings),
    field_mapping_mode: rule.field_mapping_mode,
    output_key: rule.output_key,
    required: rule.required,
    sort_order: String(rule.sort_order),
  };
}

function itemStatusVariant(item: TemplatePackageRenderContextItem | undefined) {
  if (!item) return "default" as const;
  if (item.ready) return "success" as const;
  if (item.binding_count === 0) return "warning" as const;
  return "danger" as const;
}

function parseObjectJson(text: string, label: string): Record<string, unknown> {
  try {
    const value = JSON.parse(text || "{}");
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error(`${label} 必须是 JSON 对象`);
    }
    return value as Record<string, unknown>;
  } catch (error) {
    throw new Error(error instanceof Error ? error.message : `${label} 解析失败`);
  }
}

function parseArrayJson(text: string, label: string): TemplateFieldMapping[] {
  try {
    const value = JSON.parse(text || "[]");
    if (!Array.isArray(value)) {
      throw new Error(`${label} 必须是 JSON 数组`);
    }
    return value as TemplateFieldMapping[];
  } catch (error) {
    throw new Error(error instanceof Error ? error.message : `${label} 解析失败`);
  }
}

function summarizeSuggestion(group: TemplateFieldMappingSuggestionGroup): string {
  if (group.field_mappings.length === 0) return "暂无建议字段";
  return group.field_mappings.map((mapping) => mapping.target_field).join(" / ");
}

export function TemplateFieldWorkbench() {
  const queryClient = useQueryClient();
  const [selectedPackageId, setSelectedPackageId] = useState<string | null>(null);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [selectedBindingId, setSelectedBindingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<BindingDraft>(createEmptyDraft(null));
  const [saveError, setSaveError] = useState("");

  const packagesQuery = useQuery({
    queryKey: ["template-packages"],
    queryFn: () => listTemplatePackages(),
  });

  const packageDetailQuery = useQuery({
    queryKey: ["template-package-detail", selectedPackageId],
    queryFn: () => fetchTemplatePackageDetail(selectedPackageId!),
    enabled: Boolean(selectedPackageId),
  });

  const packageContextQuery = useQuery({
    queryKey: ["template-package-context", selectedPackageId],
    queryFn: () => fetchTemplatePackageRenderContext(selectedPackageId!),
    enabled: Boolean(selectedPackageId),
  });

  const itemBindingsQuery = useQuery({
    queryKey: ["template-item-bindings", selectedItemId],
    queryFn: () => fetchTemplateItemBindings(selectedItemId!),
    enabled: Boolean(selectedItemId),
  });

  const itemContextQuery = useQuery({
    queryKey: ["template-item-context", selectedItemId],
    queryFn: () => fetchTemplateItemRenderContext(selectedItemId!),
    enabled: Boolean(selectedItemId),
  });

  const suggestionQuery = useQuery({
    queryKey: ["template-item-suggestions", selectedItemId],
    queryFn: () => fetchTemplateFieldMappingSuggestions(selectedItemId!),
    enabled: Boolean(selectedItemId),
  });

  useEffect(() => {
    if (!selectedPackageId && packagesQuery.data && packagesQuery.data.length > 0) {
      setSelectedPackageId(packagesQuery.data[0].id);
    }
  }, [packagesQuery.data, selectedPackageId]);

  useEffect(() => {
    const items = packageDetailQuery.data?.items ?? [];
    if (items.length === 0) {
      setSelectedItemId(null);
      return;
    }
    if (!selectedItemId || !items.some((item) => item.id === selectedItemId)) {
      setSelectedItemId(items[0].id);
    }
  }, [packageDetailQuery.data?.items, selectedItemId]);

  useEffect(() => {
    const bindings = itemBindingsQuery.data ?? [];
    if (bindings.length === 0) {
      setSelectedBindingId(null);
      return;
    }
    if (!selectedBindingId || !bindings.some((binding) => binding.id === selectedBindingId)) {
      setSelectedBindingId(bindings[0].id);
    }
  }, [itemBindingsQuery.data, selectedBindingId]);

  const selectedItem = useMemo(
    () => packageDetailQuery.data?.items.find((item) => item.id === selectedItemId) ?? null,
    [packageDetailQuery.data?.items, selectedItemId],
  );
  const selectedBinding = useMemo(
    () => itemBindingsQuery.data?.find((binding) => binding.id === selectedBindingId) ?? null,
    [itemBindingsQuery.data, selectedBindingId],
  );
  const itemContext = useMemo(
    () => packageContextQuery.data?.items.find((item) => item.item_id === selectedItemId),
    [packageContextQuery.data?.items, selectedItemId],
  );

  useEffect(() => {
    if (selectedBinding) {
      setDraft(draftFromBinding(selectedBinding));
      setSaveError("");
      return;
    }
    setDraft(createEmptyDraft(selectedItem));
    setSaveError("");
  }, [selectedBinding, selectedItem]);

  const refreshItemQueries = () => {
    void queryClient.invalidateQueries({ queryKey: ["template-item-bindings", selectedItemId] });
    void queryClient.invalidateQueries({ queryKey: ["template-item-context", selectedItemId] });
    void queryClient.invalidateQueries({ queryKey: ["template-package-context", selectedPackageId] });
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!selectedItemId) throw new Error("请先选择模板项");
      const payload: TemplateBindingPayload = {
        binding_name: draft.binding_name.trim(),
        source_type: draft.source_type,
        selection_mode: draft.selection_mode,
        source_filters: parseObjectJson(draft.source_filters, "来源筛选"),
        field_mappings: parseArrayJson(draft.field_mappings, "字段映射"),
        field_mapping_mode: draft.field_mapping_mode,
        output_key: draft.output_key.trim(),
        required: draft.required,
        sort_order: Number(draft.sort_order) || 0,
      };
      if (!payload.binding_name) throw new Error("绑定名称不能为空");
      if (!payload.output_key) throw new Error("输出键不能为空");

      if (selectedBindingId) {
        return updateTemplateBindingRule(selectedBindingId, payload);
      }
      return createTemplateItemBinding(selectedItemId, payload);
    },
    onSuccess: (rule) => {
      setSelectedBindingId(rule.id);
      setSaveError("");
      refreshItemQueries();
    },
    onError: (error) => {
      setSaveError(error instanceof Error ? error.message : "保存失败");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async () => {
      if (!selectedBindingId) throw new Error("请先选择绑定规则");
      return deleteTemplateBindingRule(selectedBindingId);
    },
    onSuccess: () => {
      setSelectedBindingId(null);
      setSaveError("");
      refreshItemQueries();
    },
    onError: (error) => {
      setSaveError(error instanceof Error ? error.message : "删除失败");
    },
  });

  const applySuggestion = (group: TemplateFieldMappingSuggestionGroup) => {
    setDraft((current) => ({
      ...current,
      source_type: group.source_type,
      output_key: defaultOutputKey(group.source_type),
      field_mapping_mode: group.field_mapping_mode,
      field_mappings: prettyJson(group.field_mappings),
    }));
  };

  const itemContextPreview = prettyJson(itemContextQuery.data?.context ?? {});
  const itemBindingsPreview = prettyJson(itemContextQuery.data?.bindings ?? []);

  return (
    <div className="template-field-shell">
      <aside className="template-field-rail">
        <section className="template-panel template-panel--rail">
          <div className="template-panel__header">
            <div>
              <p className="template-panel__eyebrow">模板包</p>
              <h2>目录视图</h2>
            </div>
            <Badge variant="info">{packagesQuery.data?.length ?? 0}</Badge>
          </div>
          {packagesQuery.isLoading && <div className="spinner" />}
          {packagesQuery.isError && <p className="text-error">{(packagesQuery.error as Error).message}</p>}
          <div className="template-list">
            {(packagesQuery.data ?? []).map((pkg) => (
              <button
                key={pkg.id}
                type="button"
                className={`template-list__item ${selectedPackageId === pkg.id ? "is-active" : ""}`}
                onClick={() => {
                  setSelectedPackageId(pkg.id);
                  setSelectedItemId(null);
                  setSelectedBindingId(null);
                }}
              >
                <span className="template-list__title">{pkg.display_name}</span>
                <span className="template-list__meta">{pkg.item_count} 个模板项</span>
              </button>
            ))}
          </div>
        </section>

        <section className="template-panel template-panel--rail">
          <div className="template-panel__header">
            <div>
              <p className="template-panel__eyebrow">模板项</p>
              <h2>{packageDetailQuery.data?.display_name ?? "未选择模板包"}</h2>
            </div>
            <Badge variant="default">{packageDetailQuery.data?.items.length ?? 0}</Badge>
          </div>
          {packageDetailQuery.isLoading && <div className="spinner" />}
          <div className="template-list">
            {(packageDetailQuery.data?.items ?? []).map((item) => {
              const contextItem = packageContextQuery.data?.items.find((row) => row.item_id === item.id);
              return (
                <button
                  key={item.id}
                  type="button"
                  className={`template-list__item ${selectedItemId === item.id ? "is-active" : ""}`}
                  onClick={() => {
                    setSelectedItemId(item.id);
                    setSelectedBindingId(null);
                  }}
                >
                  <div className="template-list__row">
                    <span className="template-list__code">{item.item_code ?? "-"}</span>
                    <Badge variant={itemStatusVariant(contextItem)}>
                      {contextItem?.ready ? "已就绪" : contextItem?.binding_count ? "待完善" : "未绑定"}
                    </Badge>
                  </div>
                  <span className="template-list__title">{item.item_name}</span>
                  <span className="template-list__meta">{item.render_mode} / {item.item_type}</span>
                </button>
              );
            })}
          </div>
        </section>
      </aside>

      <main className="template-field-main">
        <section className="template-panel template-panel--hero">
          <div className="template-panel__header template-panel__header--hero">
            <div>
              <p className="template-panel__eyebrow">模板项字段面板</p>
              <h2>{selectedItem ? `${selectedItem.item_code ?? ""} ${selectedItem.item_name}`.trim() : "请选择模板项"}</h2>
              <p className="template-panel__description">
                {selectedItem ? selectedItem.relative_path : "从左侧选择模板包和模板项后，配置数据绑定、字段映射和输出键。"}
              </p>
            </div>
            {selectedItem && (
              <div className="template-summary">
                <div className="template-summary__pill">
                  <span>绑定规则</span>
                  <strong>{itemBindingsQuery.data?.length ?? 0}</strong>
                </div>
                <div className="template-summary__pill">
                  <span>上下文状态</span>
                  <strong>{itemContext?.ready ? "就绪" : "待完善"}</strong>
                </div>
                <div className="template-summary__pill">
                  <span>缺失项</span>
                  <strong>{itemContext?.missing_required_bindings.length ?? 0}</strong>
                </div>
              </div>
            )}
          </div>
        </section>

        {selectedItem ? (
          <div className="template-field-grid">
            <section className="template-panel">
              <div className="template-panel__header">
                <div>
                  <p className="template-panel__eyebrow">绑定编辑器</p>
                  <h2>规则配置</h2>
                </div>
                <div className="template-inline-actions">
                  <ClayButton
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setSelectedBindingId(null);
                      setDraft(createEmptyDraft(selectedItem));
                    }}
                  >
                    <Icon name="plus" size={14} /> 新建
                  </ClayButton>
                  <ClayButton
                    variant="danger"
                    size="sm"
                    disabled={!selectedBindingId || deleteMutation.isPending}
                    onClick={() => {
                      if (selectedBindingId && window.confirm("删除该绑定规则？")) {
                        deleteMutation.mutate();
                      }
                    }}
                  >
                    <Icon name="trash" size={14} /> 删除
                  </ClayButton>
                </div>
              </div>

              <div className="template-binding-strip">
                {(itemBindingsQuery.data ?? []).map((binding) => (
                  <button
                    key={binding.id}
                    type="button"
                    className={`template-chip ${selectedBindingId === binding.id ? "is-active" : ""}`}
                    onClick={() => setSelectedBindingId(binding.id)}
                  >
                    {binding.binding_name}
                  </button>
                ))}
                {(itemBindingsQuery.data?.length ?? 0) === 0 && (
                  <span className="template-strip-empty">当前模板项还没有绑定规则。</span>
                )}
              </div>

              <div className="template-form-grid">
                <div className="form-group">
                  <label className="form-label">绑定名称</label>
                  <input
                    className="clay-input"
                    value={draft.binding_name}
                    onChange={(event) => setDraft((current) => ({ ...current, binding_name: event.target.value }))}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">输出键</label>
                  <input
                    className="clay-input"
                    value={draft.output_key}
                    onChange={(event) => setDraft((current) => ({ ...current, output_key: event.target.value }))}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">来源类型</label>
                  <select
                    className="clay-input"
                    value={draft.source_type}
                    onChange={(event) => {
                      const sourceType = event.target.value as TemplateSourceType;
                      setDraft((current) => ({
                        ...current,
                        source_type: sourceType,
                        output_key: current.output_key === defaultOutputKey(current.source_type)
                          ? defaultOutputKey(sourceType)
                          : current.output_key,
                      }));
                    }}
                  >
                    {SOURCE_TYPE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">选择模式</label>
                  <select
                    className="clay-input"
                    value={draft.selection_mode}
                    onChange={(event) => setDraft((current) => ({ ...current, selection_mode: event.target.value as TemplateSelectionMode }))}
                  >
                    {SELECTION_MODE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">映射模式</label>
                  <select
                    className="clay-input"
                    value={draft.field_mapping_mode}
                    onChange={(event) => setDraft((current) => ({ ...current, field_mapping_mode: event.target.value as TemplateFieldMappingMode }))}
                  >
                    {FIELD_MAPPING_MODE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">排序</label>
                  <input
                    className="clay-input"
                    type="number"
                    value={draft.sort_order}
                    onChange={(event) => setDraft((current) => ({ ...current, sort_order: event.target.value }))}
                  />
                </div>
              </div>

              <div className="template-toggle-row">
                <label className="template-toggle">
                  <input
                    type="checkbox"
                    checked={draft.required}
                    onChange={(event) => setDraft((current) => ({ ...current, required: event.target.checked }))}
                  />
                  <span>必填绑定</span>
                </label>
              </div>

              <div className="form-group">
                <label className="form-label">来源筛选 JSON</label>
                <textarea
                  className="clay-textarea template-json"
                  rows={8}
                  value={draft.source_filters}
                  onChange={(event) => setDraft((current) => ({ ...current, source_filters: event.target.value }))}
                />
              </div>
              <div className="form-group">
                <label className="form-label">字段映射 JSON</label>
                <textarea
                  className="clay-textarea template-json"
                  rows={12}
                  value={draft.field_mappings}
                  onChange={(event) => setDraft((current) => ({ ...current, field_mappings: event.target.value }))}
                />
              </div>

              {saveError && <p className="text-error">{saveError}</p>}

              <div className="template-inline-actions">
                <ClayButton onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
                  {saveMutation.isPending ? "保存中..." : selectedBindingId ? "更新绑定" : "创建绑定"}
                </ClayButton>
                <ClayButton variant="outline" onClick={refreshItemQueries}>
                  <Icon name="refresh" size={14} /> 刷新预览
                </ClayButton>
              </div>
            </section>

            <div className="template-field-stack">
              <section className="template-panel">
                <div className="template-panel__header">
                  <div>
                    <p className="template-panel__eyebrow">映射建议</p>
                    <h2>推荐字段</h2>
                  </div>
                  <Badge variant="primary">{suggestionQuery.data?.suggestions.length ?? 0}</Badge>
                </div>
                <div className="template-suggestion-list">
                  {(suggestionQuery.data?.suggestions ?? []).map((group) => (
                    <button
                      key={group.source_type}
                      type="button"
                      className="template-suggestion"
                      onClick={() => applySuggestion(group)}
                    >
                      <div className="template-suggestion__top">
                        <strong>{SOURCE_TYPE_OPTIONS.find((option) => option.value === group.source_type)?.label ?? group.source_type}</strong>
                        <Badge variant="info">{group.field_mapping_mode}</Badge>
                      </div>
                      <p>{summarizeSuggestion(group)}</p>
                    </button>
                  ))}
                  {suggestionQuery.isLoading && <div className="spinner" />}
                </div>
              </section>

              <section className="template-panel">
                <div className="template-panel__header">
                  <div>
                    <p className="template-panel__eyebrow">上下文预览</p>
                    <h2>映射结果</h2>
                  </div>
                  <Badge variant={itemContext?.ready ? "success" : "warning"}>
                    {itemContext?.ready ? "ready" : "draft"}
                  </Badge>
                </div>
                <div className="template-preview-tabs">
                  <div className="template-preview-block">
                    <h3>Context</h3>
                    <pre>{itemContextPreview}</pre>
                  </div>
                  <div className="template-preview-block">
                    <h3>Resolved Bindings</h3>
                    <pre>{itemBindingsPreview}</pre>
                  </div>
                </div>
              </section>
            </div>
          </div>
        ) : (
          <section className="template-panel">
            <div className="empty-state" style={{ padding: "var(--space-12)" }}>
              <p>请选择模板项开始配置字段映射。</p>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
