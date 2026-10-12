# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Tree rules of the one project breakdown structure (``ProjectWBS``). Pure, no database.

The tree is stored by ``projects`` (SPEC decision 1); this module owns its
rules. Codes are unique per project (rule 1), a child code starts with its
parent's code plus the separator when hierarchical codes are on (rule 2), a
renumber moves the whole subtree in one plan, and a closed node accepts no new
children (rule 3). Uniqueness is compared case-insensitively, because a code
is typed by people and read by people.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

NODE_KINDS: tuple[str, ...] = ("location", "system", "package", "phase", "cost")


@dataclass(frozen=True)
class Node:
    id: uuid.UUID
    parent_id: uuid.UUID | None
    code: str
    closed: bool = False


class WbsRuleError(ValueError):
    """A refused tree change; ``code`` is the error code."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


def _key(code: str) -> str:
    return (code or "").strip().casefold()


def duplicate_codes(nodes: Iterable[Node]) -> dict[str, list[uuid.UUID]]:
    """Codes held by more than one node (existing dirty data is listed, never silently merged)."""
    seen: dict[str, list[Node]] = {}
    for n in nodes:
        seen.setdefault(_key(n.code), []).append(n)
    return {group[0].code: [n.id for n in group] for group in seen.values() if len(group) > 1}


def descendants(nodes: Sequence[Node], node_id: uuid.UUID) -> list[Node]:
    """Every node below ``node_id`` (not the node itself), parents before children."""
    children: dict[uuid.UUID | None, list[Node]] = {}
    for n in nodes:
        children.setdefault(n.parent_id, []).append(n)
    out: list[Node] = []
    stack = list(children.get(node_id, []))
    while stack:
        n = stack.pop(0)
        out.append(n)
        stack.extend(children.get(n.id, []))
    return out


def check_code(
    nodes: Sequence[Node],
    *,
    code: str,
    parent_id: uuid.UUID | None,
    node_id: uuid.UUID | None = None,
    hierarchical: bool = True,
    separator: str = ".",
) -> None:
    """Rules 1-3 for a new or changed node; raises :class:`WbsRuleError`."""
    if not (code or "").strip():
        raise WbsRuleError("wbs_code_required")
    by_id = {n.id: n for n in nodes}
    others = [n for n in nodes if n.id != node_id]
    if any(_key(n.code) == _key(code) for n in others):
        raise WbsRuleError("wbs_code_duplicate", code)
    if parent_id is not None:
        parent = by_id.get(parent_id)
        if parent is None:
            raise WbsRuleError("wbs_parent_not_found")
        if parent.closed:
            raise WbsRuleError("wbs_node_closed", parent.code)
        if node_id is not None and (parent_id == node_id or parent_id in {d.id for d in descendants(nodes, node_id)}):
            raise WbsRuleError("wbs_move_cycle")
        if hierarchical and not (code.startswith(parent.code + separator) and len(code) > len(parent.code + separator)):
            raise WbsRuleError("wbs_code_not_under_parent", f"{parent.code}{separator}")


def tree_errors(nodes: Sequence[Node], *, hierarchical: bool = True, separator: str = ".") -> list[dict[str, str]]:
    """Rules 1-3 over a whole stored tree: every violation, one per node it sits on.

    Each entry carries ``node_id``, so a caller can tell the violations a write
    introduced from the ones the tree already had (:func:`new_errors`). Rule 3
    is read as "a closed node has no children that are open"; a subtree closed
    together is valid.
    """
    out: list[dict[str, str]] = []
    for code, ids in duplicate_codes(nodes).items():
        out.extend({"code": "wbs_code_duplicate", "value": code, "node_id": str(i)} for i in ids)
    by_id = {n.id: n for n in nodes}
    for n in nodes:
        if not (n.code or "").strip():
            out.append({"code": "wbs_code_required", "value": "", "node_id": str(n.id)})
            continue
        parent = by_id.get(n.parent_id) if n.parent_id is not None else None
        if parent is None:
            continue
        if parent.closed and not n.closed:
            out.append({"code": "wbs_node_closed", "value": n.code, "node_id": str(n.id)})
        prefix = parent.code + separator
        if hierarchical and not (n.code.startswith(prefix) and len(n.code) > len(prefix)):
            out.append({"code": "wbs_code_not_under_parent", "value": n.code, "node_id": str(n.id)})
    return out


def _identity(error: dict[str, str]) -> tuple[str, str, str]:
    return error["code"], error.get("node_id", ""), _key(error.get("value", ""))


def new_errors(before: Sequence[dict[str, str]], after: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    """The violations a write introduced: in ``after`` and not in ``before``, by (rule, node, value).

    A tree that already breaks a rule stays editable; only a write that adds a
    violation, or moves a broken node onto another broken value, is refused.
    """
    known = {_identity(e) for e in before}
    return [e for e in after if _identity(e) not in known]


def renumber_plan(
    nodes: Sequence[Node], node_id: uuid.UUID, new_code: str, *, separator: str = "."
) -> dict[uuid.UUID, str]:
    """New codes for a node and its subtree (rule 2): the old prefix is replaced on every descendant.

    Raises :class:`WbsRuleError` ``wbs_code_duplicate`` when a resulting code is
    held by a node outside the subtree, so nothing is applied half-way.
    """
    by_id = {n.id: n for n in nodes}
    node = by_id.get(node_id)
    if node is None:
        raise WbsRuleError("wbs_node_not_found")
    old = node.code
    plan = {node_id: new_code}
    for d in descendants(nodes, node_id):
        if d.code.startswith(old + separator):
            plan[d.id] = new_code + d.code[len(old) :]
    outside = {_key(n.code) for n in nodes if n.id not in plan}
    taken = [c for c in plan.values() if _key(c) in outside]
    if taken:
        raise WbsRuleError("wbs_code_duplicate", ", ".join(sorted(taken)))
    new_keys = [_key(c) for c in plan.values()]
    if len(new_keys) != len(set(new_keys)):
        raise WbsRuleError("wbs_code_duplicate")
    return {k: v for k, v in plan.items() if by_id[k].code != v}


def deletable(nodes: Sequence[Node], node_id: uuid.UUID, referenced: set[uuid.UUID]) -> bool:
    """Rule 3: a node can be deleted only when neither it nor any descendant is referenced."""
    ids = {node_id} | {d.id for d in descendants(nodes, node_id)}
    return not (ids & referenced)


__all__ = [
    "NODE_KINDS",
    "Node",
    "WbsRuleError",
    "check_code",
    "new_errors",
    "tree_errors",
    "deletable",
    "descendants",
    "duplicate_codes",
    "renumber_plan",
]
