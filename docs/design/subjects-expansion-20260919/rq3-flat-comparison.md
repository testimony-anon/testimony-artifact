# RQ3 paired comparison on the added subjects: Full vs flat

Same recordings, model, generation rounds and validation pipeline; Paperless-ngx compares the 32 inputs of the reduced ablation suite (L1-DOCLIST-01/02/04 excluded: their Full M10 never completed). Labels are model-assisted initial labels (Full: plus the author-adjudicated items).

| Subject | Configuration | M10 candidates | Constructible | M12 validated/refuted/not evaluable/infrastructure failed | Retained (business/structural) | Correct business instances | Correct semantic groups | E | Cases with at least one correct business assertion | Tokens (prompt/completion, M) |
|---|---|---:|---:|---|---|---:|---:|---:|---:|---|
| umami | Full | 265 | 144 | 133/2/8/1 | 133 (110/23) | 110 | 95 | 0 | 13 | 11.0/5.8 |
| umami | flat | 1411 | 539 | 508/6/22/3 | 508 (219/289) | 218 | 178 | 0 | 13 | 30.1/14.8 |
| umami | Paired by input (correct business instances, flat vs Full) | | | | | | | | | improved 9 / degraded 1 / same 4 |
| paperless | Full | 956 | 902 | 738/33/46/85 | 738 (444/294) | 444 | 255 | 0 | 22 | 29.3/10.3 |
| paperless | flat | 2156 | 1985 | 1720/78/20/167 | 1720 (508/1212) | 507 | 239 | 1 | 24 | 63.7/23.0 |
| paperless | Paired by input (correct business instances, flat vs Full) | | | | | | | | | improved 13 / degraded 7 / same 4 |
| ghost | Full | 1025 | 754 | 748/2/0/4 | 748 (598/150) | 596 | 99 | 2 | 21 | 36.2/16.5 |
| ghost | flat | 2082 | 1340 | 1315/17/0/8 | 1315 (843/472) | 833 | 128 | 10 | 24 | 51.7/24.0 |
| ghost | Paired by input (correct business instances, flat vs Full) | | | | | | | | | improved 19 / degraded 4 / same 5 |
