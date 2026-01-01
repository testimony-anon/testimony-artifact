"""Seed the input root of the DeepSeek RQ2 suite evaluation (run once).

inputs/  (UISEMTEST_RQ2_LEGACY)
  source-versions.jsonl   registered source versions: Conduit rows from the
                          frozen Astra suite root (fast-reset deploy roots,
                          images uisemtest-rq2-*:20260907), RWA rows from the
                          legacy root (patched checkouts B-R01..B-R24 + pristine)
  subjects/rwa/pristine   symlink to the never-run pristine RWA checkout
  subjects/rwa/normal/node_modules  symlink to the shared RWA node_modules
  seed.json               provenance of every seeded item
suite/   (UISEMTEST_RQ2_ROOT) is created by `uisemtest-rq2 prepare` and the
runs; nothing under the two source roots is modified.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
LEGACY = REPO / "eval/ui_semantics/rq2-20260907"
SUITE = REPO / "eval/ui_semantics/rq2-suite-20260908"
INPUTS = HERE / "inputs"


def lines(path: Path):
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()]


def main() -> int:
    if INPUTS.exists():
        raise SystemExit(f"{INPUTS} already exists; refusing to reseed")
    (INPUTS / "subjects/rwa/normal").mkdir(parents=True)
    conduit = [v for v in lines(SUITE / "source-versions.jsonl") if v["subject"] == "conduit"]
    rwa = [v for v in lines(LEGACY / "source-versions.jsonl") if v["subject"] == "rwa"]
    rows = []
    for v in conduit:
        row = dict(v)
        row["seed_origin"] = str(SUITE / "source-versions.jsonl")
        row["reset_variant"] = "TRUNCATE RESTART IDENTITY (fast reset)" if v["fault_id"] != "B-C01" else "DROP/CREATE in origin; replaced by fast reset after prepare (see seed.json)"
        rows.append(row)
    for v in rwa:
        row = dict(v)
        row["seed_origin"] = str(LEGACY / "source-versions.jsonl")
        rows.append(row)
    with (INPUTS / "source-versions.jsonl").open("w") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    pristine = (LEGACY / "subjects/rwa/pristine").resolve(strict=True)
    node_modules = (LEGACY / "subjects/rwa/normal/node_modules").resolve(strict=True)
    os.symlink(pristine, INPUTS / "subjects/rwa/pristine", target_is_directory=True)
    os.symlink(node_modules, INPUTS / "subjects/rwa/normal/node_modules", target_is_directory=True)
    (INPUTS / "seed.json").write_text(json.dumps({
        "seeded_at": dt.datetime.now(dt.UTC).isoformat(),
        "conduit_versions": [v["fault_id"] for v in conduit],
        "rwa_versions": [v["fault_id"] for v in rwa],
        "pristine_rwa": str(pristine), "rwa_node_modules": str(node_modules),
        "fault_registry": str(LEGACY / "faults.jsonl"),
        "conduit_images": "uisemtest-rq2-<fault>:20260907 (built 2026-09-07 from the registered patches; reused unchanged)",
        "b_c01_reset_note": "the frozen Astra evaluation kept DROP/CREATE for B-C01 because its results predated the reset switch; this evaluation uses the fast reset for every Conduit version, copied from the suite root's B-C02 deploy after prepare",
        "environment": {"UISEMTEST_RQ2_LEGACY": str(INPUTS), "UISEMTEST_RQ2_ROOT": str(HERE / "suite"),
                        "UISEMTEST_RQ2_RWA_SOURCE": "run", "UISEMTEST_RQ2_COMPOSE_PREFIX": "uisemtest-rq2-dsfinal2"},
    }, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"inputs": str(INPUTS), "versions": len(rows), "conduit": len(conduit), "rwa": len(rwa)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
