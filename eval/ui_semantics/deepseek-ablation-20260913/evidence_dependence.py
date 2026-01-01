"""Option C (observational, no re-run): which evidence the retained business relations of the final DeepSeek suite cite.

For every retained main-chain test whose candidate payload is available, records: the kind of evidence card the
proposal was anchored on, whether the candidate cites association facts (value flows vf-/dependency edges de-/
binding opportunities bo-,binding-/transition facts), page-change facts (ui-diff), negative request facts;
whether producer and observer requests belong to different UI actions / different actors, and whether they lie
more than MECHANICAL_NEIGHBORHOOD_ORDER_RADIUS apart in recording order (only an association-expanded
neighborhood co-locates them); whether the anchoring card is the center of a business-operation episode.
Labels come from rq1-audit-deepseek/tests-labeled.jsonl.  Output: JSON rows + a Markdown summary.
"""
import json, glob, sys
from collections import Counter, defaultdict
from pathlib import Path
import os
REPO = Path(__file__).resolve().parents[3]
CFG = os.environ.get('DEP_CONFIG', 'full')          # full | temporal | flat (which suite to analyse)
D = REPO / (os.environ.get('DEP_RUNS_ROOT') or 'eval/ui_semantics/deepseek-full-20260912')
RUNS = {'conduit': (os.environ.get('DEP_RUNS_CONDUIT') or 'm11fix-01').split(','),
        'rwa': (os.environ.get('DEP_RUNS_RWA') or 'm11fix-02,rerecord-01,m11fix-01').split(',')}
AUDIT = REPO / (os.environ.get('DEP_AUDIT_DIR') or 'docs/design/cpv-expansion/rq1-audit-deepseek')
RADIUS = 16
labels = {}
for l in open(AUDIT / 'tests-labeled.jsonl'):
    r = json.loads(l); labels[r['test_key']] = r
def ref_kind(ref):
    if ':request:' in ref: return 'request'
    # binding-NNNN = recorded UI-action -> request link (trajectory structure, kept in every configuration);
    # bo-... = binding opportunity (mined association).  Only mined structures count as association facts.
    for prefix, kind in (('vf-', 'association'), ('de-', 'association'), ('bo-', 'association'), ('binding-', 'action_link'),
                         ('transition-fact', 'association'), ('ui-diff', 'page_change'), ('negative-request', 'negative_fact'), ('evidence-card', 'card')):
        if ref.startswith(prefix): return kind
    return 'other'
rows = []
for subj, runs in (('conduit', RUNS['conduit']), ('rwa', RUNS['rwa'])):
    seen = set()
    for run in runs:
        for u in sorted(glob.glob(f'{D}/{subj}/{run}/cases/*/union')):
            case = u.split('/')[-2]
            if case in seen or not (Path(u) / 'M14/final_calibrated_suite.json').exists(): continue
            seen.add(case)
            view = json.load(open(f'{u}/M01_09/proposal_evidence_view.json')); cards = {c['card_id']: c for c in view['evidence_cards']}
            req = {r['request_ref']: r for r in view['api_requests']}
            prov = json.load(open(f'{u}/M10/union/union_provenance.json'))
            episode_primary = {r['primary_card_id'] for r in prov['detail_regions'] if r['region_kind'] == 'business_operation_episode'}
            pay = {c['candidate_id']: c['payload'] for c in json.load(open(f'{u}/M10/union/candidate_set.json'))['candidates']}
            m14 = json.load(open(f'{u}/M14/final_calibrated_suite.json'))
            for t in m14['retained_tests']:
                p = pay.get(t['candidate_id']);
                if not p: continue
                key = f"{subj}/{case}/{t['test_id']}"; lab = labels.get(key, {})
                kinds = Counter(ref_kind(r) for r in p.get('evidence_refs', []))
                prod = (p.get('producer') or {}).get('request_ref'); cons = (p.get('consumer') or {}).get('request_ref')
                rel = None; far = None
                if prod in req and cons in req:
                    a, b = req[prod], req[cons]
                    rel = 'cross_actor' if a['actor_id'] != b['actor_id'] else ('cross_action' if a.get('action_event_id') != b.get('action_event_id') else 'same_action')
                    far = abs(int(a['global_order']) - int(b['global_order'])) > RADIUS
                card = cards.get(p.get('evidence_card_id'), {})
                rows.append({'test_key': key, 'subject': subj, 'case_id': case, 'layer': lab.get('layer'), 'label': lab.get('label'),
                             'protocol': t.get('protocol_kind'), 'card_kind': card.get('card_kind'),
                             'card_is_episode_center': p.get('evidence_card_id') in episode_primary,
                             'cites_association': kinds['association'] > 0, 'cites_page_change': kinds['page_change'] > 0,
                             'cites_negative_fact': kinds['negative_fact'] > 0, 'cited_kinds': dict(kinds),
                             'producer_consumer': rel, 'beyond_temporal_radius': far})
out = REPO / f'eval/ui_semantics/deepseek-ablation-20260913/evidence-dependence-{CFG}.jsonl'
out.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
def pct(a, b): return f"{a}/{b} ({100.0*a/b:.1f}%)" if b else '-'
lines = ['# RQ3: evidence cited by the final test set (observation, not an ablation)' if CFG == 'full' else f'# RQ3: evidence cited by the {CFG} ablation suite (observation)', '',
         'Population: the retained main-chain tests of the final test set (traced back through the `canonical` candidate payload); labels from `rq1-audit-deepseek/tests-labeled.jsonl`.',
         '"cites association" = the candidate\'s `evidence_refs` include a data flow (vf-), a dependency edge (de-), a rebinding opportunity (bo-) or a state transition (transition-fact); the recorded UI-action-to-request links (binding-NNNN) are trace structure and are not counted; "cites page change" = includes a ui-diff record;',
         f'"beyond temporal radius" = producer and observer requests are more than {RADIUS} positions apart in recording order (only association-based expansion puts both into one view).', '',
         '| Subject | Layer | Label | Tests | Cites association | Cites page change | Cites negative fact | Card is the write-episode centre | Across UI actions | Across users | Beyond temporal radius |',
         '|---|---|---|---:|---|---|---|---|---|---|---|']
for subj in ('conduit', 'rwa'):
    for layer in ('business_relation', 'basic_constraint'):
        for label in (('C', 'E') if layer == 'business_relation' else (None,)):
            rs = [r for r in rows if r['subject'] == subj and r['layer'] == layer and (label is None or r['label'] == label)]
            if not rs: continue
            n = len(rs); pc = [r for r in rs if r['producer_consumer']]
            lines.append(f"| {subj} | {layer} | {label or '-'} | {n} | {pct(sum(r['cites_association'] for r in rs), n)} | {pct(sum(r['cites_page_change'] for r in rs), n)} | {pct(sum(r['cites_negative_fact'] for r in rs), n)} | {pct(sum(r['card_is_episode_center'] for r in rs), n)} | {pct(sum(r['producer_consumer']=='cross_action' for r in pc), len(pc))} | {pct(sum(r['producer_consumer']=='cross_actor' for r in pc), len(pc))} | {pct(sum(bool(r['beyond_temporal_radius']) for r in pc), len(pc))} |")
lines += ['', '## By validation plan (business relations, C)', '', '| Subject | Plan | Tests | Cites association | Cites page change | Across UI actions or users | Beyond temporal radius |', '|---|---|---:|---|---|---|---|']
for subj in ('conduit', 'rwa'):
    by = defaultdict(list)
    for r in rows:
        if r['subject'] == subj and r['layer'] == 'business_relation' and r['label'] == 'C': by[r['protocol']].append(r)
    for proto, rs in sorted(by.items()):
        n = len(rs); pc = [r for r in rs if r['producer_consumer']]
        lines.append(f"| {subj} | {proto} | {n} | {pct(sum(r['cites_association'] for r in rs), n)} | {pct(sum(r['cites_page_change'] for r in rs), n)} | {pct(sum(r['producer_consumer'] in ('cross_action','cross_actor') for r in pc), len(pc))} | {pct(sum(bool(r['beyond_temporal_radius']) for r in pc), len(pc))} |")
(REPO / ('docs/design/cpv-expansion/rq3-evidence-dependence-20260913.md' if CFG == 'full' else f'docs/design/cpv-expansion/rq3-evidence-dependence-{CFG}-20260913.md')).write_text('\n'.join(lines) + '\n')
print(json.dumps({'rows': len(rows), 'business_C': sum(1 for r in rows if r['layer']=='business_relation' and r['label']=='C')}))
print('\n'.join(lines[6:16]))
