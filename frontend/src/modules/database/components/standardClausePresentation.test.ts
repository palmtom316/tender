import { describe, expect, it } from "vitest";

import type { StandardClauseNode } from "../../../lib/api";
import {
  buildCommentaryHeading,
  cleanStandardClauseText,
  getStandardClauseMarker,
  getStandardClauseTitle,
} from "./standardClausePresentation";

function createNode(overrides: Partial<StandardClauseNode>): StandardClauseNode {
  return {
    id: "node-1",
    clause_no: "4.2.1",
    node_type: "clause",
    node_key: null,
    node_label: null,
    clause_title: null,
    clause_text: "默认条文",
    summary: null,
    tags: [],
    clause_type: "normative",
    source_type: "text",
    source_label: null,
    page_start: 1,
    page_end: 1,
    sort_order: 1,
    parent_id: null,
    children: [],
    ...overrides,
  };
}

describe("standardClausePresentation", () => {
  it("removes latex-style OCR artifacts from displayed clause text", () => {
    expect(cleanStandardClauseText("3\\mathrm{kV} \\sim 750\\mathrm{kV}")).toBe("3kV ~ 750kV");
    expect(cleanStandardClauseText("0^{\\circ}\\mathrm{C}")).toBe("0°C");
    expect(cleanStandardClauseText("\\mathrm{SF}_6")).toBe("SF6");
  });

  it("formats commentary headings with the clause number", () => {
    expect(buildCommentaryHeading("4.8.2")).toBe("4.8.2 条文说明");
    expect(buildCommentaryHeading(null)).toBe("条文说明");
  });

  it("hides duplicated parent clause markers for item nodes", () => {
    const itemNode = createNode({ node_type: "item", clause_text: "设备到达现场后应及时检查。" });
    expect(getStandardClauseMarker(itemNode, "4.2.1")).toBeNull();
    expect(getStandardClauseMarker(itemNode, null)).toBe("4.2.1");
  });

  it("renders commentary nodes with a stable title", () => {
    const commentaryNode = createNode({
      clause_type: "commentary",
      node_type: "commentary",
      clause_title: null,
      clause_text: "本条说明。",
    });
    expect(getStandardClauseTitle(commentaryNode)).toBe("条文说明");
  });
});
