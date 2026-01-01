# RQ3 paired comparison: Full vs temporal

Same 83 inputs, recordings, model, generation rounds and validation pipeline; labels are model-assisted initial labels plus author adjudication.

| Subject | Configuration | M10 candidates | Constructible | M12 validated/refuted/not evaluable/infrastructure failed | Retained (business/structural) | Correct business instances | Correct semantic groups | E | Cases with at least one correct business assertion | Cases with the primary target checked | Tokens (prompt/completion, M) |
|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| conduit | Full | 698 | 674 | 548/12/15/99 | 548 (323/225) | 322 | 182 | 1 | 31 | 18 | 21.3/11.1 |
| conduit | temporal | 979 | 930 | 774/10/25/121 | 774 (238/536) | 238 | 95 | 0 | 28 | 11 | 18.4/9.4 |
| conduit | Paired by input (correct business instances, temporal vs Full) | | | | | | | | | | improved 4 / degraded 23 / same 4 |
| rwa | Full | 1982 | 1966 | 1612/45/129/180 | 1612 (724/888) | 720 | 433 | 4 | 34 | 30 | 70.1/39.1 |
| rwa | temporal | 3328 | 3305 | 2622/118/97/468 | 2622 (406/2216) | 405 | 274 | 1 | 33 | 22 | 42.4/21.0 |
| rwa | Paired by input (correct business instances, temporal vs Full) | | | | | | | | | | improved 9 / degraded 26 / same 5 |
