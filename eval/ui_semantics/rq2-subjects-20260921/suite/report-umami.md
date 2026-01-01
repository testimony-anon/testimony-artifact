# RQ2 results for umami (reduced fault set, added subject)

|Kind|Subject|Faults|O0 detected|O1 detected|O2 detected|Business-only|O2 undetected|O2 unknown|No test|
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
|response|umami|4|0|0|2|2|1|0|1|
|source|umami|0|0|0|0|0|0|0|0|

Incomplete pairs stay unknown; non-activated faults and faults without tests remain in the catalogue denominator; O0 is the generic checks plus application 5xx; a response fault detected without any changed response is rewritten to unknown.

## Per-fault results

|Kind|Fault|Module|Completed/planned tests|Changed responses|O0|O1|O2|B vs O1|
|---|---|---|---:|---:|---|---|---|---|
|response|PR-U01|website|8/8|24|completed_not_detected|completed_not_detected|detected|business-only|
|response|PR-U02|website|11/11|33|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|response|PR-U03|share|0/0|0|no_eligible_tests|no_eligible_tests|no_eligible_tests|unknown|
|response|PR-U04|user|9/9|27|completed_not_detected|completed_not_detected|detected|business-only|
