import { useEffect, useState } from "react";

import { Badge } from "../../../components/ui/Badge";
import { ClayButton } from "../../../components/ui/ClayButton";
import { Icon } from "../../../components/ui/Icon";
import type { StandardViewerData } from "../../../lib/api";
import { StandardClauseTree, findClauseNode, firstClauseNode } from "./StandardClauseTree";
import { StandardPdfPane } from "./StandardPdfPane";

type StandardViewerModalProps = {
  open: boolean;
  mode: "browse" | "search-hit";
  viewerData: StandardViewerData | null;
  initialClauseId?: string | null;
  onClose: () => void;
};

export function StandardViewerModal({
  open,
  mode,
  viewerData,
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
            <StandardPdfPane
              pdfUrl={viewerData.pdf_url}
              targetPage={selectedClause?.page_start ?? null}
            />
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
                    {selectedClause.clause_no && <span>{selectedClause.clause_no}</span>}
                    <strong>{selectedClause.clause_title || "条款详情"}</strong>
                  </div>
                  {selectedClause.summary && (
                    <p className="standard-viewer-modal__summary">{selectedClause.summary}</p>
                  )}
                  {selectedClause.clause_text && (
                    <p className="standard-viewer-modal__text">{selectedClause.clause_text}</p>
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
                    {selectedClause.page_start != null
                      ? ` P${selectedClause.page_start}${selectedClause.page_end && selectedClause.page_end !== selectedClause.page_start ? `-${selectedClause.page_end}` : ""}`
                      : " 未标注"}
                  </div>
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
