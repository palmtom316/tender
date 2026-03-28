import type { StandardClauseNode } from "../../../lib/api";

type ClausePresentationNode = Pick<
  StandardClauseNode,
  "clause_no" | "clause_text" | "clause_title" | "clause_type" | "node_label" | "node_type"
>;

export function cleanStandardClauseText(value: string | null | undefined): string {
  if (!value) return "";

  return value
    .replace(/\\mathrm\{([^}]*)\}/gu, "$1")
    .replace(/\\text\{([^}]*)\}/gu, "$1")
    .replace(/\^\{\\circ\}/gu, "°")
    .replace(/\\sim/gu, "~")
    .replace(/\\cdot/gu, "·")
    .replace(/\\delta/gu, "δ")
    .replace(/\\%/gu, "%")
    .replace(/_\{([^}]*)\}/gu, "$1")
    .replace(/_([0-9A-Za-z]+)/gu, "$1")
    .replace(/[ \t]+\n/gu, "\n")
    .replace(/\n{3,}/gu, "\n\n")
    .trim();
}

export function buildCommentaryHeading(clauseNo: string | null | undefined): string {
  const normalizedClauseNo = clauseNo?.trim();
  return normalizedClauseNo ? `${normalizedClauseNo} 条文说明` : "条文说明";
}

export function getStandardClauseMarker(
  node: ClausePresentationNode,
  parentClauseNo: string | null = null,
): string | null {
  if (node.node_label) return node.node_label;
  if (!node.clause_no) return null;
  if (node.node_type !== "clause" && parentClauseNo && node.clause_no === parentClauseNo) {
    return null;
  }
  return node.clause_no;
}

export function getStandardClauseTitle(node: ClausePresentationNode): string {
  if (node.clause_type === "commentary") {
    return "条文说明";
  }
  return cleanStandardClauseText(node.clause_title) || cleanStandardClauseText(node.clause_text) || "未命名条款";
}
