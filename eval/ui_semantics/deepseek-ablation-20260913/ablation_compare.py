"""RQ3 paired comparison: Full (final DeepSeek suite) vs an ablation configuration, by input case.

Usage: ablation_compare.py <config-name> <ablation-audit-dir> [<ablation-runs-root> <run-name>]
Reads tests-labeled.jsonl / targets.jsonl / groups.jsonl of both audit dirs (labels: model-assisted review + main line),
writes docs/design/cpv-expansion/rq3-<config>-comparison.md and eval/.../rq3-<config>-comparison.json.
Metrics per subject: M10 candidates, constructible, validated, retained (business/basic), correct business relations
(instances and distinct core identities), E, cases with >=1 correct business relation, main-target cases, cross-action /
cross-actor correct relations, per-case paired outcome (improve/degrade/same on correct business instances), tokens.
"""
import json, glob, sys
from collections import Counter, defaultdict
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]
FULL_AUDIT = REPO / 'docs/design/cpv-expansion/rq1-audit-deepseek'
FULL_ROOT = REPO / 'eval/ui_semantics/deepseek-full-20260912'
def lines(p):
    return [json.loads(l) for l in open(p)] if Path(p).exists() else []
def usage(root, subject, runs):
    tot = Counter(); seen = set()
    for run in runs:
        for cd in sorted(glob.glob(f'{root}/{subject}/{run}/cases/*')):
            case = Path(cd).name
            if case.startswith('.') or case in seen or not (Path(cd) / 'union/M14/final_calibrated_suite.json').exists(): continue
            seen.add(case)
            for env in glob.glob(f'{cd}/attempts/*/M10/calls/*/provider_response_envelope.json') + glob.glob(f'{cd}/union/M10/center_completion/**/provider_response_envelope.json', recursive=True):
                u = ((json.load(open(env)) or {}).get('raw_envelope') or {}).get('usage') or {}
                tot['prompt'] += u.get('prompt_tokens', 0) or 0; tot['completion'] += u.get('completion_tokens', 0) or 0
    return tot
def funnel(root, subject, runs):
    f = Counter(); seen = set()
    for run in runs:
        for cd in sorted(glob.glob(f'{root}/{subject}/{run}/cases/*')):
            case = Path(cd).name; u = Path(cd) / 'union'
            if case.startswith('.') or case in seen or not (u / 'M14/final_calibrated_suite.json').exists(): continue
            seen.add(case); f['cases'] += 1
            cs = json.load(open(u / 'M10/union/candidate_set.json')) if (u / 'M10/union/candidate_set.json').exists() else {'candidates': []}
            f['exact'] += len(cs['candidates'])
            el = json.load(open(u / 'M11b/materialization_eligibility.json')) if (u / 'M11b/materialization_eligibility.json').exists() else {}
            f['ineligible'] += el.get('materialization_ineligible_count', 0) or 0
            rr = json.load(open(u / 'M12/run_report.json')) if (u / 'M12/run_report.json').exists() else {}
            for r in rr.get('rows', []): f['m12_' + str((r.get('protocol_result') or {}).get('protocol_verdict'))] += 1
    return f
def per_case(audit):
    tests = lines(Path(audit) / 'tests-labeled.jsonl'); targets = {(t['subject'], t['case_id']): t for t in lines(Path(audit) / 'targets.jsonl')}
    out = defaultdict(lambda: Counter()); cores = defaultdict(set)
    for t in tests:
        k = (t['subject'], t['case_id']); out[k]['retained'] += 1
        if t['layer'] == 'business_relation':
            out[k]['business'] += 1
            if t.get('label') == 'C':
                out[k]['C'] += 1; cores[k].add(t.get('core_identity'))
            elif t.get('label') == 'E': out[k]['E'] += 1
        elif t['layer'] == 'basic_constraint': out[k]['basic'] += 1
    for k in out: out[k]['C_groups'] = len(cores[k] - {None}); out[k]['target'] = 1 if (targets.get(k) or {}).get('has_correct_target') else 0
    return out
def main(argv):
    name, audit = argv[1], Path(argv[2]); runs_root = Path(argv[3]) if len(argv) > 3 else REPO / 'eval/ui_semantics/deepseek-ablation-20260913'; run = (argv[4] if len(argv) > 4 else f'{name}-01').split(',')
    full = per_case(FULL_AUDIT); abl = per_case(audit)
    report = {'config': name, 'subjects': {}}
    md = [f'# RQ3 paired comparison: Full vs {name}', '', 'Same 83 inputs, recordings, model, generation rounds and validation pipeline; labels are model-assisted initial labels plus author adjudication.', '',
          '| Subject | Configuration | M10 candidates | Constructible | M12 validated/refuted/not evaluable/infrastructure failed | Retained (business/structural) | Correct business instances | Correct semantic groups | E | Cases with at least one correct business assertion | Cases with the primary target checked | Tokens (prompt/completion, M) |', '|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|---|']
    for subject in ('conduit', 'rwa'):
        cfgs = {'Full': (FULL_ROOT, ['m11fix-01'] if subject == 'conduit' else ['m11fix-02', 'rerecord-01', 'm11fix-01'], full), name: (runs_root, run, abl)}
        rows = {}
        for cfg, (root, runs, pc) in cfgs.items():
            f = funnel(root, subject, runs); u = usage(root, subject, runs)
            cases = {k: v for k, v in pc.items() if k[0] == subject}
            agg = Counter()
            for v in cases.values(): agg.update(v)
            rows[cfg] = {'funnel': dict(f), 'usage': dict(u), 'agg': dict(agg), 'cases_with_C': sum(1 for v in cases.values() if v['C'] > 0), 'target_cases': sum(v['target'] for v in cases.values())}
            md.append(f"| {subject} | {cfg} | {f['exact']} | {f['exact'] - f['ineligible']} | {f['m12_validated']}/{f['m12_refuted']}/{f['m12_not_evaluable']}/{f['m12_infrastructure_failed']} | {agg['retained']} ({agg['business']}/{agg['basic']}) | {agg['C']} | {agg['C_groups']} | {agg['E']} | {rows[cfg]['cases_with_C']} | {rows[cfg]['target_cases']} | {u['prompt']/1e6:.1f}/{u['completion']/1e6:.1f} |")
        paired = Counter()
        for k in {k for k in list(full) + list(abl) if k[0] == subject}:
            a, b = full.get(k, Counter())['C'], abl.get(k, Counter())['C']
            paired['improve' if b > a else 'degrade' if b < a else 'same'] += 1
        rows['paired_on_correct_business_instances'] = dict(paired)
        report['subjects'][subject] = rows
        md.append(f"| {subject} | Paired by input (correct business instances, {name} vs Full) | | | | | | | | | | improved {paired['improve']} / degraded {paired['degrade']} / same {paired['same']} |")
    out_md = REPO / f'docs/design/cpv-expansion/rq3-{name}-comparison.md'; out_md.write_text('\n'.join(md) + '\n')
    (REPO / f'eval/ui_semantics/deepseek-ablation-20260913/rq3-{name}-comparison.json').write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print('\n'.join(md[4:]))
if __name__ == '__main__':
    main(sys.argv)
