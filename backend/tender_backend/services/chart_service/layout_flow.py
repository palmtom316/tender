from __future__ import annotations


def compute_flow_layout(node_ids: list[str], edges: list[tuple[str, str]]) -> dict[str, tuple[int, int]]:
    incoming = {node_id: 0 for node_id in node_ids}
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for from_id, to_id in edges:
        outgoing.setdefault(from_id, []).append(to_id)
        incoming[to_id] = incoming.get(to_id, 0) + 1

    roots = [node_id for node_id in node_ids if incoming.get(node_id, 0) == 0] or node_ids[:1]
    row_by_id: dict[str, int] = {node_id: 0 for node_id in roots}
    queue = list(roots)
    max_relaxations = max(len(node_ids) - 1, 0)
    relaxations = {node_id: 0 for node_id in node_ids}

    while queue:
        current = queue.pop(0)
        for child in outgoing.get(current, []):
            next_row = row_by_id[current] + 1
            if child not in row_by_id or next_row > row_by_id[child]:
                if relaxations.get(child, 0) >= max_relaxations:
                    continue
                row_by_id[child] = next_row
                relaxations[child] = relaxations.get(child, 0) + 1
                queue.append(child)

    for node_id in node_ids:
        row_by_id.setdefault(node_id, max(row_by_id.values(), default=0) + 1)

    rows: dict[int, list[str]] = {}
    for node_id in node_ids:
        rows.setdefault(row_by_id[node_id], []).append(node_id)

    layout: dict[str, tuple[int, int]] = {}
    max_cols = max((len(values) for values in rows.values()), default=1)
    for row, ids in rows.items():
        pad = max((max_cols - len(ids)) // 2, 0)
        for col, node_id in enumerate(ids, start=pad):
            layout[node_id] = (col, row)
    return layout
