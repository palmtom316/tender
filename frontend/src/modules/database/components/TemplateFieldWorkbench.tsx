import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge } from "../../../components/ui/Badge";
import { ClayButton } from "../../../components/ui/ClayButton";
import { ConfirmDialog } from "../../../components/ui/ConfirmDialog";
import { Icon } from "../../../components/ui/Icon";
import type {
  TemplateBindingPayload,
  TemplateBindingRule,
  TemplateFieldMapping,
  TemplateFieldMappingMode,
  TemplateFieldMappingSuggestionGroup,
  TemplateItem,
  TemplatePackageCategory,
  TemplatePackageRenderPreflightItem,
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
  fetchTemplatePackageRenderPreflight,
  fetchTemplatePackageRenderContext,
  listTemplatePackageCategories,
  listTemplatePackages,
  updateTemplateBindingRule,
} from "../../../lib/api";

type BindingDraft = {
  binding_name: string;
  source_type: TemplateSourceType;
  selection_mode: TemplateSelectionMode;
  source_filters: string;
  field_mappings: TemplateFieldMapping[];
  field_mapping_mode: TemplateFieldMappingMode;
  output_key: string;
  required: boolean;
  sort_order: string;
};

type TemplateFieldTransform = NonNullable<TemplateFieldMapping["transform"]>;

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

const FIELD_TRANSFORM_OPTIONS: Array<{ value: TemplateFieldTransform; label: string }> = [
  { value: "copy", label: "直接复制" },
  { value: "join", label: "多字段拼接" },
  { value: "date", label: "日期格式化" },
  { value: "number", label: "数值格式化" },
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

function createEmptyFieldMapping(): TemplateFieldMapping {
  return {
    target_field: "",
    source_field: "",
    transform: "copy",
    default_value: "",
  };
}

function withFieldMappingDefaults(mapping: TemplateFieldMapping): TemplateFieldMapping {
  const transform = mapping.transform ?? "copy";
  return {
    ...mapping,
    transform,
    join_with: transform === "join" ? mapping.join_with ?? "" : undefined,
    date_format: transform === "date" ? mapping.date_format ?? "%Y-%m-%d" : undefined,
    decimals: transform === "number" ? mapping.decimals ?? 2 : undefined,
  };
}

function createEmptyDraft(item: TemplateItem | null): BindingDraft {
  return {
    binding_name: item ? `${item.item_code ?? "item"}_binding` : "",
    source_type: "company_profile",
    selection_mode: "latest",
    source_filters: "{}",
    field_mappings: [],
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
    field_mappings: rule.field_mappings.map(withFieldMappingDefaults),
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

function preflightStatusVariant(item: TemplatePackageRenderPreflightItem | null | undefined) {
  if (!item) return "default" as const;
  return item.ready ? "success" : "warning";
}

function preflightStatusLabel(item: TemplatePackageRenderPreflightItem | null | undefined) {
  if (!item) return "未预检";
  return item.ready ? "可导出" : "需修复";
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

function normalizeFieldMappings(mappings: TemplateFieldMapping[]): TemplateFieldMapping[] {
  return mappings.map((mapping, index) => {
    const targetField = mapping.target_field.trim();
    if (!targetField) {
      throw new Error(`字段映射第 ${index + 1} 行缺少目标字段`);
    }

    const transform = mapping.transform ?? "copy";
    const defaultValue = typeof mapping.default_value === "string"
      ? mapping.default_value.trim()
      : mapping.default_value;

    const normalized: TemplateFieldMapping = {
      target_field: targetField,
      transform,
    };

    if (defaultValue !== "" && defaultValue !== undefined) {
      normalized.default_value = defaultValue;
    }

    if (transform === "join") {
      const sourceFields = (mapping.source_fields ?? [])
        .map((field) => field.trim())
        .filter(Boolean);
      if (sourceFields.length === 0) {
        throw new Error(`字段映射第 ${index + 1} 行缺少来源字段`);
      }
      normalized.source_fields = sourceFields;
      if ((mapping.join_with ?? "").trim()) {
        normalized.join_with = mapping.join_with?.trim();
      }
      return normalized;
    }

    const sourceField = mapping.source_field?.trim();
    if (!sourceField && normalized.default_value === undefined) {
      throw new Error(`字段映射第 ${index + 1} 行缺少来源字段`);
    }
    if (sourceField) {
      normalized.source_field = sourceField;
    }
    if (transform === "date" && (mapping.date_format ?? "").trim()) {
      normalized.date_format = mapping.date_format?.trim();
    }
    if (transform === "number" && Number.isFinite(mapping.decimals)) {
      normalized.decimals = mapping.decimals;
    }
    return normalized;
  });
}

function summarizeSuggestion(group: TemplateFieldMappingSuggestionGroup): string {
  if (group.field_mappings.length === 0) return "暂无建议字段";
  return group.field_mappings.map((mapping) => mapping.target_field).join(" / ");
}

function formatConfidence(confidence: number): string {
  return `${Math.round(confidence * 100)}%`;
}

export function TemplateFieldWorkbench() {
  const queryClient = useQueryClient();
  const [selectedCategoryCode, setSelectedCategoryCode] = useState<string>("");
  const [selectedPackageId, setSelectedPackageId] = useState<string | null>(null);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [selectedBindingId, setSelectedBindingId] = useState<string | null>(null);
  const [showOnlyBlockedItems, setShowOnlyBlockedItems] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [draft, setDraft] = useState<BindingDraft>(createEmptyDraft(null));
  const [saveError, setSaveError] = useState("");

  const categoriesQuery = useQuery({
    queryKey: ["template-package-categories"],
    queryFn: () => listTemplatePackageCategories(),
  });

  const packagesQuery = useQuery({
    queryKey: ["template-packages", selectedCategoryCode],
    queryFn: () => listTemplatePackages({ categoryCode: selectedCategoryCode || undefined }),
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

  const packagePreflightQuery = useQuery({
    queryKey: ["template-package-preflight", selectedPackageId],
    queryFn: () => fetchTemplatePackageRenderPreflight(selectedPackageId!),
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
    const packages = packagesQuery.data ?? [];
    if (packages.length === 0) {
      setSelectedPackageId(null);
      return;
    }
    if (!selectedPackageId || !packages.some((pkg) => pkg.id === selectedPackageId)) {
      setSelectedPackageId(packages[0].id);
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
  const preflightItem = useMemo(
    () => packagePreflightQuery.data?.items.find((item) => item.item_id === selectedItemId) ?? null,
    [packagePreflightQuery.data?.items, selectedItemId],
  );
  const filteredPackageItems = useMemo(() => {
    const items = packageDetailQuery.data?.items ?? [];
    if (!showOnlyBlockedItems) return items;
    const blockedIds = new Set(
      (packagePreflightQuery.data?.items ?? [])
        .filter((item) => !item.ready)
        .map((item) => item.item_id),
    );
    return items.filter((item) => blockedIds.has(item.id));
  }, [packageDetailQuery.data?.items, packagePreflightQuery.data?.items, showOnlyBlockedItems]);
  const blockedPreflightItems = useMemo(
    () => (packagePreflightQuery.data?.items ?? []).filter((item) => !item.ready),
    [packagePreflightQuery.data?.items],
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

  useEffect(() => {
    if (!showOnlyBlockedItems) return;
    if (filteredPackageItems.length === 0) return;
    if (!selectedItemId || !filteredPackageItems.some((item) => item.id === selectedItemId)) {
      setSelectedItemId(filteredPackageItems[0].id);
      setSelectedBindingId(null);
    }
  }, [filteredPackageItems, selectedItemId, showOnlyBlockedItems]);

  const refreshItemQueries = () => {
    void queryClient.invalidateQueries({ queryKey: ["template-item-bindings", selectedItemId] });
    void queryClient.invalidateQueries({ queryKey: ["template-item-context", selectedItemId] });
    void queryClient.invalidateQueries({ queryKey: ["template-package-context", selectedPackageId] });
    void queryClient.invalidateQueries({ queryKey: ["template-package-preflight", selectedPackageId] });
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!selectedItemId) throw new Error("请先选择模板项");
      const payload: TemplateBindingPayload = {
        binding_name: draft.binding_name.trim(),
        source_type: draft.source_type,
        selection_mode: draft.selection_mode,
        source_filters: parseObjectJson(draft.source_filters, "来源筛选"),
        field_mappings: normalizeFieldMappings(draft.field_mappings),
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
      field_mappings: group.field_mappings,
    }));
  };

  const updateFieldMapping = (
    index: number,
    updater: (mapping: TemplateFieldMapping) => TemplateFieldMapping,
  ) => {
    setDraft((current) => ({
      ...current,
      field_mappings: current.field_mappings.map((mapping, mappingIndex) => (
        mappingIndex === index ? updater(mapping) : mapping
      )),
    }));
  };

  const itemContextPreview = prettyJson(itemContextQuery.data?.context ?? {});
  const itemBindingsPreview = prettyJson(itemContextQuery.data?.bindings ?? []);
  const selectedCategory = (categoriesQuery.data ?? []).find((item) => item.code === selectedCategoryCode) ?? null;

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
          <div className="form-group form-group--tight">
            <label className="form-label">模板类别</label>
            <select
              className="clay-input"
              aria-label="模板类别"
              value={selectedCategoryCode}
              onChange={(event) => {
                setSelectedCategoryCode(event.target.value);
                setSelectedPackageId(null);
                setSelectedItemId(null);
                setSelectedBindingId(null);
              }}
            >
              <option value="">全部模板类别</option>
              {(categoriesQuery.data ?? []).map((category: TemplatePackageCategory) => (
                <option key={category.code} value={category.code}>{category.display_name}</option>
              ))}
            </select>
          </div>
          {packagesQuery.isLoading && (
            <div className="skeleton-stack" aria-label="模板包加载中">
              <div className="skeleton-card" />
              <div className="skeleton-card" />
            </div>
          )}
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
                <span className="template-list__meta">
                  {(categoriesQuery.data ?? []).find((category) => category.code === pkg.category_code)?.display_name ?? "未分类"} / {pkg.item_count} 个模板项
                </span>
              </button>
            ))}
            {(packagesQuery.data?.length ?? 0) === 0 && (
              <div className="template-strip-empty">
                {selectedCategory ? `${selectedCategory.display_name} 下暂无模板包。` : "当前没有模板包。"}
              </div>
            )}
          </div>
        </section>

        <section className="template-panel template-panel--rail">
          <div className="template-panel__header">
            <div>
              <p className="template-panel__eyebrow">模板项</p>
              <h2>{packageDetailQuery.data?.display_name ?? "未选择模板包"}</h2>
            </div>
            <Badge variant="default">{filteredPackageItems.length}</Badge>
          </div>
          <div className="template-inline-actions template-inline-actions--compact">
            <ClayButton
              variant={showOnlyBlockedItems ? "secondary" : "outline"}
              size="sm"
              onClick={() => setShowOnlyBlockedItems((current) => !current)}
              disabled={!packagePreflightQuery.data}
            >
              {showOnlyBlockedItems ? "显示全部" : "只看待修复项"}
            </ClayButton>
          </div>
          {packageDetailQuery.isLoading && (
            <div className="skeleton-stack" aria-label="模板项加载中">
              <div className="skeleton-card" />
              <div className="skeleton-card" />
            </div>
          )}
          <div className="template-list">
            {filteredPackageItems.map((item) => {
              const contextItem = packageContextQuery.data?.items.find((row) => row.item_id === item.id);
              const preflightListItem = packagePreflightQuery.data?.items.find((row) => row.item_id === item.id) ?? null;
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
                    <Badge variant={preflightListItem ? preflightStatusVariant(preflightListItem) : itemStatusVariant(contextItem)}>
                      {preflightListItem ? preflightStatusLabel(preflightListItem) : contextItem?.ready ? "已就绪" : contextItem?.binding_count ? "待完善" : "未绑定"}
                    </Badge>
                  </div>
                  <span className="template-list__title">{item.item_name}</span>
                  <span className="template-list__meta">
                    {item.render_mode} / {item.item_type}
                    {preflightListItem && preflightListItem.issue_count > 0 ? ` / ${preflightListItem.issue_count} 个问题` : ""}
                  </span>
                </button>
              );
            })}
            {showOnlyBlockedItems && filteredPackageItems.length === 0 && (
              <div className="template-strip-empty">当前模板包没有待修复项。</div>
            )}
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
                <div className="template-summary__pill">
                  <span>预检状态</span>
                  <strong>{packagePreflightQuery.data?.ready ? "可导出" : "需修复"}</strong>
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
                    onClick={() => setDeleteDialogOpen(true)}
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
                    aria-label="绑定名称"
                    value={draft.binding_name}
                    onChange={(event) => setDraft((current) => ({ ...current, binding_name: event.target.value }))}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">输出键</label>
                  <input
                    className="clay-input"
                    aria-label="输出键"
                    value={draft.output_key}
                    onChange={(event) => setDraft((current) => ({ ...current, output_key: event.target.value }))}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">来源类型</label>
                  <select
                    className="clay-input"
                    aria-label="来源类型"
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
                    aria-label="选择模式"
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
                    aria-label="映射模式"
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
                    aria-label="排序"
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
                    aria-label="必填绑定"
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
                  aria-label="来源筛选 JSON"
                  rows={8}
                  value={draft.source_filters}
                  onChange={(event) => setDraft((current) => ({ ...current, source_filters: event.target.value }))}
                />
              </div>
              <div className="form-group">
                <div className="template-mapping-header">
                  <label className="form-label template-label-inline">字段映射</label>
                  <Badge variant="info">{draft.field_mappings.length}</Badge>
                </div>
                <div className="template-mapping-list">
                  {draft.field_mappings.map((mapping, index) => {
                    const transform = mapping.transform ?? "copy";
                    return (
                      <div key={`${mapping.target_field}-${index}`} className="template-mapping-card">
                        <div className="template-mapping-card__header">
                          <strong>映射 {index + 1}</strong>
                          <button
                            type="button"
                            className="template-mapping-card__remove"
                            onClick={() => {
                              setDraft((current) => ({
                                ...current,
                                field_mappings: current.field_mappings.filter((_, rowIndex) => rowIndex !== index),
                              }));
                            }}
                          >
                            删除
                          </button>
                        </div>
                        <div className="template-mapping-grid">
                          <div className="form-group">
                            <label className="form-label">目标字段</label>
                            <input
                              className="clay-input"
                              aria-label={`字段映射 ${index + 1} 目标字段`}
                              value={mapping.target_field}
                              onChange={(event) => updateFieldMapping(index, (current) => ({
                                ...current,
                                target_field: event.target.value,
                              }))}
                            />
                          </div>
                          <div className="form-group">
                            <label className="form-label">转换方式</label>
                            <select
                              className="clay-input"
                              aria-label={`字段映射 ${index + 1} 转换方式`}
                              value={transform}
                              onChange={(event) => {
                                const nextTransform = event.target.value as TemplateFieldTransform;
                                updateFieldMapping(index, (current) => ({
                                  ...current,
                                  transform: nextTransform,
                                  source_field: nextTransform === "join" ? undefined : current.source_field,
                                  source_fields: nextTransform === "join" ? current.source_fields ?? [] : undefined,
                                  join_with: nextTransform === "join" ? current.join_with ?? "" : undefined,
                                  date_format: nextTransform === "date" ? current.date_format ?? "%Y-%m-%d" : undefined,
                                  decimals: nextTransform === "number" ? current.decimals ?? 2 : undefined,
                                }));
                              }}
                            >
                              {FIELD_TRANSFORM_OPTIONS.map((option) => (
                                <option key={option.value} value={option.value}>{option.label}</option>
                              ))}
                            </select>
                          </div>
                          {transform === "join" ? (
                            <>
                              <div className="form-group template-mapping-grid__wide">
                                <label className="form-label">来源字段列表</label>
                                <input
                                  className="clay-input"
                                  aria-label={`字段映射 ${index + 1} 来源字段列表`}
                                  placeholder="例如：certificate_name, grade, specialty"
                                  value={(mapping.source_fields ?? []).join(", ")}
                                  onChange={(event) => updateFieldMapping(index, (current) => ({
                                    ...current,
                                    source_fields: event.target.value
                                      .split(",")
                                      .map((field) => field.trim())
                                      .filter(Boolean),
                                  }))}
                                />
                              </div>
                              <div className="form-group">
                                <label className="form-label">拼接分隔符</label>
                                <input
                                  className="clay-input"
                                  aria-label={`字段映射 ${index + 1} 拼接分隔符`}
                                  placeholder="例如： / "
                                  value={mapping.join_with ?? ""}
                                  onChange={(event) => updateFieldMapping(index, (current) => ({
                                    ...current,
                                    join_with: event.target.value,
                                  }))}
                                />
                              </div>
                            </>
                          ) : (
                            <div className="form-group template-mapping-grid__wide">
                              <label className="form-label">来源字段</label>
                              <input
                                className="clay-input"
                                aria-label={`字段映射 ${index + 1} 来源字段`}
                                placeholder="例如：company_name"
                                value={mapping.source_field ?? ""}
                                onChange={(event) => updateFieldMapping(index, (current) => ({
                                  ...current,
                                  source_field: event.target.value,
                                }))}
                              />
                            </div>
                          )}
                          {transform === "date" && (
                            <div className="form-group">
                              <label className="form-label">日期格式</label>
                              <input
                                className="clay-input"
                                aria-label={`字段映射 ${index + 1} 日期格式`}
                                placeholder="%Y-%m-%d"
                                value={mapping.date_format ?? ""}
                                onChange={(event) => updateFieldMapping(index, (current) => ({
                                  ...current,
                                  date_format: event.target.value,
                                }))}
                              />
                            </div>
                          )}
                          {transform === "number" && (
                            <div className="form-group">
                              <label className="form-label">小数位</label>
                              <input
                                className="clay-input"
                                aria-label={`字段映射 ${index + 1} 小数位`}
                                type="number"
                                min={0}
                                value={mapping.decimals ?? 2}
                                onChange={(event) => updateFieldMapping(index, (current) => ({
                                  ...current,
                                  decimals: Number(event.target.value || 0),
                                }))}
                              />
                            </div>
                          )}
                          <div className="form-group template-mapping-grid__wide">
                            <label className="form-label">默认值</label>
                            <input
                              className="clay-input"
                              aria-label={`字段映射 ${index + 1} 默认值`}
                              placeholder="来源字段为空时使用"
                              value={typeof mapping.default_value === "string" ? mapping.default_value : ""}
                              onChange={(event) => updateFieldMapping(index, (current) => ({
                                ...current,
                                default_value: event.target.value,
                              }))}
                            />
                          </div>
                        </div>
                      </div>
                    );
                  })}
                  {draft.field_mappings.length === 0 && (
                    <div className="template-mapping-empty">
                      <p>当前绑定还没有字段映射。可直接新增，或点击右侧“映射建议”自动填充。</p>
                    </div>
                  )}
                </div>
                <div className="template-inline-actions template-inline-actions--offset">
                  <ClayButton
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setDraft((current) => ({
                        ...current,
                        field_mappings: [...current.field_mappings, createEmptyFieldMapping()],
                      }));
                    }}
                  >
                    <Icon name="plus" size={14} /> 新增映射
                  </ClayButton>
                </div>
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
                    <p className="template-panel__eyebrow">渲染预检</p>
                    <h2>导出前检查</h2>
                  </div>
                  <Badge variant={packagePreflightQuery.data?.ready ? "success" : "warning"}>
                    {packagePreflightQuery.data?.ready ? "可导出" : "待修复"}
                  </Badge>
                </div>
                {packagePreflightQuery.isLoading && (
                  <div className="skeleton-stack" aria-label="预检加载中">
                    <div className="skeleton-card" />
                    <div className="skeleton-line" />
                  </div>
                )}
                {packagePreflightQuery.isError && (
                  <p className="text-error">{(packagePreflightQuery.error as Error).message}</p>
                )}
                {packagePreflightQuery.data && (
                  <>
                    <div className="template-preflight-summary">
                      <div className="template-preflight-summary__card">
                        <span>已就绪模板项</span>
                        <strong>{packagePreflightQuery.data.ready_item_count}</strong>
                      </div>
                      <div className="template-preflight-summary__card">
                        <span>待修复模板项</span>
                        <strong>{packagePreflightQuery.data.blocked_item_count}</strong>
                      </div>
                      <div className="template-preflight-summary__card">
                        <span>问题总数</span>
                        <strong>{packagePreflightQuery.data.issue_count}</strong>
                      </div>
                    </div>
                    {blockedPreflightItems.length > 0 && (
                      <div className="template-preflight-locator">
                        <div className="template-preflight-locator__header">
                          <strong>待修复模板项</strong>
                          <span>{blockedPreflightItems.length} 项</span>
                        </div>
                        <div className="template-preflight-locator__list">
                          {blockedPreflightItems.map((item) => (
                            <button
                              key={item.item_id}
                              type="button"
                              className={`template-preflight-locator__item ${selectedItemId === item.item_id ? "is-active" : ""}`}
                              onClick={() => {
                                setSelectedItemId(item.item_id);
                                setSelectedBindingId(null);
                              }}
                            >
                              <span>{item.item_name}</span>
                              <Badge variant="warning">{item.issue_count}</Badge>
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                    {selectedItem && preflightItem ? (
                      <TemplatePreflightDetail item={preflightItem} />
                    ) : (
                      <div className="template-mapping-empty">选择模板项后查看该项的预检详情。</div>
                    )}
                  </>
                )}
              </section>

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
                        <div className="template-suggestion__badges">
                          <Badge variant="info">{group.field_mapping_mode}</Badge>
                          <Badge variant={group.confidence >= 0.8 ? "success" : group.confidence >= 0.5 ? "warning" : "default"}>
                            {formatConfidence(group.confidence)}
                          </Badge>
                        </div>
                      </div>
                      <p>{summarizeSuggestion(group)}</p>
                    </button>
                  ))}
                  {suggestionQuery.isLoading && (
                    <div className="skeleton-stack" aria-label="映射建议加载中">
                      <div className="skeleton-card" />
                      <div className="skeleton-card" />
                    </div>
                  )}
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
            <div className="empty-state empty-state--spacious">
              <span className="empty-state__icon">映</span>
              <p className="empty-state__title">选择模板项</p>
              <p className="empty-state__description">选择左侧模板项后，可配置字段映射、预检问题和推荐字段。</p>
            </div>
          </section>
        )}
        <ConfirmDialog
          open={deleteDialogOpen}
          title="删除绑定规则"
          description="删除后，该模板项的字段映射与数据绑定配置将立即失效。"
          confirmLabel="确认删除"
          busy={deleteMutation.isPending}
          onCancel={() => setDeleteDialogOpen(false)}
          onConfirm={() => {
            setDeleteDialogOpen(false);
            deleteMutation.mutate();
          }}
        />
      </main>
    </div>
  );
}

function TemplatePreflightDetail({ item }: { item: TemplatePackageRenderPreflightItem }) {
  return (
    <div className="template-preflight-detail">
      <div className="template-preflight-detail__header">
        <div>
          <h3>{item.item_name}</h3>
          <p>{item.relative_path}</p>
        </div>
        <Badge variant={item.ready ? "success" : "warning"}>
          {item.ready ? "通过" : "阻塞"}
        </Badge>
      </div>
      <div className="template-preflight-meta">
        <span>{item.render_mode} / {item.item_type}</span>
        <span>附件 {item.valid_asset_count}/{item.asset_count}</span>
        <span>问题 {item.issue_count}</span>
      </div>
      {item.issues.length === 0 ? (
        <div className="template-mapping-empty">该模板项预检通过，可直接参与包渲染。</div>
      ) : (
        <div className="template-preflight-issues">
          {item.issues.map((issue, index) => (
            <div key={`${issue.code}-${index}`} className="template-preflight-issue">
              <div className="template-preflight-issue__top">
                <strong>{issue.code}</strong>
                {issue.asset_name && <Badge variant="warning">{issue.asset_name}</Badge>}
              </div>
              <p>{issue.message}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
