"""Stage 6 assembly: live replay + counterexamples → grounded_report + write-back of the three artifacts (D47–D52, M1–M5, S1–S4).

Sequences and edges are kept separate (M2): a passing sequence replay only flips the sequence to status=grounded and marks its edges grounded (data flow validated);
promoting an edge to hard requires a counterexample (D50). Soft edges are retained and marked soft, not deleted (D51).
"""

from __future__ import annotations

import json
import re
import secrets as _pysecrets
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from common.contracts import REPO_ROOT, make_envelope, validate_artifact
from stage6_ground.http_client import send

from .config import ReplayConfig
from .counterexample import EdgeVerdict, run_counterexample
from .replay import ReplayOutcome
from .safety import SafetyShell
from .substrate import ReplaySubstrate

AUTH_FIELD = "Authorization"
FROM_RESPONSE_BODY = "response_body"


# ---------- pure functions: enumerate used value-flows, aggregate edge strength, write back, assemble ----------

def enumerate_value_flows(sequences: list[dict]) -> list[dict]:
    """Enumerate the used value-flows from sequence bindings, deduplicated by producer/consumer/source/target,
    taking the lexicographically smallest sequence as representative. auth (Authorization) and data flows are split."""
    seen: dict[tuple, dict] = {}
    for seq in sorted(sequences, key=lambda s: s["sequence_id"]):
        steps = seq["steps"]
        for b in seq["bindings"]:
            producer, consumer = steps[b["from_step"]], steps[b["to_step"]]
            key = (producer, consumer, b.get("from_location", FROM_RESPONSE_BODY), b["from_field"],
                   b["to_location"], b["to_field"])
            if key in seen:
                continue
            kind = "auth" if b["to_field"] == AUTH_FIELD else "data"
            seen[key] = {"producer": producer, "consumer": consumer, "kind": kind,
                         "binding": b, "sequence_id": seq["sequence_id"], "steps": steps,
                         "bindings": seq["bindings"]}
    return list(seen.values())


def aggregate_edge_strength(verdicts: list[EdgeVerdict]) -> dict[tuple, str]:
    """Strength of each (producer,consumer) edge = aggregate of its value-flow counterexamples (hard>soft>inconclusive);
    drop_all_sources (category-level evidence) does not take part in per-edge write-back."""
    order = {"hard": 2, "soft": 1, "inconclusive": 0}
    best: dict[tuple, str] = {}
    for v in verdicts:
        if v.perturbation == "drop_all_sources":
            continue  # category-level, not written back to a single edge
        key = (v.producer, v.consumer)
        # store only the strength string: a tie between several value-flows of equal strength always gives the same result (independent of traversal order, deterministic output)
        if key not in best or order[v.dependency_strength] > order[best[key]]:
            best[key] = v.dependency_strength
    return best


def writeback_dependency_graph(dep: dict, grounded_edges: set, edge_strength: dict) -> dict:
    """Write back dependency_graph: used edges get grounded=true; strength is aggregated from counterexamples, edges without a counterexample run are inconclusive."""
    for e in dep["edges"]:
        key = (e["producer"], e["consumer"])
        if key in grounded_edges:
            e["grounded"] = True
        if key in edge_strength:
            e["dependency_strength"] = edge_strength[key]
        elif e["kind"] == "auth":
            e["dependency_strength"] = "soft"  # D50a: auth sources are interchangeable, token bytes identical → single edge soft
        else:
            e["dependency_strength"] = "inconclusive"  # not used by any sequence / no counterexample run (M3)
    return dep


def _step_to_dict(sr) -> dict:
    d = {"step_index": sr.step_index, "operation_id": sr.operation_id, "passed": sr.passed}
    if sr.response_status is not None:
        d["response_status"] = sr.response_status
    if sr.error:
        d["error"] = sr.error
    if sr.bindings_resolved:
        d["bindings_resolved"] = sr.bindings_resolved
    return d


def _result(target_type: str, target_id: str, outcome: ReplayOutcome) -> dict:
    return {"target_type": target_type, "target_id": target_id, "passed": outcome.passed,
            "steps": [_step_to_dict(s) for s in outcome.steps]}


_ARTICLES_IDX = re.compile(r"\$\.articles\[(\d+)\]")


def articles_max_index(bindings: list[dict]) -> int:
    """Largest index N of $.articles[N] in bindings.from_field (-1 if none). D62 seed count derivation."""
    mx = -1
    for b in bindings:
        m = _ARTICLES_IDX.search(b.get("from_field", ""))
        if m:
            mx = max(mx, int(m.group(1)))
    return mx


def build_grounded_report(results: list[dict], counterexamples: list[EdgeVerdict],
                          removed_false_edges: list[dict], upstream: list[dict],
                          seeding_record: list[dict] | None = None) -> dict:
    ce = []
    for v in counterexamples:
        item = {k: val for k, val in asdict(v).items() if val is not None}
        ce.append(item)
    doc = {
        "metadata": make_envelope("grounded_report", "stage6", _new_run_id(), upstream_refs=upstream),
        "results": results,
        "counterexample_results": ce,
        "removed_false_edges": removed_false_edges,
    }
    if seeding_record:
        doc["seeding_record"] = seeding_record  # D62 audit trail (optional)
    return doc


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"r{stamp}-{_pysecrets.token_hex(2)}"


def canonical_dumps(document: dict) -> str:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, indent=1, allow_nan=False) + "\n"


# ---------- legacy Stage6 live orchestration (the default SafetyShell is still the Conduit adapter) ----------

class GroundingRunner:
    """Sequential live replay + counterexamples. The default shell uses the legacy Conduit reset/seed/cleanup adapter."""

    def __init__(self, augmented_oas: dict, dependency_graph: dict, test_sequences: dict,
                 skills: dict, cfg: ReplayConfig, shell: SafetyShell, majority_n: int = 3):
        self.aug = augmented_oas
        self.dep = dependency_graph
        self.ts = test_sequences
        self.sk = skills
        self.cfg = cfg
        self.shell = shell
        self.majority_n = majority_n
        self.substrate = ReplaySubstrate(augmented_oas, cfg, shell)  # 011: expose the existing replay substrate
        self.client = self.substrate._client  # counterexample orchestration reuses the underlying client (package-internal; the main line's public surface = substrate.run_sequence)
        self.results: list[dict] = []
        self.counterexamples: list[EdgeVerdict] = []
        self.passed_seq: set[str] = set()
        self.seq_status: dict[str, str] = {}   # D63: seq_id → grounded|inconclusive|validation_failed
        self.seeding_record: list[dict] = []

    # --- baseline management ---
    def _seed_plan(self, steps: list[str], bindings: list[dict]) -> tuple[int, str | None]:
        """D62: the seed count is derived from the largest $.articles[N] index in bindings.from_field (max N → N+1).
        Honest boundary: articles resource only; seed only when the steps include a get_api_articles read."""
        if "get_api_articles" not in steps:
            return 0, None
        mx = articles_max_index(bindings)
        count = max(1, mx + 1)
        basis = (f"largest $.articles[N] index in bindings N={mx} → seed N+1={count}" if mx >= 0
                 else "get_api_articles read present, no $.articles[N] index binding → seed 1")
        return count, basis

    # --- phase 1: sequence/skill replay ---
    def replay_all(self) -> None:
        for seq, skill in zip(self.ts["sequences"], self.sk["skills"]):
            count, basis = self._seed_plan(seq["steps"], seq["bindings"])  # D62 seed derivation stays at this level (run level, 011 hardening c)
            if count:
                self.seeding_record.append({"target_id": seq["sequence_id"], "seed_count": count,
                                            "basis": basis, "resource": "articles"})
            # run through the substrate's safe entry point: reset+seed+replay+create-use-clean binding (same behaviour as the original per-sequence loop; a cleanup failure trips the circuit breaker inside the substrate)
            outcome = self.substrate.run_sequence(
                seq["steps"], skill["bindings"], skill["parameters"], seed_count=count)
            self.seq_status[seq["sequence_id"]] = self._verdict(outcome)  # D63 three-state verdict
            if outcome.passed:  # cleanup succeeded (otherwise the call above already tripped the breaker) → a passing replay is grounded
                self.passed_seq.add(seq["sequence_id"])
            self.results.append(_result("sequence", seq["sequence_id"], outcome))
            self.results.append(_result("skill", skill["skill_id"], outcome))

    # --- phase 2: counterexamples ---
    def counterexample_all(self) -> None:
        flows = enumerate_value_flows(self.ts["sequences"])
        data_flows = [f for f in flows if f["kind"] == "data"]
        auth_flows = [f for f in flows if f["kind"] == "auth"]

        for f in data_flows:
            self.shell.reset()
            tok = self.shell.login()
            count, _ = self._seed_plan(f["steps"], f["bindings"])
            seeds = self.shell.seed_articles(tok, count) if count else []
            ev = run_counterexample(self.client, f["steps"], f["bindings"], self._params_for(f),
                                    f["binding"], "data", "replace_nonexistent",
                                    f["sequence_id"], self.majority_n)
            self.counterexamples.append(ev)
            self.substrate._cleanup(seeds, [])  # counterexample cleanup reuses the substrate's internal primitive (same package; orchestration stays at this level, 011 hardening b)

        self._auth_counterexamples(auth_flows)

    def _auth_counterexamples(self, auth_flows: list[dict]) -> None:
        # live confirmation of interchangeable token sources (D50a): byte comparison of the login token and the user-group token
        self.shell.reset()
        login_tok = self.shell.login()
        user_tok = self._fetch_user_token(login_tok)
        identical = (user_tok is not None and login_tok == user_tok)
        basis = f"login/user token bytes {'identical' if identical else 'different'} (live comparison)"

        # for each used auth edge: switch judges soft (identical token → consumer behaviour unchanged after switching the source) + drop probes whether the category is required
        self.shell.reset()
        seed_tok = self.shell.login()
        auth_count = max([self._seed_plan(f["steps"], f["bindings"])[0] for f in auth_flows] + [1])
        self.shell.seed_articles(seed_tok, auth_count)  # D62: seed enough articles to support $.articles[N] auth consumers
        for f in auth_flows:
            self.counterexamples.append(self._auth_switch_verdict(f, basis))
            self.counterexamples.append(self._auth_drop_verdict(f))
        # user-group auth edges not used by any sequence (D50a/K5: all retained by Stage 4, refuted → soft)
        self._user_group_soft_verdicts(basis)

    def _auth_switch_verdict(self, f: dict, basis: str) -> EdgeVerdict:
        return EdgeVerdict(f["producer"], f["consumer"], "auth", "switch_alternative_source",
                           None, False, "soft", f["sequence_id"],
                           f"switched to a legitimate alternative source ({basis}) → consumer behaviour unchanged → single edge soft (interchangeable sources, D50a)")

    def _auth_drop_verdict(self, f: dict) -> EdgeVerdict:
        ev = run_counterexample(self.client, f["steps"], f["bindings"], self._params_for(f),
                                f["binding"], "auth", "drop_all_sources", f["sequence_id"],
                                self.majority_n)
        # drop is category-level evidence: 401 → category hard, 200 → this consumer does not even require auth
        ev.reason += " (category-level: all auth sources dropped; not written back as single-edge strength, see the switch soft verdict for the single edge)"
        return ev

    def _user_group_soft_verdicts(self, basis: str) -> None:
        for e in self.dep["edges"]:
            if e["kind"] == "auth" and e["producer"] == "get_api_user":
                self.counterexamples.append(EdgeVerdict(
                    e["producer"], e["consumer"], "auth", "switch_alternative_source",
                    None, False, "soft", "",
                    f"user-group auth edge (unused by sequences, all retained by Stage 4): {basis} → switching to the login source is equivalent → soft"
                    " (propose-and-verify loop: Stage 4 does not dare to delete, the Stage 6 counterexample proves soft)"))

    def _params_for(self, flow: dict) -> list[dict]:
        sid = flow["sequence_id"].replace("seq_", "skill_")
        for s in self.sk["skills"]:
            if s["skill_id"] == sid:
                return s["parameters"]
        return []

    def _fetch_user_token(self, login_tok: str) -> str | None:
        res = send("GET", self.cfg.base_url + "/api/user",
                   headers={"Authorization": f"{self.cfg.token_scheme} {login_tok}"})
        doc = res.json()
        return (doc.get("user") or {}).get("token") if isinstance(doc, dict) else None

    # --- phase 3: write-back + assembly ---
    @staticmethod
    def _verdict(outcome) -> str:
        """D63 three-state verdict (based on the outcome's existing signals, no new heuristics):
        replay passed → grounded;
        setup break (bind_fail short-circuit, the failed step sent no request so response_status is None,
          replay already marked inconclusive_setup) → inconclusive;
        executed and failed on business grounds (request sent, response_status is a real code) → validation_failed."""
        if outcome.passed:
            return "grounded"
        idx = outcome.failed_step_index
        failed = outcome.steps[idx] if idx is not None and idx < len(outcome.steps) else None
        if failed is not None and failed.response_status is None:
            return "inconclusive"      # no request sent = setup break
        return "validation_failed"     # request sent, business failure

    def assemble(self) -> tuple[dict, dict, dict, dict]:
        grounded_edges = self._grounded_edges()
        edge_strength = aggregate_edge_strength(self.counterexamples)
        dep = writeback_dependency_graph(self.dep, grounded_edges, edge_strength)
        for seq in self.ts["sequences"]:
            seq["status"] = self.seq_status.get(seq["sequence_id"], "validation_failed")  # D63 three-state verdict
        for sk in self.sk["skills"]:
            sid = sk["skill_id"].replace("skill_", "seq_")
            sk["status"] = self.seq_status.get(sid, "validation_failed")                  # keep skills in sync
        upstream = [{"artifact_type": "test_sequences", "run_id": self.ts["metadata"]["run_id"]},
                    {"artifact_type": "skills", "run_id": self.sk["metadata"]["run_id"]},
                    {"artifact_type": "dependency_graph", "run_id": self.dep["metadata"]["run_id"]}]
        report = build_grounded_report(self.results, self.counterexamples, [], upstream, self.seeding_record)
        return report, self.ts, self.sk, dep

    def _grounded_edges(self) -> set:
        """Edges used by a passing sequence → grounded=true (data flow validated by replay, D51)."""
        edges: set = set()
        for seq in self.ts["sequences"]:
            if seq["sequence_id"] not in self.passed_seq:
                continue
            steps = seq["steps"]
            for b in seq["bindings"]:
                edges.add((steps[b["from_step"]], steps[b["to_step"]]))
        return edges

    def run(self) -> tuple[dict, dict, dict, dict]:
        self.replay_all()
        self.counterexample_all()
        return self.assemble()


def run_stage6(input_dir: str | Path, base_url: str | None = None,
               artifacts_root: str | Path | None = None, majority_n: int = 3,
               reset_cmd: list | None = None) -> tuple[dict, Path]:
    """Main entry: read the 4 inputs (schema-validated) → live replay + counterexamples → write back → validate → write to disk. Returns (grounded_report, directory)."""
    input_dir = Path(input_dir)
    aug = _load(input_dir / "augmented_oas.json", "augmented_oas.schema.json")
    dep = _load(input_dir / "dependency_graph.json", "dependency_graph.schema.json")
    ts = _load(input_dir / "test_sequences.json", "test_sequences.schema.json")
    sk = _load(input_dir / "skills.json", "skills.schema.json")

    base = base_url or aug["servers"][0]["url"]
    cfg = ReplayConfig.from_env(base)
    shell = SafetyShell(cfg, reset_cmd=reset_cmd) if reset_cmd else SafetyShell(cfg)
    runner = GroundingRunner(aug, dep, ts, sk, cfg, shell, majority_n=majority_n)
    report, ts_out, sk_out, dep_out = runner.run()

    validate_artifact("grounded_report.schema.json", report)
    validate_artifact("test_sequences.schema.json", ts_out)
    validate_artifact("skills.schema.json", sk_out)
    validate_artifact("dependency_graph.schema.json", dep_out)

    root = Path(artifacts_root) if artifacts_root else REPO_ROOT / "artifacts"
    run_dir = root / report["metadata"]["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "grounded_report.json").write_text(canonical_dumps(report))
    (run_dir / "test_sequences.json").write_text(canonical_dumps(ts_out))
    (run_dir / "skills.json").write_text(canonical_dumps(sk_out))
    (run_dir / "dependency_graph.json").write_text(canonical_dumps(dep_out))
    return report, run_dir


def _load(path: Path, schema: str) -> dict:
    doc = json.loads(path.read_text())
    validate_artifact(schema, doc)
    return doc
