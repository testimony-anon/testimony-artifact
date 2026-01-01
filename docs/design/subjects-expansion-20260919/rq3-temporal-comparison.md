# RQ3 paired comparison on the added subjects: Full vs temporal

Same recordings, model, generation rounds and validation pipeline; Paperless-ngx compares the 32 inputs of the reduced ablation suite (L1-DOCLIST-01/02/04 excluded: their Full M10 never completed). Labels are model-assisted initial labels (Full: plus the author-adjudicated items).

| Subject | Configuration | M10 candidates | Constructible | M12 validated/refuted/not evaluable/infrastructure failed | Retained (business/structural) | Correct business instances | Correct semantic groups | E | Cases with at least one correct business assertion | Tokens (prompt/completion, M) |
|---|---|---:|---:|---|---|---:|---:|---:|---:|---|
| umami | Full | 265 | 144 | 133/2/8/1 | 133 (110/23) | 110 | 95 | 0 | 13 | 11.0/5.8 |
| umami | temporal | 273 | 133 | 119/3/6/5 | 119 (92/27) | 90 | 75 | 2 | 13 | 9.2/4.8 |
| umami | Paired by input (correct business instances, temporal vs Full) | | | | | | | | | improved 5 / degraded 7 / same 2 |
| paperless | Full | 956 | 902 | 738/33/46/85 | 738 (444/294) | 444 | 255 | 0 | 22 | 29.3/10.3 |
| paperless | temporal | 842 | 747 | 600/17/11/119 | 600 (328/272) | 327 | 212 | 1 | 24 | 12.4/4.5 |
| paperless | Paired by input (correct business instances, temporal vs Full) | | | | | | | | | improved 5 / degraded 15 / same 4 |
| ghost | Full | 1025 | 754 | 748/2/0/4 | 748 (598/150) | 596 | 99 | 2 | 21 | 36.2/16.5 |
| ghost | temporal | 908 | 565 | 558/3/0/4 | 558 (372/186) | 371 | 84 | 1 | 24 | 21.3/9.1 |
| ghost | Paired by input (correct business instances, temporal vs Full) | | | | | | | | | improved 8 / degraded 14 / same 6 |
