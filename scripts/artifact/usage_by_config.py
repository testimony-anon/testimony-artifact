#!/usr/bin/env python3
"""Token usage per configuration (Appendix F), summed over the model calls of the runs that form each suite."""
import glob, json
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
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
                tot['cache_hit'] += u.get('prompt_cache_hit_tokens', 0) or 0
                tot['reasoning'] += ((u.get('completion_tokens_details') or {}).get('reasoning_tokens', 0) or 0); tot['calls'] += 1
    return tot
CFGS = {'full': (ROOT / 'eval/ui_semantics/deepseek-full-20260912', {'conduit': ['m11fix-01'], 'rwa': ['m11fix-02', 'rerecord-01', 'm11fix-01']}),
        'temporal': (ROOT / 'eval/ui_semantics/deepseek-ablation-20260913', {'conduit': ['temporal-01'], 'rwa': ['temporal-retry-02', 'temporal-01']}),
        'flat': (ROOT / 'eval/ui_semantics/deepseek-ablation-20260913', {'conduit': ['flat-01'], 'rwa': ['flat-fix-01', 'flat-retry-01', 'flat-01']})}
for cfg, (root, runs) in CFGS.items():
    for subj, rs in runs.items():
        t = usage(root, subj, rs)
        print(cfg, subj, {k: (round(v / 1e6, 2) if k != 'calls' else v) for k, v in t.items()})
