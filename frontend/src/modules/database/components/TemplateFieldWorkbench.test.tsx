import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const {
  listTemplatePackageCategoriesMock,
  listTemplatePackagesMock,
  fetchTemplatePackageDetailMock,
  fetchTemplatePackageRenderContextMock,
  fetchTemplatePackageRenderPreflightMock,
  fetchTemplateItemBindingsMock,
  fetchTemplateItemRenderContextMock,
  fetchTemplateFieldMappingSuggestionsMock,
} = vi.hoisted(() => ({
  listTemplatePackageCategoriesMock: vi.fn(),
  listTemplatePackagesMock: vi.fn(),
  fetchTemplatePackageDetailMock: vi.fn(),
  fetchTemplatePackageRenderContextMock: vi.fn(),
  fetchTemplatePackageRenderPreflightMock: vi.fn(),
  fetchTemplateItemBindingsMock: vi.fn(),
  fetchTemplateItemRenderContextMock: vi.fn(),
  fetchTemplateFieldMappingSuggestionsMock: vi.fn(),
}));

vi.mock("../../../lib/api", async () => {
  const actual = await vi.importActual("../../../lib/api");
  return {
    ...actual,
    listTemplatePackageCategories: listTemplatePackageCategoriesMock,
    listTemplatePackages: listTemplatePackagesMock,
    fetchTemplatePackageDetail: fetchTemplatePackageDetailMock,
    fetchTemplatePackageRenderContext: fetchTemplatePackageRenderContextMock,
    fetchTemplatePackageRenderPreflight: fetchTemplatePackageRenderPreflightMock,
    fetchTemplateItemBindings: fetchTemplateItemBindingsMock,
    fetchTemplateItemRenderContext: fetchTemplateItemRenderContextMock,
    fetchTemplateFieldMappingSuggestions: fetchTemplateFieldMappingSuggestionsMock,
  };
});

import { TemplateFieldWorkbench } from "./TemplateFieldWorkbench";

function renderWithClient(node: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

beforeEach(() => {
  listTemplatePackageCategoriesMock.mockResolvedValue([
    { code: "sgcc", display_name: "国网施工", description: null, sort_order: 1, enabled: true, metadata_json: {} },
  ]);
  listTemplatePackagesMock.mockResolvedValue([
    {
      id: "pkg-1",
      package_key: "sgcc-business",
      display_name: "国网配网施工商务标模板",
      package_type: "business",
      category_code: "sgcc",
      source_root: "/templates",
      item_count: 2,
    },
  ]);
  fetchTemplatePackageDetailMock.mockResolvedValue({
    id: "pkg-1",
    package_key: "sgcc-business",
    display_name: "国网配网施工商务标模板",
    package_type: "business",
    category_code: "sgcc",
    source_root: "/templates",
    item_count: 2,
    items: [
      {
        id: "item-5",
        item_code: "5",
        item_name: "投标函及投标函附录（含法定代表人签字盖章位置和多行长标题）",
        filename: "5.docx",
        relative_path: "商务标/5.docx",
        source_kind: "docx",
        item_type: "chapter",
        render_mode: "template",
        is_required: true,
        sort_order: 5,
      },
      {
        id: "item-7",
        item_code: "7.2.10",
        item_name: "资格审查资料与企业类似项目业绩证明文件清单",
        filename: "7.docx",
        relative_path: "商务标/7.docx",
        source_kind: "docx",
        item_type: "chapter",
        render_mode: "template",
        is_required: true,
        sort_order: 7,
      },
    ],
  });
  fetchTemplatePackageRenderContextMock.mockResolvedValue({
    package_id: "pkg-1",
    package_key: "sgcc-business",
    display_name: "国网配网施工商务标模板",
    package_type: "business",
    ready_item_count: 1,
    total_item_count: 2,
    items: [
      { item_id: "item-5", item_code: "5", item_name: "投标函及投标函附录（含法定代表人签字盖章位置和多行长标题）", filename: "5.docx", render_mode: "template", binding_count: 0, ready: false, missing_required_bindings: [], context: {}, bindings: [] },
      { item_id: "item-7", item_code: "7.2.10", item_name: "资格审查资料与企业类似项目业绩证明文件清单", filename: "7.docx", render_mode: "template", binding_count: 1, ready: true, missing_required_bindings: [], context: {}, bindings: [] },
    ],
  });
  fetchTemplatePackageRenderPreflightMock.mockResolvedValue({
    package_id: "pkg-1",
    package_key: "sgcc-business",
    display_name: "国网配网施工商务标模板",
    package_type: "business",
    total_item_count: 2,
    ready_item_count: 1,
    blocked_item_count: 1,
    issue_count: 3,
    ready: false,
    items: [
      { item_id: "item-5", item_name: "投标函及投标函附录（含法定代表人签字盖章位置和多行长标题）", filename: "5.docx", relative_path: "商务标/5.docx", render_mode: "template", item_type: "chapter", ready: false, issue_count: 3, issues: [], missing_required_bindings: [], asset_count: 0, valid_asset_count: 0, invalid_asset_count: 0, context_keys: [] },
      { item_id: "item-7", item_name: "资格审查资料与企业类似项目业绩证明文件清单", filename: "7.docx", relative_path: "商务标/7.docx", render_mode: "template", item_type: "chapter", ready: true, issue_count: 0, issues: [], missing_required_bindings: [], asset_count: 1, valid_asset_count: 1, invalid_asset_count: 0, context_keys: [] },
    ],
  });
  fetchTemplateItemBindingsMock.mockResolvedValue([]);
  fetchTemplateItemRenderContextMock.mockResolvedValue({ context: {}, bindings: [] });
  fetchTemplateFieldMappingSuggestionsMock.mockResolvedValue({ suggestions: [] });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("TemplateFieldWorkbench", () => {
  it("renders template directory rows with separated code, title, and status cells", async () => {
    renderWithClient(<TemplateFieldWorkbench />);

    const longTitle = await screen.findByText("投标函及投标函附录（含法定代表人签字盖章位置和多行长标题）");
    const row = longTitle.closest("button");

    expect(row).not.toBeNull();
    expect(row?.querySelector(".template-list__item-shell")).toBeInTheDocument();
    expect(row?.querySelector(".template-list__code-cell")).toHaveTextContent("5");
    expect(row?.querySelector(".template-list__title")).toHaveTextContent(longTitle.textContent ?? "");
    expect(row?.querySelector(".template-list__status")).toHaveTextContent("需修复");
    expect(row?.querySelector(".template-list__meta")).toHaveTextContent("template / chapter / 3 个问题");
  });
});
