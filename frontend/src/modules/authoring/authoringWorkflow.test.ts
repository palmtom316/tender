import { describe, expect, it } from "vitest";
import { MODULE_CONFIG } from "../../lib/navigation";
import { authoringSteps, editorBlockReason, nextAuthoringTab, projectNextAction } from "./authoringWorkflow";

describe("authoringWorkflow", () => {
  it("routes new projects without documents to upload", () => {
    expect(nextAuthoringTab({ hasDocument: false })).toBe("upload");
    expect(projectNextAction({ hasDocument: false })).toEqual({ tab: "upload", label: "上传招标文件" });
  });

  it("routes parsed documents with unconfirmed requirements to requirements", () => {
    expect(nextAuthoringTab({ hasDocument: true, parseStatus: "done", requirementsConfirmed: false })).toBe("requirements");
  });

  it("routes confirmed requirements with draft template to template", () => {
    expect(nextAuthoringTab({ hasDocument: true, parseStatus: "done", requirementsConfirmed: true, templateStatus: "draft" })).toBe("template");
  });

  it("routes confirmed template to editor", () => {
    expect(nextAuthoringTab({ hasDocument: true, parseStatus: "done", requirementsConfirmed: true, templateStatus: "ready_for_authoring" })).toBe("editor");
  });

  it("blocks editor when template has critical blockers", () => {
    const status = { hasDocument: true, parseStatus: "done" as const, requirementsConfirmed: true, templateStatus: "needs_reconciliation" as const, unresolvedCriticalIssues: 2 };
    expect(editorBlockReason(status)).toContain("2 个模板阻断问题");
    expect(authoringSteps(status, "template").find((step) => step.id === "template")?.state).toBe("active");
  });

  it("adds template tab between requirements and editor", () => {
    const authoringTabs = MODULE_CONFIG.find((module) => module.id === "authoring")!.tabs;
    expect(authoringTabs.map((tab) => tab.id)).toEqual(["upload", "parse", "requirements", "template", "editor"]);
    expect(authoringTabs[3].label).toBe("模板调整");
  });
});
