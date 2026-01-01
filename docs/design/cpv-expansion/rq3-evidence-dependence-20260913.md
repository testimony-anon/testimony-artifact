# RQ3: evidence cited by the final test set (observation, not an ablation)

Population: the retained main-chain tests of the final test set (traced back through the `canonical` candidate payload); labels from `rq1-audit-deepseek/tests-labeled.jsonl`.
"cites association" = the candidate's `evidence_refs` include a data flow (vf-), a dependency edge (de-), a rebinding opportunity (bo-) or a state transition (transition-fact); the recorded UI-action-to-request links (binding-NNNN) are trace structure and are not counted; "cites page change" = includes a ui-diff record;
"beyond temporal radius" = producer and observer requests are more than 16 positions apart in recording order (only association-based expansion puts both into one view).

| Subject | Layer | Label | Tests | Cites association | Cites page change | Cites negative fact | Card is the write-episode centre | Across UI actions | Across users | Beyond temporal radius |
|---|---|---|---:|---|---|---|---|---|---|---|
| conduit | business_relation | C | 322 | 142/322 (44.1%) | 27/322 (8.4%) | 6/322 (1.9%) | 107/322 (33.2%) | 128/220 (58.2%) | 21/220 (9.5%) | 1/220 (0.5%) |
| conduit | business_relation | E | 1 | 1/1 (100.0%) | 0/1 (0.0%) | 0/1 (0.0%) | 0/1 (0.0%) | 1/1 (100.0%) | 0/1 (0.0%) | 0/1 (0.0%) |
| conduit | basic_constraint | - | 225 | 18/225 (8.0%) | 5/225 (2.2%) | 0/225 (0.0%) | 17/225 (7.6%) | - | - | - |
| rwa | business_relation | C | 720 | 379/720 (52.6%) | 70/720 (9.7%) | 0/720 (0.0%) | 207/720 (28.8%) | 264/680 (38.8%) | 11/680 (1.6%) | 19/680 (2.8%) |
| rwa | business_relation | E | 4 | 2/4 (50.0%) | 0/4 (0.0%) | 0/4 (0.0%) | 0/4 (0.0%) | 4/4 (100.0%) | 0/4 (0.0%) | 0/4 (0.0%) |
| rwa | basic_constraint | - | 888 | 41/888 (4.6%) | 1/888 (0.1%) | 0/888 (0.0%) | 36/888 (4.1%) | - | - | - |

## By validation plan (business relations, C)

| Subject | Plan | Tests | Cites association | Cites page change | Across UI actions or users | Beyond temporal radius |
|---|---|---:|---|---|---|---|
| conduit | V2 | 102 | 5/102 (4.9%) | 0/102 (0.0%) | - | - |
| conduit | V3 | 76 | 26/76 (34.2%) | 1/76 (1.3%) | 76/76 (100.0%) | 0/76 (0.0%) |
| conduit | V4 | 117 | 100/117 (85.5%) | 12/117 (10.3%) | 46/117 (39.3%) | 1/117 (0.9%) |
| conduit | V6 | 6 | 0/6 (0.0%) | 6/6 (100.0%) | 6/6 (100.0%) | 0/6 (0.0%) |
| conduit | V7 | 21 | 11/21 (52.4%) | 8/21 (38.1%) | 21/21 (100.0%) | 0/21 (0.0%) |
| rwa | V1 | 11 | 3/11 (27.3%) | 7/11 (63.6%) | 3/11 (27.3%) | 0/11 (0.0%) |
| rwa | V2 | 40 | 14/40 (35.0%) | 0/40 (0.0%) | - | - |
| rwa | V3 | 99 | 51/99 (51.5%) | 0/99 (0.0%) | 99/99 (100.0%) | 0/99 (0.0%) |
| rwa | V4 | 559 | 303/559 (54.2%) | 61/559 (10.9%) | 162/559 (29.0%) | 17/559 (3.0%) |
| rwa | V7 | 11 | 8/11 (72.7%) | 2/11 (18.2%) | 11/11 (100.0%) | 2/11 (18.2%) |
