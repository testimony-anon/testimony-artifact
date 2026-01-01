`suite/fault-roots/<subject>/<version>/` and `suite/runtime/` are not part of this package: the fault roots are
throw-away directories that mimic the package root (symlinked `src`, `deploy`, `contracts`, `fixtures`, `.venv`)
and differ from it in exactly one file, a copy of the subject's runtime adapter whose `docker_single.volumes`
block carries one extra read-only bind mount that lays the patched source file over its path inside the image.
The frozen suite runtime expands `${UISEMTEST_REPO_ROOT}` from the environment, so pointing that variable at a
fault root makes the supervise and reset subprocesses start the faulted container; the image digest, the reset
scripts and the recorded inputs are identical to the normal version. `suite/runtime/` holds the per-run scratch
state of the subject adapters. `scripts/experiments/rq2_subjects/rq2_subjects.py prepare` rebuilds both from
`inputs/faults-<subject>.jsonl` and `patches/`.
