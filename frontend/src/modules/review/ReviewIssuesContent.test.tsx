import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { useNavigationMock, fetchReviewIssuesMock, resolveIssueMock, runBidReviewMock } = vi.hoisted(() => ({
  useNavigationMock: vi.fn(),
  fetchReviewIssuesMock: vi.fn(),
  resolveIssueMock: vi.fn(),
  runBidReviewMock: vi.fn(),
}));

vi.mock("../../lib/NavigationContext", () => ({
  useNavigation: useNavigationMock,
}));

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual("../../lib/api");
  return {
    ...actual,
    fetchReviewIssues: fetchReviewIssuesMock,
    resolveIssue: resolveIssueMock,
    runBidReview: runBidReviewMock,
  };
});

import { ReviewIssuesContent } from "./ReviewIssuesContent";

function withClient(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>;
}

describe("ReviewIssuesContent", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useNavigationMock.mockReturnValue({ projectId: "proj-1" });
    fetchReviewIssuesMock.mockResolvedValue([
      {
        id: "issue-1",
        severity: "P1",
        title: "章节质量指标不足",
        detail: "章节缺少足够的策略章节、约束响应或实质段落。",
        resolved: false,
        metadata_json: {
          quality_metrics: {
            required_section_coverage: 0.5,
            confirmed_constraint_coverage: 0.25,
            standard_clause_support_count: 1,
            scoring_item_coverage: 0,
            chart_placeholder_count: 1,
            generic_phrase_density: 2,
            substantive_paragraph_count: 1,
            minimum_substantive_paragraph_count: 3,
          },
        },
      },
    ]);
  });

  it("shows topic-level chapter quality metrics from review metadata", async () => {
    render(withClient(<ReviewIssuesContent />));

    expect(await screen.findByText("章节质量指标不足")).toBeInTheDocument();
    expect(screen.getByText("策略章节覆盖 50%")).toBeInTheDocument();
    expect(screen.getByText("约束响应覆盖 25%")).toBeInTheDocument();
    expect(screen.getByText("实质段落 1/3")).toBeInTheDocument();
    expect(screen.getByText("泛化密度 2")).toBeInTheDocument();
  });
});

it("routes template-caused and content-caused issues to the right workspace", async () => {
  const navigate = vi.fn();
  useNavigationMock.mockReturnValue({ projectId: "proj-1", navigate });
  fetchReviewIssuesMock.mockResolvedValue([
    { id: "issue-template", severity: "P1", title: "模板提示词问题", detail: "prompt", resolved: false, issue_source: "template_prompt", suggested_workspace: "template", metadata_json: {} },
    { id: "issue-editor", severity: "P2", title: "正文事实错误", detail: "fact", resolved: false, issue_source: "generated_content", suggested_workspace: "editor", metadata_json: {} },
  ]);

  render(withClient(<ReviewIssuesContent />));

  (await screen.findByRole("button", { name: "去模板调整" })).click();
  expect(navigate).toHaveBeenCalledWith("authoring", "template", "proj-1");
  screen.getByRole("button", { name: "去标书编写" }).click();
  expect(navigate).toHaveBeenCalledWith("authoring", "editor", "proj-1");
});
