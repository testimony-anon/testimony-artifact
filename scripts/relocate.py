#!/usr/bin/env python3
"""Rewrite the packaging placeholders to the actual locations on this machine.

<ARTIFACT_ROOT>  -> absolute path of this package (its directory)
<SUBJECTS>       -> --subjects <dir> (directory that contains the cypress-realworld-app checkout); default: <ARTIFACT_ROOT>/subjects
<HOME>           -> --home <dir>; default: the current user's home
<PAPER_CODE_WORKTREE> -> --paper-code-worktree <dir>; only rewritten when the option is given. It appears in the
                 launcher scripts of the ablation runs and names the checkout of the pinned code those runs were
                 executed from; pass this package's own directory to run them against the shipped code.
Run it once after extracting the package (and again after moving it). Only text files are touched; the
replacement is exact and reversible (run with --to-placeholders to restore).
"""
import argparse, hashlib, json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
ATTEST = ROOT / "docs/artifact-relocation.json"
TEXT = {".json", ".jsonl", ".md", ".py", ".sh", ".txt", ".log", ".csv", ".toml", ".cfg", ".yaml", ".yml", ".ini", ".patch", ".diff", ".example"}
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--subjects"); ap.add_argument("--home")
    ap.add_argument("--paper-code-worktree"); ap.add_argument("--to-placeholders", action="store_true")
    a = ap.parse_args()
    pairs = [("<ARTIFACT_ROOT>", str(ROOT)), ("<SUBJECTS>", str(Path(a.subjects).resolve()) if a.subjects else str(ROOT / "subjects")), ("<HOME>", a.home or str(Path.home()))]
    if a.paper_code_worktree: pairs.append(("<PAPER_CODE_WORKTREE>", str(Path(a.paper_code_worktree).resolve())))
    if a.to_placeholders: pairs = [(v, k) for k, v in pairs]
    attested = set(json.loads(ATTEST.read_text(encoding="utf-8")).get("sha256_map", {})) if ATTEST.is_file() else set()
    n = 0; skipped = 0
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.is_symlink() or (p.suffix not in TEXT and p.name != "uisemtest"): continue
        try: s = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError): continue
        t = s
        for k, v in pairs: t = t.replace(k, v)
        if t == s: continue
        if attested and hashlib.sha256(s.encode("utf-8")).hexdigest() in attested:
            skipped += 1; continue   # hash-pinned provenance manifest: keep the placeholders (see docs/artifact-relocation.json)
        p.write_text(t, encoding="utf-8"); n += 1
    print(f"rewrote {n} files, kept {skipped} hash-pinned manifests; ARTIFACT_ROOT={ROOT}")
if __name__ == "__main__": main()
