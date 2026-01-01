"""Per-operation dependency closure + topological sort (006 D41 + 006A rulings).

data edges define the total order (producer before consumer); self-loops impose no constraint, and the only 2-cycle
is broken by dropping the lexicographically larger back edge (M1); when a consumed field has several producers, the
lexicographically smallest operationId is chosen (S4/D46).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

FROM_RESPONSE_BODY = "response_body"


@dataclass(frozen=True)
class SelectedBinding:
    producer: str
    from_location: str
    from_field: str
    consumer: str
    to_location: str
    to_field: str
    observation_refs: tuple


def _ordering_edges(dep_graph: dict) -> list[dict]:
    """Drop self-loops from data edges and break 2-cycle back edges (delete the lexicographically larger directed edge)."""
    data = [e for e in dep_graph["edges"] if e["kind"] == "data" and e["producer"] != e["consumer"]]
    pairs = {(e["producer"], e["consumer"]) for e in data}
    drop = set()
    for (a, b) in pairs:
        if (b, a) in pairs:
            drop.add(max((a, b), (b, a)))  # the lexicographically larger one is the back edge
    return [e for e in data if (e["producer"], e["consumer"]) not in drop]


def _field_producers(ordering_edges: list[dict]) -> dict:
    """(consumer, to_location, to_field) -> [(producer, from_location, from_field, obs_refs)]."""
    fp: dict = defaultdict(list)
    for e in ordering_edges:
        for ev in e["evidence"]:
            d = ev["detail"]
            fp[(e["consumer"], d["to_location"], d["to_field"])].append(
                (e["producer"], d.get("from_location", FROM_RESPONSE_BODY), d["from_field"], tuple(
                    (r["producer_ref"]["run_id"], r["producer_ref"]["entry_index"],
                     r["consumer_ref"]["run_id"], r["consumer_ref"]["entry_index"])
                    for r in d["observation_refs"])))
    return fp


def closure(target_op: str, dep_graph: dict) -> tuple[set[str], list[SelectedBinding]]:
    """Minimal dependency closure of target + the selected data bindings (with several producers, take the lexicographically smallest)."""
    fp = _field_producers(_ordering_edges(dep_graph))
    chain = {target_op}
    bindings: list[SelectedBinding] = []
    seen_field: set[tuple] = set()
    worklist = [target_op]
    while worklist:
        op = worklist.pop()
        for (consumer, tl, tf), cands in fp.items():
            if consumer != op:
                continue
            if (consumer, tl, tf) in seen_field:
                continue
            seen_field.add((consumer, tl, tf))
            producer = min(c[0] for c in cands)  # pick the lexicographically smallest producer
            # After choosing the producer, the from_location/from_field/refs dimensions also take the deterministic minimum.
            # When a response body exposes both a top-level id and a nested id, prefer the shallower JSONPath; this avoids
            # getting stuck on a nested duplicate field when the runtime returns a slimmed envelope, while keeping the D46 total-order tiebreak.
            from_location, from_field, refs = min(
                ((c[1], c[2], c[3]) for c in cands if c[0] == producer),
                key=_producer_source_rank,
            )
            bindings.append(SelectedBinding(
                producer, from_location, from_field, consumer, tl, tf, refs))
            if producer not in chain:
                chain.add(producer)
                worklist.append(producer)
    return chain, bindings


def _producer_source_rank(item: tuple[str, str, tuple]) -> tuple:
    from_location, from_field, refs = item
    return (from_location, _field_depth(from_field), from_field, refs)


def _field_depth(from_field: str) -> int:
    if not from_field:
        return 0
    if from_field.startswith("$."):
        body_path = from_field[2:]
        if not body_path:
            return 0
        return body_path.count(".") + body_path.count("[") + 1
    if from_field.startswith("xml:"):
        return len([part for part in from_field[4:].split("/") if part])
    return 1


def topo_order(chain: set[str], bindings: list[SelectedBinding]) -> list[str]:
    """Topological sort within the chain (Kahn's algorithm + lexicographic operationId tiebreak, D46)."""
    edges = {(b.producer, b.consumer) for b in bindings
             if b.producer in chain and b.consumer in chain and b.producer != b.consumer}
    indeg = {op: 0 for op in chain}
    adj: dict = defaultdict(list)
    for (p, c) in edges:
        adj[p].append(c)
        indeg[c] += 1
    ready = sorted(op for op in chain if indeg[op] == 0)
    order = []
    while ready:
        op = ready.pop(0)
        order.append(op)
        for nxt in sorted(adj[op]):
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                ready.append(nxt)
        ready.sort()
    return order
