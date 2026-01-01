# RQ3: evidence cited by the flat ablation suite (observation)

Population: the retained main-chain tests of the final test set (traced back through the `canonical` candidate payload); labels from `rq1-audit-deepseek/tests-labeled.jsonl`.
"cites association" = the candidate's `evidence_refs` include a data flow (vf-), a dependency edge (de-), a rebinding opportunity (bo-) or a state transition (transition-fact); the recorded UI-action-to-request links (binding-NNNN) are trace structure and are not counted; "cites page change" = includes a ui-diff record;
"beyond temporal radius" = producer and observer requests are more than 16 positions apart in recording order (only association-based expansion puts both into one view).

| Subject | Layer | Label | Tests | Cites association | Cites page change | Cites negative fact | Card is the write-episode centre | Across UI actions | Across users | Beyond temporal radius |
|---|---|---|---:|---|---|---|---|---|---|---|
| conduit | business_relation | C | 203 | 0/203 (0.0%) | 0/203 (0.0%) | 0/203 (0.0%) | 26/203 (12.8%) | 38/56 (67.9%) | 12/56 (21.4%) | 0/56 (0.0%) |
| conduit | basic_constraint | - | 997 | 0/997 (0.0%) | 0/997 (0.0%) | 0/997 (0.0%) | 0/997 (0.0%) | - | - | - |
| rwa | business_relation | C | 156 | 0/156 (0.0%) | 0/156 (0.0%) | 0/156 (0.0%) | 89/156 (57.1%) | 25/117 (21.4%) | 10/117 (8.5%) | 3/117 (2.6%) |
| rwa | basic_constraint | - | 3392 | 0/3392 (0.0%) | 0/3392 (0.0%) | 0/3392 (0.0%) | 0/3392 (0.0%) | - | - | - |

## By validation plan (business relations, C)

| Subject | Plan | Tests | Cites association | Cites page change | Across UI actions or users | Beyond temporal radius |
|---|---|---:|---|---|---|---|
| conduit | V2 | 147 | 0/147 (0.0%) | 0/147 (0.0%) | - | - |
| conduit | V3 | 15 | 0/15 (0.0%) | 0/15 (0.0%) | 15/15 (100.0%) | 0/15 (0.0%) |
| conduit | V4 | 24 | 0/24 (0.0%) | 0/24 (0.0%) | 18/24 (75.0%) | 0/24 (0.0%) |
| conduit | V6 | 5 | 0/5 (0.0%) | 0/5 (0.0%) | 5/5 (100.0%) | 0/5 (0.0%) |
| conduit | V7 | 12 | 0/12 (0.0%) | 0/12 (0.0%) | 12/12 (100.0%) | 0/12 (0.0%) |
| rwa | V1 | 11 | 0/11 (0.0%) | 0/11 (0.0%) | 0/11 (0.0%) | 0/11 (0.0%) |
| rwa | V2 | 39 | 0/39 (0.0%) | 0/39 (0.0%) | - | - |
| rwa | V3 | 4 | 0/4 (0.0%) | 0/4 (0.0%) | 4/4 (100.0%) | 0/4 (0.0%) |
| rwa | V4 | 92 | 0/92 (0.0%) | 0/92 (0.0%) | 21/92 (22.8%) | 0/92 (0.0%) |
| rwa | V7 | 9 | 0/9 (0.0%) | 0/9 (0.0%) | 9/9 (100.0%) | 3/9 (33.3%) |
| rwa | V8 | 1 | 0/1 (0.0%) | 0/1 (0.0%) | 1/1 (100.0%) | 0/1 (0.0%) |
