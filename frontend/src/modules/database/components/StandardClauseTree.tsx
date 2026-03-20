import { useEffect, useState } from "react";

import { Badge } from "../../../components/ui/Badge";
import { Icon } from "../../../components/ui/Icon";
import type { StandardClauseNode } from "../../../lib/api";

type StandardClauseTreeProps = {
  nodes: StandardClauseNode[];
  selectedClauseId: string | null;
  onSelectClause: (node: StandardClauseNode) => void;
};

function containsNode(nodes: StandardClauseNode[], targetId: string | null): boolean {
  if (!targetId) return false;
  for (const node of nodes) {
    if (node.id === targetId) return true;
    if (containsNode(node.children, targetId)) return true;
  }
  return false;
}

function findNode(nodes: StandardClauseNode[], targetId: string | null): StandardClauseNode | null {
  if (!targetId) return null;
  for (const node of nodes) {
    if (node.id === targetId) return node;
    const childMatch = findNode(node.children, targetId);
    if (childMatch) return childMatch;
  }
  return null;
}

function ClauseTreeItem({
  node,
  depth,
  selectedClauseId,
  onSelectClause,
}: {
  node: StandardClauseNode;
  depth: number;
  selectedClauseId: string | null;
  onSelectClause: (node: StandardClauseNode) => void;
}) {
  const hasChildren = node.children.length > 0;
  const shouldOpen = depth === 0 || containsNode(node.children, selectedClauseId);
  const [expanded, setExpanded] = useState(shouldOpen);

  useEffect(() => {
    if (containsNode(node.children, selectedClauseId)) {
      setExpanded(true);
    }
  }, [node.children, selectedClauseId]);

  return (
    <div className="standard-clause-tree__node">
      <button
        type="button"
        className={`standard-clause-tree__row ${selectedClauseId === node.id ? "is-selected" : ""}`}
        style={{ paddingLeft: `${12 + depth * 18}px` }}
        onClick={() => onSelectClause(node)}
      >
        <span
          className="standard-clause-tree__toggle"
          onClick={(event) => {
            event.stopPropagation();
            if (hasChildren) setExpanded((value) => !value);
          }}
        >
          {hasChildren ? <Icon name={expanded ? "chevron-down" : "chevron-right"} size={14} /> : null}
        </span>
        <span className="standard-clause-tree__meta">
          {node.clause_no && <span className="standard-clause-tree__no">{node.clause_no}</span>}
          <span className="standard-clause-tree__title">
            {node.clause_title || node.clause_text || "未命名条款"}
          </span>
        </span>
        {node.page_start != null && (
          <Badge variant="default">P{node.page_start}</Badge>
        )}
      </button>

      {expanded && hasChildren && (
        <div className="standard-clause-tree__children">
          {node.children.map((child) => (
            <ClauseTreeItem
              key={child.id}
              node={child}
              depth={depth + 1}
              selectedClauseId={selectedClauseId}
              onSelectClause={onSelectClause}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function findClauseNode(
  nodes: StandardClauseNode[],
  clauseId: string | null,
): StandardClauseNode | null {
  return findNode(nodes, clauseId);
}

export function firstClauseNode(nodes: StandardClauseNode[]): StandardClauseNode | null {
  if (nodes.length === 0) return null;
  const [first] = nodes;
  return first.children.length > 0 ? firstClauseNode(first.children) ?? first : first;
}

export function StandardClauseTree({
  nodes,
  selectedClauseId,
  onSelectClause,
}: StandardClauseTreeProps) {
  if (nodes.length === 0) {
    return <div className="empty-state">暂无可展示条款</div>;
  }

  return (
    <div className="standard-clause-tree">
      {nodes.map((node) => (
        <ClauseTreeItem
          key={node.id}
          node={node}
          depth={0}
          selectedClauseId={selectedClauseId}
          onSelectClause={onSelectClause}
        />
      ))}
    </div>
  );
}
