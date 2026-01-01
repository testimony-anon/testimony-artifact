# RQ2 results for paperless (reduced fault set, added subject)

|Kind|Subject|Faults|O0 detected|O1 detected|O2 detected|Business-only|O2 undetected|O2 unknown|No test|
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
|response|paperless|3|0|0|2|2|0|0|1|
|source|paperless|3|0|0|2|2|1|0|0|

Incomplete pairs stay unknown; non-activated faults and faults without tests remain in the catalogue denominator; O0 is the generic checks plus application 5xx; a response fault detected without any changed response is rewritten to unknown.

## Per-fault results

|Kind|Fault|Module|Completed/planned tests|Changed responses|O0|O1|O2|B vs O1|
|---|---|---|---:|---:|---|---|---|---|
|response|PR-P01|documents|27/27|39|completed_not_detected|completed_not_detected|detected|business-only|
|response|PR-P02|tags|17/17|30|completed_not_detected|completed_not_detected|detected|business-only|
|response|PR-P03|users|0/0|0|no_eligible_tests|no_eligible_tests|no_eligible_tests|unknown|
|source|B-P01|documents|27/27|—|completed_not_detected|completed_not_detected|detected|business-only|
|source|B-P02|notes|8/8|—|completed_not_detected|completed_not_detected|detected|business-only|
|source|B-P03|bulk_edit|3/3|—|completed_not_detected|completed_not_detected|completed_not_detected|neither|
