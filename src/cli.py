"""Current deterministic UISemTest recording CLI."""

from __future__ import annotations

import argparse
import json
import sys


def _cmd_record(args: argparse.Namespace) -> int:
    from stage1_record import execute_recording_workflow

    if args.suite is not None:
        if args.artifacts_root is None:
            raise ValueError("suite recording requires an explicit fresh --artifacts-root")
        from common.contracts import REPO_ROOT
        from ui_semantics.current_suite import record_current_suite

        result = record_current_suite(
            args.suite,
            artifacts_root=args.artifacts_root,
            headless=args.headless,
            repo_root=REPO_ROOT,
            recorder=execute_recording_workflow,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["status"] == "completed" else 2
    result = execute_recording_workflow(
        args.workflow,
        artifacts_root=args.artifacts_root,
        headless=args.headless,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "completed" else 2


def configure_record_parser(rec: argparse.ArgumentParser) -> None:
    source = rec.add_mutually_exclusive_group(required=True)
    source.add_argument("--workflow")
    source.add_argument("--suite")
    rec.add_argument("--artifacts-root", default=None)
    rec.add_argument("--headless", action="store_true")


def run_record_command(args: argparse.Namespace) -> int:
    return _cmd_record(args)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="uisemtest-stages")
    sub = parser.add_subparsers(dest="command", required=True)
    record = sub.add_parser("record", help="execute one typed N-actor workflow")
    configure_record_parser(record)
    record.set_defaults(func=_cmd_record)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
