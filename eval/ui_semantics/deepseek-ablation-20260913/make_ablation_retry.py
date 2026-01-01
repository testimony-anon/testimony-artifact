"""Build a retry suite (manifest + filtered recording root) for failed cases of an ablation configuration.
Usage: make_ablation_retry.py <cfg> <conduit|rwa> <CASE_ID> [...]
Writes fixtures/recording_workflows/<subject>_modular/retry-ablation-<cfg>-20260913.json and
eval/ui_semantics/deepseek-ablation-20260913/<subject>/recordings-retry-<cfg>/ (copies from recordings-final)."""
import json, shutil, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]
def main(argv):
    cfg, subject, selected = argv[1], argv[2], argv[3:]
    src_suite = REPO / f"fixtures/recording_workflows/{subject}_modular"
    src_rec = REPO / f"eval/ui_semantics/deepseek-ablation-20260913/{subject}/recordings-final"
    rec_dir = REPO / f"eval/ui_semantics/deepseek-ablation-20260913/{subject}/recordings-retry-{cfg}"
    inv = json.loads((src_suite / "inventory.json").read_text())
    cases = [c for c in inv["cases"] if c["case_id"] in selected]
    assert {c["case_id"] for c in cases} == set(selected), "unknown case ids"
    mods = [{**m, "case_ids": [c for c in m["case_ids"] if c in selected]} for m in inv["modules"] if any(c in selected for c in m["case_ids"])]
    manifest = {**inv, "suite_id": inv["suite_id"] + f"-ablation-{cfg}-retry", "modules": mods, "case_count": len(cases), "cases": cases}
    blob = json.dumps(manifest, ensure_ascii=False, indent=2).encode() + b"\n"
    (src_suite / f"retry-ablation-{cfg}-20260913.json").write_bytes(blob)
    if rec_dir.exists(): shutil.rmtree(rec_dir)
    rec_dir.mkdir(parents=True); (rec_dir / "suite_manifest.json").write_bytes(blob)
    res = json.loads((src_rec / "suite_recording_result.json").read_text())
    rows = [r for r in res["cases"] if r["case_id"] in selected]
    res2 = {**res, "suite_id": manifest["suite_id"], "case_count": len(rows), "completed_case_count": sum(r["status"] == "completed" for r in rows),
            "rejected_case_count": sum(r["status"] != "completed" for r in rows), "cases": rows, "distinct_reset_count": len({r["reset_epoch"] for r in rows})}
    (rec_dir / "suite_recording_result.json").write_text(json.dumps(res2, ensure_ascii=False, indent=2) + "\n")
    (rec_dir / "cases").mkdir()
    for c in cases: shutil.copytree(src_rec / "cases" / c["case_id"], rec_dir / "cases" / c["case_id"])
    print(f"{subject}/{cfg}: retry suite with {len(cases)} cases -> {rec_dir}")
if __name__ == "__main__": main(sys.argv)
