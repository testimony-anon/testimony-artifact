# RQ2 results for ghost (reduced fault set, added subject)

|Kind|Subject|Faults|O0 detected|O1 detected|O2 detected|Business-only|O2 undetected|O2 unknown|No test|
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
|response|ghost|6|0|1|1|0|2|0|3|
|source|ghost|5|0|0|0|0|3|0|2|

Incomplete pairs stay unknown; non-activated faults and faults without tests remain in the catalogue denominator; O0 is the generic checks plus application 5xx; a response fault detected without any changed response is rewritten to unknown.

## Per-fault results

|Kind|Fault|Module|Completed/planned tests|Changed responses|O0|O1|O2|B vs O1|
|---|---|---|---:|---:|---|---|---|---|
|response|PR-G01|posts|0/0|0|no_eligible_tests|no_eligible_tests|no_eligible_tests|unknown|
|response|PR-G02|posts|0/0|0|no_eligible_tests|no_eligible_tests|no_eligible_tests|unknown|
|response|PR-G03|members|0/0|0|no_eligible_tests|no_eligible_tests|no_eligible_tests|unknown|
|response|PR-G04|posts|438/438|833|completed_not_detected|detected|detected|both|
|response|PR-G05|newsletters|248/248|470|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|response|PR-G06|posts|438/438|833|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|source|B-G01|posts|0/0|—|no_eligible_tests|no_eligible_tests|no_eligible_tests|unknown|
|source|B-G02|members|0/0|—|no_eligible_tests|no_eligible_tests|no_eligible_tests|unknown|
|source|B-G03|settings|3/3|—|completed_not_detected|completed_not_detected|completed_not_detected|no_business_tests|
|source|B-G04|posts|438/438|—|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|source|B-G05|posts|32/32|—|completed_not_detected|completed_not_detected|completed_not_detected|no_business_tests|
