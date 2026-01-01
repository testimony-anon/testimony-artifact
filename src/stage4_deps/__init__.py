"""Stage 4 — dependency inference (dependency graph; decision records 005 + 005A; V1 fully deterministic).

Pure-function assembly: consumes augmented_oas + session_bundle, looks up the real literal values behind each observation
reference for exact value-flow matching, produces dependency_graph and writes it back into x-carverflow-dependencies of
augmented_oas. Never replays any request (grounded is always false); the E9 zero-egress check applies to this package.
"""

from .assemble import (
    build_dependency_graph,
    canonical_dumps,
    edge_set,
    run_stage4,
    writeback_augmented,
)
from .lowcard import is_low_card
from .valueflow import converge_edges, extract_candidates, template_inference_edges

__all__ = [
    "build_dependency_graph",
    "canonical_dumps",
    "converge_edges",
    "edge_set",
    "extract_candidates",
    "is_low_card",
    "run_stage4",
    "template_inference_edges",
    "writeback_augmented",
]
