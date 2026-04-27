import { Suspense, lazy, useEffect, useState } from "react";

import { Badge } from "../../../components/ui/Badge";
import { ClayButton } from "../../../components/ui/ClayButton";
import { Icon } from "../../../components/ui/Icon";
import type {
  StandardClauseNode,
  StandardParseAssetSection,
  StandardParseAssetTable,
  StandardParseAssets,
  StandardQualityReport,
  StandardViewerData,
} from "../../../lib/api";
import { StandardClauseTree, findClauseNode, firstClauseNode } from "./StandardClauseTree";
import {
  buildCommentaryHeading,
  cleanStandardClauseText,
  getStandardClauseTitle,
} from "./standardClausePresentation";

const StandardPdfPane = lazy(async () => import("./StandardPdfPane").then((module) => ({
  default: module.StandardPdfPane,
})));

type StandardViewerModalProps = {
  open: boolean;
  mode: "browse" | "search-hit";
  viewerData: StandardViewerData | null;
  parseAssets: StandardParseAssets | null;
  parseAssetsLoading?: boolean;
  parseAssetsError?: string;
  qualityReport?: StandardQualityReport | null;
  qualityReportLoading?: boolean;
  qualityReportError?: string;
  initialClauseId?: string | null;
  onClose: () => void;
};

function clampText(value: string | null | undefined, maxLength = 180): string {
  if (!value) return "";
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength).trimEnd()}...`;
}

function formatPageRange(pageStart: number | null, pageEnd: number | null): string {
  if (pageStart == null && pageEnd == null) return "页码未标注";
  if (pageStart == null) return `P${pageEnd}`;
  if (pageEnd == null || pageStart === pageEnd) return `P${pageStart}`;
  return `P${pageStart}-${pageEnd}`;
}

function formatPercent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "-";
  return `${(value * 100).toFixed(1)}%`;
}

function qualityBadgeVariant(status: "pass" | "review" | "fail"): "success" | "warning" | "danger" {
  if (status === "pass") return "success";
  if (status === "review") return "warning";
  return "danger";
}

function gateBadgeVariant(status: "pass" | "warn" | "fail"): "success" | "warning" | "danger" {
  if (status === "pass") return "success";
  if (status === "warn") return "warning";
  return "danger";
}

function formatRawPreview(value: unknown): string {
  if (value == null) return "无原始载荷";
  if (typeof value === "string") return clampText(value, 320);
  try {
    return clampText(JSON.stringify(value, null, 2), 320);
  } catch {
    return "原始载荷无法序列化";
  }
}

function buildSafeTableHtml(value: string | null | undefined): string | null {
  const rawHtml = value?.trim();
  if (!rawHtml) return null;
  if (typeof DOMParser === "undefined") return rawHtml;

  const document = new DOMParser().parseFromString(rawHtml, "text/html");
  document.querySelectorAll("script, style, iframe, object, embed").forEach((node) => node.remove());
  document.querySelectorAll("*").forEach((element) => {
    for (const attribute of Array.from(element.attributes)) {
      const name = attribute.name.toLowerCase();
      if (name.startsWith("on") || name === "style") {
        element.removeAttribute(attribute.name);
      }
    }
  });

  const table = document.querySelector("table");
  return table?.outerHTML ?? rawHtml;
}

function normalizeSourceLabel(value: string | null | undefined): string | null {
  if (!value) return null;
  return value.replace(/^表格[:：]\s*/u, "").trim() || null;
}

function normalizeText(value: string | null | undefined): string {
  return (value ?? "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function buildKeywords(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>();
  const keywords: string[] = [];
  for (const value of values) {
    const normalized = normalizeText(value);
    if (!normalized) continue;
    if (normalized.length >= 2 && !seen.has(normalized)) {
      seen.add(normalized);
      keywords.push(normalized);
    }
    for (const token of normalized.split(" ")) {
      if (token.length < 2 || seen.has(token)) continue;
      seen.add(token);
      keywords.push(token);
    }
  }
  return keywords;
}

function rangesOverlap(
  startA: number | null,
  endA: number | null,
  startB: number | null,
  endB: number | null,
): boolean {
  const normalizedStartA = startA ?? endA;
  const normalizedEndA = endA ?? startA;
  const normalizedStartB = startB ?? endB;
  const normalizedEndB = endB ?? startB;
  if (normalizedStartA == null || normalizedEndA == null || normalizedStartB == null || normalizedEndB == null) {
    return false;
  }
  return normalizedStartA <= normalizedEndB && normalizedStartB <= normalizedEndA;
}

function rankMatches<T>(
  candidates: T[],
  scoreCandidate: (candidate: T) => number,
): T[] {
  const scored = candidates
    .map((candidate, index) => ({ candidate, index, score: scoreCandidate(candidate) }))
    .filter((item) => item.score > 0)
    .sort((left, right) => right.score - left.score || left.index - right.index);

  if (scored.length === 0) return [];

  const strongestScore = scored[0].score;
  if (strongestScore < 45) {
    return scored.slice(0, 3).map((item) => item.candidate);
  }

  const minimumScore = Math.max(35, Math.floor(strongestScore * 0.45));
  return scored
    .filter((item) => item.score >= minimumScore)
    .slice(0, 3)
    .map((item) => item.candidate);
}

function getRelatedSections(
  parseAssets: StandardParseAssets | null,
  selectedClause: StandardClauseNode | null,
): StandardParseAssetSection[] {
  if (!parseAssets || !selectedClause) return [];

  const clauseCode = normalizeText(selectedClause.clause_no);
  const clauseTitle = normalizeText(selectedClause.clause_title);
  const clauseText = normalizeText(selectedClause.clause_text);
  const keywords = buildKeywords([
    selectedClause.clause_no,
    selectedClause.clause_title,
    selectedClause.source_label,
    selectedClause.clause_text?.slice(0, 48),
  ]);

  return rankMatches(parseAssets.sections, (section) => {
    let score = 0;
    const sectionCode = normalizeText(section.section_code);
    const sectionTitle = normalizeText(section.title);
    const sectionText = normalizeText(section.text);
    const combined = `${sectionCode} ${sectionTitle} ${sectionText}`.trim();

    if (rangesOverlap(section.page_start, section.page_end, selectedClause.page_start, selectedClause.page_end)) {
      score += 24;
    }
    if (clauseCode && sectionCode === clauseCode) {
      score += 80;
    }
    if (clauseTitle && sectionTitle === clauseTitle) {
      score += 70;
    } else if (clauseTitle && sectionTitle && (sectionTitle.includes(clauseTitle) || clauseTitle.includes(sectionTitle))) {
      score += 42;
    }
    if (clauseText && clauseText.length >= 6 && sectionText.includes(clauseText.slice(0, Math.min(24, clauseText.length)))) {
      score += 55;
    }
    for (const keyword of keywords) {
      if (combined.includes(keyword)) {
        score += keyword.length >= 6 ? 12 : 6;
      }
    }

    return score;
  });
}

function getRelatedTables(
  parseAssets: StandardParseAssets | null,
  selectedClause: StandardClauseNode | null,
): StandardParseAssetTable[] {
  if (!parseAssets || !selectedClause) return [];
  const normalizedLabel = normalizeSourceLabel(selectedClause.source_label);
  const normalizedLabelText = normalizeText(normalizedLabel);
  const clauseCode = normalizeText(selectedClause.clause_no);
  const clauseTitle = normalizeText(selectedClause.clause_title);
  const clauseText = normalizeText(selectedClause.clause_text);
  const keywords = buildKeywords([
    normalizedLabel,
    selectedClause.clause_no,
    selectedClause.clause_title,
    selectedClause.clause_text?.slice(0, 32),
  ]);

  return rankMatches(parseAssets.tables, (table) => {
    let score = 0;
    const tableTitle = normalizeText(table.table_title);
    const tableHtml = normalizeText(table.table_html);
    const tableRaw = normalizeText(formatRawPreview(table.raw_json));
    const combined = `${tableTitle} ${tableHtml} ${tableRaw}`.trim();

    if (rangesOverlap(table.page_start, table.page_end, selectedClause.page_start, selectedClause.page_end)) {
      score += 18;
    }
    if (selectedClause.source_type === "table" && normalizedLabelText && tableTitle === normalizedLabelText) {
      score += 95;
    } else if (selectedClause.source_type === "table" && normalizedLabelText && tableTitle
      && (tableTitle.includes(normalizedLabelText) || normalizedLabelText.includes(tableTitle))) {
      score += 56;
    }
    if (clauseTitle && tableTitle && (tableTitle.includes(clauseTitle) || clauseTitle.includes(tableTitle))) {
      score += 36;
    }
    if (clauseCode && combined.includes(clauseCode)) {
      score += 24;
    }
    if (clauseText && clauseText.length >= 4 && combined.includes(clauseText.slice(0, Math.min(16, clauseText.length)))) {
      score += 30;
    }
    for (const keyword of keywords) {
      if (combined.includes(keyword)) {
        score += keyword.length >= 6 ? 10 : 5;
      }
    }

    return score;
  });
}

function findParentClauseNode(
  nodes: StandardClauseNode[],
  clauseId: string | null,
  parent: StandardClauseNode | null = null,
): StandardClauseNode | null {
  if (!clauseId) return null;
  for (const node of nodes) {
    if (node.id === clauseId) return parent;
    const nested = findParentClauseNode(node.children, clauseId, node);
    if (nested) return nested;
  }
  return null;
}

function isPollutedCommentaryLocation(node: StandardClauseNode | null): boolean {
  if (!node || node.clause_type !== "commentary") return false;
  const sourceLabel = (node.source_label ?? "").trim();
  if (!sourceLabel) return false;
  return /^(前言|2\s*术语|本规范用词说明|引用标准名录)/u.test(sourceLabel);
}

export function StandardViewerModal({
  open,
  mode,
  viewerData,
  parseAssets,
  parseAssetsLoading = false,
  parseAssetsError = "",
  qualityReport = null,
  qualityReportLoading = false,
  qualityReportError = "",
  initialClauseId = null,
  onClose,
}: StandardViewerModalProps) {
  const [selectedClauseId, setSelectedClauseId] = useState<string | null>(initialClauseId);

  useEffect(() => {
    if (!open || !viewerData) return;
    const nextClause = initialClauseId ?? firstClauseNode(viewerData.clause_tree)?.id ?? null;
    setSelectedClauseId(nextClause);
  }, [initialClauseId, open, viewerData]);

  if (!open || !viewerData) return null;

  const selectedClause = findClauseNode(viewerData.clause_tree, selectedClauseId)
    ?? firstClauseNode(viewerData.clause_tree);
  const parentClause = selectedClause?.clause_type === "commentary"
    ? findParentClauseNode(viewerData.clause_tree, selectedClause.id)
    : null;
  const selectedClauseMarker = selectedClause?.node_label
    ? `${selectedClause.clause_no ?? ""} ${selectedClause.node_label}`.trim()
    : selectedClause?.clause_no ?? null;
  const commentaryClauses = selectedClause?.clause_type === "normative"
    ? selectedClause.children.filter((child) => child.clause_type === "commentary")
    : [];
  const selectedClausePageStart = selectedClause?.page_start;
  const parentClausePageStart = parentClause?.page_start;
  const parentClausePageEnd = parentClause?.page_end;
  const fallbackToParentClausePage = isPollutedCommentaryLocation(selectedClause)
    && parentClausePageStart != null
    && parentClausePageStart > 0;
  const fallbackCommentaryPage = commentaryClauses.find(
    (child) => child.page_start != null && child.page_start > 0,
  )?.page_start;
  const targetPage = fallbackToParentClausePage
    ? Math.max(parentClausePageStart ?? 1, 1)
    : selectedClausePageStart != null
    ? Math.max(selectedClausePageStart, 1)
    : fallbackCommentaryPage ?? null;
  const displayPageStart = fallbackToParentClausePage
    ? Math.max(parentClausePageStart ?? 1, 1)
    : selectedClausePageStart != null
    ? Math.max(selectedClausePageStart, 1)
    : fallbackCommentaryPage ?? null;
  const displayPageEnd = fallbackToParentClausePage
    ? (parentClausePageEnd != null
      ? Math.max(parentClausePageEnd, displayPageStart ?? 1)
      : displayPageStart)
    : selectedClause?.page_end != null
    ? Math.max(selectedClause.page_end, displayPageStart ?? 1)
    : commentaryClauses.find((child) => child.page_end != null && child.page_end > 0)?.page_end
      ?? displayPageStart;
  const relatedSections = getRelatedSections(parseAssets, selectedClause ?? null);
  const relatedTables = getRelatedTables(parseAssets, selectedClause ?? null);
  const parserLabel = [parseAssets?.document?.parser_name, parseAssets?.document?.parser_version]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="standard-viewer-modal">
      <div className="standard-viewer-modal__backdrop" onClick={onClose} />
      <div className="standard-viewer-modal__panel">
        <div className="standard-viewer-modal__header">
          <div>
            <div className="standard-viewer-modal__eyebrow">
              <Badge variant={mode === "search-hit" ? "primary" : "default"}>
                {mode === "search-hit" ? "查询命中" : "规范查阅"}
              </Badge>
              {viewerData.specialty && <span>{viewerData.specialty}</span>}
            </div>
            <h2>{viewerData.standard_code} {viewerData.standard_name}</h2>
          </div>
          <ClayButton type="button" variant="ghost" size="sm" onClick={onClose}>
            <Icon name="x" size={16} /> 关闭
          </ClayButton>
        </div>

        <div className="standard-viewer-modal__body">
          <div className="standard-viewer-modal__pdf">
            <Suspense fallback={(
              <div className="empty-state">
                <div className="spinner" />
                <p>PDF 组件加载中...</p>
              </div>
            )}
            >
              <StandardPdfPane
                pdfUrl={viewerData.pdf_url}
                targetPage={targetPage}
              />
            </Suspense>
          </div>

          <div className="standard-viewer-modal__aside">
            <div className="standard-viewer-modal__tree">
              <StandardClauseTree
                nodes={viewerData.clause_tree}
                selectedClauseId={selectedClause?.id ?? null}
                onSelectClause={(node) => setSelectedClauseId(node.id)}
              />
            </div>

            <div className="standard-viewer-modal__detail">
              {selectedClause ? (
                <>
                  <div className="standard-viewer-modal__detail-header">
                    {selectedClauseMarker && <span>{selectedClauseMarker}</span>}
                    <strong>{getStandardClauseTitle(selectedClause)}</strong>
                  </div>
                  {selectedClause.summary && (
                    <p className="standard-viewer-modal__summary">{cleanStandardClauseText(selectedClause.summary)}</p>
                  )}
                  {selectedClause.source_type && selectedClause.source_type !== "text" && (
                    <div className="standard-viewer-modal__tags">
                      <Badge variant="warning">
                        {selectedClause.source_type === "table" ? "来自表格" : selectedClause.source_type}
                      </Badge>
                      {selectedClause.source_label && (
                        <Badge variant="default">{selectedClause.source_label}</Badge>
                      )}
                    </div>
                  )}
                  {selectedClause.clause_text && (
                    <p className="standard-viewer-modal__text">{cleanStandardClauseText(selectedClause.clause_text)}</p>
                  )}
                  {!selectedClause.clause_text && selectedClause.clause_type === "outline" && (
                    <p className="standard-viewer-modal__text">
                      当前选中的是目录节点，可继续展开查看其下 AI 条款。
                    </p>
                  )}
                  {commentaryClauses.length > 0 && (
                    <>
                      <div className="standard-viewer-modal__detail-header">
                        <strong>{buildCommentaryHeading(commentaryClauses[0]?.clause_no ?? selectedClause.clause_no)}</strong>
                      </div>
                      {commentaryClauses.map((commentary) => (
                        <p key={commentary.id} className="standard-viewer-modal__text">
                          {cleanStandardClauseText(commentary.clause_text)}
                        </p>
                      ))}
                    </>
                  )}
                  {selectedClause.tags.length > 0 && (
                    <div className="standard-viewer-modal__tags">
                      {selectedClause.tags.map((tag) => (
                        <Badge key={tag} variant="info">{tag}</Badge>
                      ))}
                    </div>
                  )}
                  <div className="standard-viewer-modal__page">
                    原文页码：
                    {displayPageStart != null
                      ? ` P${displayPageStart}${displayPageEnd && displayPageEnd !== displayPageStart ? `-${displayPageEnd}` : ""}`
                      : " 未标注"}
                  </div>
                  <details className="standard-viewer-modal__diagnostics" open={mode === "search-hit"}>
                    <summary className="standard-viewer-modal__diagnostics-summary">
                      <span>解析诊断</span>
                      {parseAssets && (
                        <span className="standard-viewer-modal__diagnostics-count">
                          {parseAssets.sections.length} 段 / {parseAssets.tables.length} 表
                        </span>
                      )}
                    </summary>
                    <div className="standard-viewer-modal__diagnostics-body">
                      {parseAssetsLoading && (
                        <div className="standard-viewer-modal__diagnostics-note">正在加载解析诊断数据...</div>
                      )}
                      {!parseAssetsLoading && parseAssetsError && (
                        <div className="warning-banner">{parseAssetsError}</div>
                      )}
                      {!parseAssetsLoading && !parseAssetsError && (
                        <>
                          <div className="standard-viewer-modal__tags">
                            <Badge variant="info">{parserLabel || "解析器未标注"}</Badge>
                            <Badge variant="default">段落 {parseAssets?.sections.length ?? 0}</Badge>
                            <Badge variant="default">表格 {parseAssets?.tables.length ?? 0}</Badge>
                            <Badge variant={selectedClause?.source_type === "table" ? "warning" : "default"}>
                              来源 {selectedClause?.source_type === "table" ? "表格" : "正文"}
                            </Badge>
                            {selectedClause?.source_label && (
                              <Badge variant="default">{selectedClause.source_label}</Badge>
                            )}
                          </div>

                          {qualityReportLoading && (
                            <div className="standard-viewer-modal__diagnostics-note">正在加载入库质量报告...</div>
                          )}
                          {!qualityReportLoading && qualityReportError && (
                            <div className="warning-banner">{qualityReportError}</div>
                          )}
                          {qualityReport && (
                            <div className="standard-viewer-modal__asset-group">
                              <div className="standard-viewer-modal__asset-title">入库质量</div>
                              <div className="standard-viewer-modal__tags">
                                <Badge variant={qualityBadgeVariant(qualityReport.overview.status)}>
                                  {qualityReport.overview.status === "pass"
                                    ? "通过"
                                    : qualityReport.overview.status === "review"
                                      ? "需复核"
                                      : "未通过"}
                                </Badge>
                                <Badge variant="default">
                                  段落锚点 {formatPercent(qualityReport.metrics.section_anchor_coverage)}
                                </Badge>
                                <Badge variant="default">
                                  条款锚点 {formatPercent(qualityReport.metrics.clause_anchor_coverage)}
                                </Badge>
                                <Badge variant="default">
                                  校验问题 {qualityReport.metrics.validation_issue_count}
                                </Badge>
                                <Badge variant="default">
                                  表格条款 {qualityReport.metrics.table_clause_count}/{qualityReport.metrics.table_count}
                                </Badge>
                              </div>
                              <div className="standard-viewer-modal__diagnostics-note">
                                {qualityReport.overview.summary}
                              </div>
                              <div className="standard-viewer-modal__tags">
                                {qualityReport.gates.map((gate) => (
                                  <Badge key={gate.code} variant={gateBadgeVariant(gate.status)}>
                                    {gate.code}
                                  </Badge>
                                ))}
                              </div>
                              {qualityReport.gates.map((gate) => (
                                <div key={gate.code} className="standard-viewer-modal__asset-card">
                                  <div className="standard-viewer-modal__asset-meta">
                                    <strong>{gate.code}</strong>
                                    <span>{gate.status}</span>
                                  </div>
                                  <p className="standard-viewer-modal__asset-text">{gate.message}</p>
                                </div>
                              ))}
                              {qualityReport.recommended_skills.length > 0 && (
                                <>
                                  <div className="standard-viewer-modal__asset-title">建议 Skills</div>
                                  {qualityReport.recommended_skills.map((skill) => (
                                    <div key={skill.skill_name} className="standard-viewer-modal__asset-card">
                                      <div className="standard-viewer-modal__asset-meta">
                                        <strong>{skill.skill_name}</strong>
                                        <span>{skill.active ? "已接入" : "未启用"}</span>
                                      </div>
                                      <p className="standard-viewer-modal__asset-text">{skill.reason}</p>
                                    </div>
                                  ))}
                                </>
                              )}
                              {qualityReport.top_issues.length > 0 && (
                                <>
                                  <div className="standard-viewer-modal__asset-title">重点问题</div>
                                  {qualityReport.top_issues.map((issue) => (
                                    <div key={`${issue.code}-${issue.clause_no ?? "root"}-${issue.message}`} className="standard-viewer-modal__asset-card">
                                      <div className="standard-viewer-modal__asset-meta">
                                        <strong>{issue.code}</strong>
                                        <span>{issue.clause_no ?? "未定位条款"}</span>
                                      </div>
                                      <p className="standard-viewer-modal__asset-text">{issue.message}</p>
                                    </div>
                                  ))}
                                </>
                              )}
                            </div>
                          )}

                          {relatedSections.length > 0 && (
                            <div className="standard-viewer-modal__asset-group">
                              <div className="standard-viewer-modal__asset-title">相关原始段落</div>
                              {relatedSections.map((section) => (
                                <div key={section.id} className="standard-viewer-modal__asset-card">
                                  <div className="standard-viewer-modal__asset-meta">
                                    <strong>{section.section_code ? `${section.section_code} ` : ""}{section.title}</strong>
                                    <span>{formatPageRange(section.page_start, section.page_end)}</span>
                                  </div>
                                  <div className="standard-viewer-modal__asset-caption">
                                    text_source: {section.text_source ?? "unknown"} · sort_order: {section.sort_order ?? "-"}
                                  </div>
                                  {section.text && (
                                    <p className="standard-viewer-modal__asset-text">{clampText(cleanStandardClauseText(section.text), 220)}</p>
                                  )}
                                  <details className="standard-viewer-modal__document-raw">
                                    <summary>查看原始解析数据</summary>
                                    <pre className="standard-viewer-modal__asset-raw">{formatRawPreview(section.raw_json)}</pre>
                                  </details>
                                </div>
                              ))}
                            </div>
                          )}

                          {relatedTables.length > 0 && (
                            <div className="standard-viewer-modal__asset-group">
                              <div className="standard-viewer-modal__asset-title">相关原始表格</div>
                              {relatedTables.map((table) => (
                                <div key={table.id} className="standard-viewer-modal__asset-card">
                                  <div className="standard-viewer-modal__asset-meta">
                                    <strong>{table.table_title ?? "未命名表格"}</strong>
                                    <span>{formatPageRange(table.page_start ?? table.page, table.page_end ?? table.page)}</span>
                                  </div>
                                  {table.table_html ? (
                                    <div className="standard-viewer-modal__table-wrap">
                                      <div
                                        className="standard-viewer-modal__table-html"
                                        dangerouslySetInnerHTML={{ __html: buildSafeTableHtml(table.table_html) ?? "" }}
                                      />
                                    </div>
                                  ) : (
                                    <p className="standard-viewer-modal__asset-text">该表格暂无可渲染的 HTML 内容。</p>
                                  )}
                                  <details className="standard-viewer-modal__document-raw">
                                    <summary>查看原始解析数据</summary>
                                    <pre className="standard-viewer-modal__asset-raw">{formatRawPreview(table.raw_json)}</pre>
                                  </details>
                                </div>
                              ))}
                            </div>
                          )}

                          {relatedSections.length === 0 && relatedTables.length === 0 && (
                            <div className="standard-viewer-modal__diagnostics-note">
                              当前条款还没有匹配到可预览的原始段落或表格，可结合页码与来源标签继续排查。
                            </div>
                          )}

                          {parseAssets?.document?.raw_payload && (
                            <details className="standard-viewer-modal__document-raw">
                              <summary>查看文档级原始解析数据</summary>
                              <pre className="standard-viewer-modal__asset-raw">
                                {formatRawPreview(parseAssets.document.raw_payload)}
                              </pre>
                            </details>
                          )}
                        </>
                      )}
                    </div>
                  </details>
                </>
              ) : (
                <div className="empty-state">未找到条款详情</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
