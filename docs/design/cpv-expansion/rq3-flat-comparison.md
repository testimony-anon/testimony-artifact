# RQ3 paired comparison: Full vs flat

Same 83 inputs, recordings, model, generation rounds and validation pipeline; labels are model-assisted initial labels plus author adjudication.

| Subject | Configuration | M10 candidates | Constructible | M12 validated/refuted/not evaluable/infrastructure failed | Retained (business/structural) | Correct business instances | Correct semantic groups | E | Cases with at least one correct business assertion | Cases with the primary target checked | Tokens (prompt/completion, M) |
|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| conduit | Full | 698 | 674 | 548/12/15/99 | 548 (323/225) | 322 | 182 | 1 | 31 | 18 | 21.3/11.1 |
| conduit | flat | 1471 | 1398 | 1200/28/49/121 | 1200 (203/997) | 203 | 87 | 0 | 27 | 0 | 30.4/13.4 |
| conduit | Paired by input (correct business instances, flat vs Full) | | | | | | | | | | improved 4 / degraded 24 / same 3 |
| rwa | Full | 1982 | 1966 | 1612/45/129/180 | 1612 (724/888) | 720 | 433 | 4 | 34 | 30 | 70.1/39.1 |
| rwa | flat | 4611 | 4597 | 3548/166/74/809 | 3548 (156/3392) | 156 | 139 | 0 | 30 | 2 | 58.7/26.0 |
| rwa | Paired by input (correct business instances, flat vs Full) | | | | | | | | | | improved 0 / degraded 31 / same 9 |
