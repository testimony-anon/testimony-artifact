"""Stage 3 — augmentation and gating (final OAS gate; decision record 004 D31–D33; V1 is fully deterministic).

This stage is a pure-function gate (no outbound requests): it consumes initial_oas + probe_results → augmented_oas.
The E9 zero-outbound check is applied to this package (the opposite of the stage2_5_probe probing layer).
"""

from .assemble import (
    build_augmented_oas,
    canonical_dumps,
    operation_set,
    run_stage3,
)
from .gate import admit, is_success, probe_untrusted
from .mediator import mediate_downstream_execution
from .runtime_probe_admission import (
    build_runtime_probe_admission_report,
    build_runtime_probe_admission_report_from_paths,
    write_runtime_admitted_augmented_oas,
    write_runtime_probe_admission_report,
)

__all__ = [
    "admit",
    "build_augmented_oas",
    "canonical_dumps",
    "is_success",
    "mediate_downstream_execution",
    "operation_set",
    "probe_untrusted",
    "run_stage3",
    "build_runtime_probe_admission_report",
    "build_runtime_probe_admission_report_from_paths",
    "write_runtime_admitted_augmented_oas",
    "write_runtime_probe_admission_report",
]
