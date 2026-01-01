"""Compatibility and offline-maintenance commands outside the current run path."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable


EVAL_OUTPUT_ROOT = Path("eval/ui_semantics/unified-pipeline-refactor-20260723")
PREPROPOSAL_OUTPUT_ROOT = Path(
    "eval/ui_semantics/preproposal-evidence-mainline-v2-20260723"
)
HARDENED_OUTPUT_ROOT = Path(
    "eval/ui_semantics/preproposal-current-v2-freeze-20260723/rwa"
)


def configure_maintenance_parser(parser: argparse.ArgumentParser) -> None:
    subparsers = parser.add_subparsers(dest="maintenance_command", required=True)

    build = subparsers.add_parser(
        "offline-build",
        help="build contracts from frozen recording bundles",
    )
    build.add_argument("--profile", type=Path, required=True)
    build.add_argument("--recording-root", type=Path, required=True)
    build.add_argument("--output-root", type=Path, required=True)
    build.add_argument("--channels", default="semantic,ui-diff,transfer")
    build.add_argument("--run-id", default="uisemtest-offline-build")
    build.add_argument("--transfer-selection", type=Path)
    build.add_argument("--transfer-population", type=Path)

    equivalence = subparsers.add_parser(
        "frozen-equivalence",
        help="audit a frozen equivalence fixture",
    )
    equivalence.add_argument("--system", choices=("rwa",), required=True)
    equivalence.add_argument("--output-root", type=Path, default=EVAL_OUTPUT_ROOT)

    compatibility = subparsers.add_parser(
        "offline-compatibility",
        help="audit a frozen offline compatibility fixture",
    )
    compatibility.add_argument("--system", choices=("mattermost",), required=True)
    compatibility.add_argument("--output-root", type=Path, default=EVAL_OUTPUT_ROOT)

    audit = subparsers.add_parser(
        "boundary-audit",
        help="scan source and frozen-boundary invariants",
    )
    audit.add_argument("--output-root", type=Path, default=EVAL_OUTPUT_ROOT)

    freeze = subparsers.add_parser(
        "freeze-hardened-input",
        help="freeze a hardened proposer input without a provider call",
    )
    freeze.add_argument("--system", choices=("rwa",), default="rwa")
    freeze.add_argument("--output-root", type=Path, default=HARDENED_OUTPUT_ROOT)
    freeze.add_argument("--frozen-at", default=None)

    verify = subparsers.add_parser(
        "verify",
        help="run offline refactor acceptance replays",
    )
    verify.add_argument("--output-root", type=Path, default=PREPROPOSAL_OUTPUT_ROOT)


def run_maintenance_command(
    args: argparse.Namespace,
    *,
    root: Path,
    offline_builder: Callable[[argparse.Namespace], dict[str, Any]],
) -> dict[str, Any]:
    command = args.maintenance_command
    if command == "offline-build":
        requested = {
            value.strip() for value in args.channels.split(",") if value.strip()
        }
        if (
            not requested <= {"semantic", "ui-diff", "transfer"}
            or "semantic" not in requested
        ):
            raise ValueError(
                "channels must include semantic and may include ui-diff/transfer"
            )
        return offline_builder(args)
    if command == "frozen-equivalence":
        from .eval_replay import rwa_frozen_equivalence

        report = rwa_frozen_equivalence(root)
        _write_json(
            args.output_root.resolve() / "rwa_frozen_equivalence_report.json",
            report,
        )
        return report
    if command == "offline-compatibility":
        from .eval_replay import mattermost_offline_compatibility

        report = mattermost_offline_compatibility(root)
        _write_json(
            args.output_root.resolve()
            / "mattermost_offline_compatibility_report.json",
            report,
        )
        return report
    if command == "boundary-audit":
        from .current_boundary import audit_current_boundary

        report = audit_current_boundary(root)
        _write_json(args.output_root.resolve() / "boundary_audit.json", report)
        return report
    if command == "freeze-hardened-input":
        from .preproposal_replay import write_rwa_hardened_v2_input_freeze

        return write_rwa_hardened_v2_input_freeze(
            root,
            args.output_root.resolve(),
            frozen_at=args.frozen_at,
        )
    if command == "verify":
        from .preproposal_replay import write_rwa_preproposal_v2_reports

        return write_rwa_preproposal_v2_reports(root, args.output_root.resolve())
    raise ValueError(f"unsupported UISemTest maintenance command: {command}")


def _write_json(path: Path, value: Any) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


__all__ = ["configure_maintenance_parser", "run_maintenance_command"]
