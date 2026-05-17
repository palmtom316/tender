from __future__ import annotations

from tender_backend.services.chart_service.layout_flow import compute_flow_layout


def test_linear_flow_layout_stacks_nodes_by_dependency_order() -> None:
    layout = compute_flow_layout(
        node_ids=["start", "execute", "review"],
        edges=[("start", "execute"), ("execute", "review")],
    )

    assert layout["start"][1] < layout["execute"][1] < layout["review"][1]
    assert len(set(layout.values())) == 3


def test_branching_flow_layout_assigns_distinct_positions() -> None:
    layout = compute_flow_layout(
        node_ids=["root", "quality", "safety", "team"],
        edges=[("root", "quality"), ("root", "safety"), ("quality", "team"), ("safety", "team")],
    )

    assert len(set(layout.values())) == 4
    assert layout["root"][1] < layout["quality"][1]
    assert layout["root"][1] < layout["safety"][1]
    assert layout["team"][1] > layout["quality"][1]


def test_cycle_flow_layout_terminates_and_keeps_all_nodes() -> None:
    layout = compute_flow_layout(
        node_ids=["check", "rectify"],
        edges=[("check", "rectify"), ("rectify", "check")],
    )

    assert set(layout) == {"check", "rectify"}
    assert len(set(layout.values())) == 2
