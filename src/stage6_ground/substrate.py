"""Execution substrate of the executable main line (decision record 011): sequences + edges → executed step by step against the application under test.

Promotes the existing Stage 6 replay capability (ReplayClient + write-safety wrapper) into a public substrate that later main-line components (the planner etc.) can call.
- **Only `run_sequence` is public**: the entry point that safely executes one sequence on a reset+seed baseline, bound to create-use-clean afterwards.
  Write sequences are **forced** through reset + create-use-clean by it; it cannot be bypassed and leaves no residue (011 item 2 / invariant 4).
- **Low-level primitives** (ReplayClient, reset/seed/cleanup) are **non-public internals** (underscore prefix), reused only by the grounding
  consumer in the same package (the counterexample orchestration of GroundingRunner) — the main line/planner sees only `run_sequence`, cannot reach the bare primitives
  and cannot bypass the safety (011 hardening a/b).
- **Seed count derivation (D62) is a run-level decision owned by the caller** (GroundingRunner._seed_plan): `run_sequence` only
  **consumes** the `seed_count` passed in and does not re-derive it per sequence here (011 hardening c).
- Fresh values are taken from the current run at run time (replay.py:95/:181), values/tokens are never written to disk, and the method side has no golden data — all inherited unchanged from the lower layer.
"""
from __future__ import annotations

from .config import ReplayConfig
from .replay import ReplayClient, ReplayOutcome, build_op_index
from .safety import CleanupFailedError, SafetyShell


class ReplaySubstrate:
    """Replayer + mandatory write-safety wrapper bound together. The only public surface is run_sequence."""

    def __init__(self, augmented_oas: dict, cfg: ReplayConfig, shell: SafetyShell):
        self._shell = shell
        self._client = ReplayClient(cfg, build_op_index(augmented_oas), shell.throttle)
        self._cleanup_log: list[dict] = []

    # ---- public: the only safe entry point ----

    def run_sequence(self, steps: list[str], bindings: list[dict], parameters: list[dict],
                     *, seed_count: int = 0) -> ReplayOutcome:
        """Safely execute one sequence on a reset+seed baseline and create-use-clean afterwards; returns the outcome.

        Consumed values are the fresh values actually produced by earlier responses in this run (underlying ReplayClient). `seed_count` is
        derived at run level by the caller and passed in (not re-derived per sequence here, 011 hardening c). Write sequences are **forced** through reset + create-use-clean here and leave no residue;
        a cleanup failure → restore the baseline, then trip the circuit breaker (D48/S3).
        """
        self._shell.reset()
        token = self._shell.login()
        seed_slugs = self._shell.seed_articles(token, seed_count) if seed_count else []
        outcome = self._client.replay(steps, bindings, parameters)
        self._cleanup(seed_slugs, outcome.created_articles)
        return outcome

    # ---- non-public internal primitives: reused only by the grounding consumer in the same package (counterexample orchestration); unreachable from the main line's public surface ----

    def _cleanup(self, seed_slugs, created) -> None:
        """Verify GET 404 after deletion (D48). Failure → restore the baseline, then trip the circuit breaker (S3): never silently flip the verdict, never continue with dirty state."""
        to_clean = list(seed_slugs) + list(created)
        if not to_clean:
            return
        token = self._shell.login()
        try:
            self._cleanup_log.extend(self._shell.cleanup_articles(token, to_clean))
        except CleanupFailedError as exc:
            self._cleanup_log.append({"error": str(exc)})
            self._shell.reset()              # restore the baseline
            raise                            # circuit breaker = stop (D48/S3): hand over to a human; never continue with dirty state, which would make the verdicts drift
