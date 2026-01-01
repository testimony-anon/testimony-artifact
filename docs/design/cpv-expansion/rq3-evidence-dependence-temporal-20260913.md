# RQ3: evidence cited by the temporal ablation suite (observation)

Population: the retained main-chain tests of the final test set (traced back through the `canonical` candidate payload); labels from `rq1-audit-deepseek/tests-labeled.jsonl`.
"cites association" = the candidate's `evidence_refs` include a data flow (vf-), a dependency edge (de-), a rebinding opportunity (bo-) or a state transition (transition-fact); the recorded UI-action-to-request links (binding-NNNN) are trace structure and are not counted; "cites page change" = includes a ui-diff record;
"beyond temporal radius" = producer and observer requests are more than 16 positions apart in recording order (only association-based expansion puts both into one view).

| Subject | Layer | Label | Tests | Cites association | Cites page change | Cites negative fact | Card is the write-episode centre | Across UI actions | Across users | Beyond temporal radius |
|---|---|---|---:|---|---|---|---|---|---|---|
| conduit | business_relation | C | 238 | 0/238 (0.0%) | 29/238 (12.2%) | 6/238 (2.5%) | 50/238 (21.0%) | 97/124 (78.2%) | 18/124 (14.5%) | 0/124 (0.0%) |
| conduit | basic_constraint | - | 536 | 0/536 (0.0%) | 3/536 (0.6%) | 0/536 (0.0%) | 19/536 (3.5%) | - | - | - |
| rwa | business_relation | C | 405 | 0/405 (0.0%) | 79/405 (19.5%) | 0/405 (0.0%) | 252/405 (62.2%) | 78/357 (21.8%) | 16/357 (4.5%) | 8/357 (2.2%) |
| rwa | business_relation | E | 1 | 0/1 (0.0%) | 0/1 (0.0%) | 0/1 (0.0%) | 0/1 (0.0%) | 1/1 (100.0%) | 0/1 (0.0%) | 0/1 (0.0%) |
| rwa | basic_constraint | - | 2216 | 0/2216 (0.0%) | 5/2216 (0.2%) | 0/2216 (0.0%) | 45/2216 (2.0%) | - | - | - |

## By validation plan (business relations, C)

| Subject | Plan | Tests | Cites association | Cites page change | Across UI actions or users | Beyond temporal radius |
|---|---|---:|---|---|---|---|
| conduit | V1 | 1 | 0/1 (0.0%) | 1/1 (100.0%) | 1/1 (100.0%) | 0/1 (0.0%) |
| conduit | V2 | 114 | 0/114 (0.0%) | 0/114 (0.0%) | - | - |
| conduit | V3 | 73 | 0/73 (0.0%) | 1/73 (1.4%) | 73/73 (100.0%) | 0/73 (0.0%) |
| conduit | V4 | 26 | 0/26 (0.0%) | 12/26 (46.2%) | 17/26 (65.4%) | 0/26 (0.0%) |
| conduit | V6 | 6 | 0/6 (0.0%) | 6/6 (100.0%) | 6/6 (100.0%) | 0/6 (0.0%) |
| conduit | V7 | 18 | 0/18 (0.0%) | 9/18 (50.0%) | 18/18 (100.0%) | 0/18 (0.0%) |
| rwa | V1 | 12 | 0/12 (0.0%) | 7/12 (58.3%) | 1/12 (8.3%) | 1/12 (8.3%) |
| rwa | V2 | 48 | 0/48 (0.0%) | 0/48 (0.0%) | - | - |
| rwa | V3 | 18 | 0/18 (0.0%) | 0/18 (0.0%) | 18/18 (100.0%) | 0/18 (0.0%) |
| rwa | V4 | 310 | 0/310 (0.0%) | 69/310 (22.3%) | 59/310 (19.0%) | 2/310 (0.6%) |
| rwa | V7 | 17 | 0/17 (0.0%) | 3/17 (17.6%) | 16/17 (94.1%) | 5/17 (29.4%) |
