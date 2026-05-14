import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { api, nav } = vi.hoisted(() => ({
  api: {
    fetchProjectTemplateInstance: vi.fn(),
    reorderProjectTemplateChapters: vi.fn(),
    updateProjectTemplateBlock: vi.fn(),
    confirmProjectTemplateInstance: vi.fn(),
    proposeProjectTemplatePromotion: vi.fn(),
  },
  nav: { projectId: "p1", navigate: vi.fn() },
}));

vi.mock("../../lib/NavigationContext", () => ({ useNavigation: () => nav }));
vi.mock("../../lib/api", async () => ({ ...(await vi.importActual("../../lib/api")), ...api }));

import { ProjectTemplateWorkbench } from "./ProjectTemplateWorkbench";

function withClient(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>;
}

function instance(overrides: Record<string, unknown> = {}) {
  return {
    id: "inst-1",
    project_id: "p1",
    display_name: "项目模板实例",
    status: "draft",
    reconciliation_summary: { critical: 0, medium: 0, low: 0 },
    unanswered_requirement_count: 0,
    pending_seal_checklist_count: 0,
    chapters: [
      { id: "c5", chapter_code: "5", chapter_title: "第五章", sort_order: 5, enabled: true, chapter_status: "draft", tender_requirement_status: "changed_order", lock_owner: null, blocks: [{ id: "b1", template_chapter_id: "c5", project_id: "p1", block_type: "fixed_text", label: "固定文本", content_text: "旧文本", sort_order: 1, required: true, render_options_json: {}, condition_json: {}, metadata_json: {} }] },
      { id: "c7", chapter_code: "7", chapter_title: "第七章", sort_order: 7, enabled: true, chapter_status: "draft", tender_requirement_status: "not_checked", lock_owner: null, blocks: [{ id: "b2", template_chapter_id: "c7", project_id: "p1", block_type: "seal_mark", label: "公司盖章", sort_order: 1, required: true, render_options_json: {}, condition_json: {}, metadata_json: { confirmation_required: true } }] },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  api.fetchProjectTemplateInstance.mockResolvedValue(instance());
  api.reorderProjectTemplateChapters.mockResolvedValue({ chapters: [instance().chapters[1], instance().chapters[0]] });
  api.updateProjectTemplateBlock.mockResolvedValue({ id: "b1", block_type: "fixed_text", content_text: "新文本" });
  api.confirmProjectTemplateInstance.mockResolvedValue({ id: "inst-1", status: "ready_for_authoring" });
  api.proposeProjectTemplatePromotion.mockResolvedValue({ id: "proposal-1", proposal_status: "draft", diff_json: { summary: { chapter_count: 2 } } });

});

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("ProjectTemplateWorkbench", () => {
  it("loads chapter tree and drags chapter 5 after chapter 7", async () => {
    render(withClient(<ProjectTemplateWorkbench projectId="p1" />));

    await screen.findByText("5 第五章", { selector: "span" });
    const rows = screen.getAllByRole("treeitem");
    fireEvent.dragStart(rows[0]);
    fireEvent.drop(rows[1]);

    await waitFor(() => expect(api.reorderProjectTemplateChapters).toHaveBeenCalled());
    expect(api.reorderProjectTemplateChapters.mock.calls[0][1].ordered_tree.map((row: any) => row.chapter_id)).toEqual(["c7", "c5"]);
  });

  it("rolls back visible order when reorder API fails", async () => {
    api.reorderProjectTemplateChapters.mockRejectedValueOnce(new Error("保存失败"));
    render(withClient(<ProjectTemplateWorkbench projectId="p1" />));

    await screen.findByText("5 第五章", { selector: "span" });
    const dragRows = screen.getAllByRole("treeitem");
    fireEvent.dragStart(dragRows[0]);
    fireEvent.drop(dragRows[1]);

    expect(await screen.findByText("保存失败，已恢复原顺序")).toBeInTheDocument();
    const rows = screen.getAllByRole("treeitem").map((row) => row.textContent);
    expect(rows[0]).toContain("5 第五章");
  });

  it("saves fixed text edits and keeps AI prompt collapsed by default", async () => {
    render(withClient(<ProjectTemplateWorkbench projectId="p1" />));

    const textarea = await screen.findByLabelText("固定文本内容");
    fireEvent.change(textarea, { target: { value: "新文本" } });
    fireEvent.click(screen.getByRole("button", { name: "保存固定文本" }));

    await waitFor(() => expect(api.updateProjectTemplateBlock).toHaveBeenCalledWith("b1", expect.objectContaining({ content_text: "新文本" })));
    expect(screen.queryByLabelText("AI 提示词内容")).not.toBeInTheDocument();
  });

  it("disables confirmation for critical issues and locked chapters", async () => {
    api.fetchProjectTemplateInstance.mockResolvedValueOnce(instance({ reconciliation_summary: { critical: 1 }, chapters: [{ ...instance().chapters[0], lock_owner: "Other" }] }));
    render(withClient(<ProjectTemplateWorkbench projectId="p1" />));

    expect((await screen.findAllByText("Other 正在编辑"))[0]).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /确认模板/ })).toBeDisabled();
  });

  it("shows required seal mark in preview and enables bid authoring after confirmation", async () => {
    render(withClient(<ProjectTemplateWorkbench projectId="p1" />));

    fireEvent.click(await screen.findByText("7 第七章"));
    expect(screen.getByText("[签章] 公司盖章")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /确认模板/ }));

    await waitFor(() => expect(api.confirmProjectTemplateInstance).toHaveBeenCalledWith("inst-1"));
    await waitFor(() => expect(nav.navigate).toHaveBeenCalledWith("authoring", "editor", "p1"));
  });

  it("creates promotion proposal and displays proposal statuses", async () => {
    api.fetchProjectTemplateInstance.mockResolvedValueOnce(instance({
      promotion_proposals: [
        { id: "proposal-draft", proposal_status: "draft" },
        { id: "proposal-submitted", proposal_status: "submitted" },
        { id: "proposal-approved", proposal_status: "approved" },
        { id: "proposal-rejected", proposal_status: "rejected" },
      ],
    }));
    render(withClient(<ProjectTemplateWorkbench projectId="p1" />));

    expect(await screen.findByText("草稿")).toBeInTheDocument();
    expect(screen.getByText("已提交")).toBeInTheDocument();
    expect(screen.getByText("已批准")).toBeInTheDocument();
    expect(screen.getByText("已拒绝")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "提议沉淀为新版模板" }));

    await waitFor(() => expect(api.proposeProjectTemplatePromotion).toHaveBeenCalledWith("inst-1"));
  });

});
