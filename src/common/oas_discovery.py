"""Shared augmented OAS discovery/readiness helpers."""

DISCOVERY_EXT = "x-carverflow-discovery"


def execution_readiness(operation: dict) -> str:
    """Return operation execution readiness; legacy operations default to ready."""
    discovery = operation.get(DISCOVERY_EXT)
    if not isinstance(discovery, dict):
        return "ready"
    return discovery.get("execution_readiness", "ready")


def is_execution_ready(operation: dict) -> bool:
    return execution_readiness(operation) == "ready"
