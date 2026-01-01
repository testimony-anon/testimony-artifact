# RQ2 suite-level results

Response faults, source faults and flow compositions are counted separately; the legacy single-position response faults are not in the tables below.

|Kind|Subject|Faults|O0 detected|O1 detected|O2 detected|Business-only|O2 undetected|O2 unknown|No test|
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
|response|conduit|16|0|2|8|6|6|1|1|
|response|rwa|19|0|4|12|8|5|1|1|
|source|conduit|18|1|2|11|9|7|0|0|
|source|rwa|24|0|3|14|10|9|1|0|

Per-fault details and conditional denominators are in summary.json. Incomplete pairs stay unknown; non-activated faults and faults without tests remain in the catalogue denominator.
O0 is the generic checks plus application 5xx; schema_type is the local type check. This is the revised experiment after the earlier diagnosis, not an independent validation set.
RWA and Conduit source faults were both executed anew under this root.
The 9 machine alarms of the RWA source faults keep their original records: the 8 business alarms are supported by representative evidence; the single structural alarm of B-R14 is of uncertain applicability to a legitimately empty list and is not counted as a trustworthy structural detection.

## Per-fault results

|Kind|Subject|Fault|Completed/planned tests|Changed responses|O0|O1|O2|B vs O1|
|---|---|---|---:|---:|---|---|---|---|
|response|conduit|PR-C01|211/211|325|completed_not_detected|completed_not_detected|detected|business-only|
|response|conduit|PR-C02|301/301|492|completed_not_detected|completed_not_detected|detected|business-only|
|response|conduit|PR-C03|504/504|838|completed_not_detected|detected|detected|both|
|response|conduit|PR-C04|20/20|20|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|response|conduit|PR-C05|14/14|14|completed_not_detected|completed_not_detected|detected|business-only|
|response|conduit|PR-C06|43/43|82|completed_not_detected|completed_not_detected|detected|business-only|
|response|conduit|PR-C07|19/19|42|completed_not_detected|completed_not_detected|detected|business-only|
|response|conduit|PR-C08|42/42|35|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|response|conduit|PR-C09|42/42|35|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|response|conduit|PR-C10|17/17|0|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|response|conduit|PR-C11|30/30|0|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|response|conduit|PR-C12-author|84/84|14|unknown|unknown|unknown|unknown|
|response|conduit|PR-C12-favorited|30/30|37|completed_not_detected|detected|detected|both|
|response|conduit|PR-C13|0/0|0|no_eligible_tests|no_eligible_tests|no_eligible_tests|unknown|
|response|conduit|PR-C14-feed|264/264|29|completed_not_detected|completed_not_detected|detected|business-only|
|response|conduit|PR-C14-bio|10/10|0|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|response|rwa|PR-R01|450/450|501|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|response|rwa|PR-R02|662/662|1426|completed_not_detected|completed_not_detected|detected|business-only|
|response|rwa|PR-R03|662/662|298|completed_not_detected|completed_not_detected|detected|business-only|
|response|rwa|PR-R04|10/10|12|completed_not_detected|completed_not_detected|detected|business-only|
|response|rwa|PR-R05|19/19|26|completed_not_detected|completed_not_detected|detected|business-only|
|response|rwa|PR-R06|689/689|229|completed_not_detected|completed_not_detected|unknown|unknown|
|response|rwa|PR-R07|1238/1238|5742|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|response|rwa|PR-R08|1238/1238|5742|completed_not_detected|completed_not_detected|detected|business-only|
|response|rwa|PR-R09-sender|653/653|266|completed_not_detected|completed_not_detected|detected|business-only|
|response|rwa|PR-R09-receiver|653/653|50|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|response|rwa|PR-R10|1238/1238|3146|unknown|detected|detected|both|
|response|rwa|PR-R11-participant|589/589|294|completed_not_detected|detected|detected|both|
|response|rwa|PR-R11-date|135/135|192|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|response|rwa|PR-R11-amount|137/137|0|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|response|rwa|PR-R12|0/0|0|no_eligible_tests|no_eligible_tests|no_eligible_tests|unknown|
|response|rwa|PR-R13-likes|160/160|406|completed_not_detected|completed_not_detected|detected|business-only|
|response|rwa|PR-R13-comments|231/231|781|completed_not_detected|detected|detected|both|
|response|rwa|PR-R14|378/378|688|completed_not_detected|detected|detected|baseline-only|
|response|rwa|PR-R15|58/58|167|completed_not_detected|completed_not_detected|detected|business-only|
|source|conduit|B-C01|366/366|—|completed_not_detected|completed_not_detected|detected|business-only|
|source|conduit|B-C02|366/366|—|completed_not_detected|detected|detected|both|
|source|conduit|B-C03|23/23|—|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|source|conduit|B-C04|23/23|—|completed_not_detected|completed_not_detected|detected|business-only|
|source|conduit|B-C05|49/49|—|completed_not_detected|completed_not_detected|detected|business-only|
|source|conduit|B-C06|19/19|—|completed_not_detected|completed_not_detected|detected|business-only|
|source|conduit|B-C07|43/43|—|completed_not_detected|completed_not_detected|detected|business-only|
|source|conduit|B-C08|26/26|—|completed_not_detected|completed_not_detected|detected|business-only|
|source|conduit|B-C09|21/21|—|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|source|conduit|B-C10|9/9|—|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|source|conduit|B-C11|327/327|—|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|source|conduit|B-C12|327/327|—|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|source|conduit|B-C13|327/327|—|completed_not_detected|completed_not_detected|detected|business-only|
|source|conduit|B-C14|264/264|—|completed_not_detected|completed_not_detected|detected|business-only|
|source|conduit|B-C15|327/327|—|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|source|conduit|B-C16|10/10|—|detected|detected|detected|both|
|source|conduit|H-C01|13/13|—|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|source|conduit|H-C03|366/366|—|completed_not_detected|completed_not_detected|detected|business-only|
|source|rwa|B-R01|662/662|—|completed_not_detected|completed_not_detected|detected|business-only|
|source|rwa|B-R02|662/662|—|completed_not_detected|completed_not_detected|detected|business-only|
|source|rwa|B-R03|662/662|—|completed_not_detected|completed_not_detected|detected|business-only|
|source|rwa|B-R04|954/954|—|completed_not_detected|completed_not_detected|detected|business-only|
|source|rwa|B-R05|689/689|—|completed_not_detected|completed_not_detected|unknown|unknown|
|source|rwa|B-R06|932/932|—|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|source|rwa|B-R07|932/932|—|completed_not_detected|completed_not_detected|detected|business-only|
|source|rwa|B-R08|932/932|—|completed_not_detected|completed_not_detected|detected|business-only|
|source|rwa|B-R09|932/932|—|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|source|rwa|B-R10|932/932|—|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|source|rwa|B-R11|932/932|—|unknown|unknown|detected|unknown|
|source|rwa|B-R12|932/932|—|completed_not_detected|detected|detected|both|
|source|rwa|B-R13|898/898|—|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|source|rwa|B-R14|760/760|—|completed_not_detected|detected|detected|both|
|source|rwa|B-R15|898/898|—|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|source|rwa|B-R16|898/898|—|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|source|rwa|B-R17|898/898|—|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|source|rwa|B-R18|1238/1238|—|completed_not_detected|completed_not_detected|detected|business-only|
|source|rwa|B-R19|231/231|—|completed_not_detected|completed_not_detected|detected|business-only|
|source|rwa|B-R20|932/932|—|completed_not_detected|detected|detected|baseline-only|
|source|rwa|B-R21|160/160|—|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|source|rwa|B-R22|231/231|—|completed_not_detected|completed_not_detected|completed_not_detected|neither|
|source|rwa|B-R23|699/699|—|completed_not_detected|completed_not_detected|detected|business-only|
|source|rwa|B-R24|60/60|—|completed_not_detected|completed_not_detected|detected|business-only|

## Activation and conditional results

PR-R14 reports trigger opportunities and actual activations per branch (payment/request/like/comment); no single branch represents the whole.

|Trigger|Qualifying tests with evidence in the normal plan|Actually changed responses|Status|
|---|---:|---:|---|
|payment|202|141|activated|
|request|176|547|activated|
|like|59|30|activated|
|comment|81|0|not_activated|

The conditional denominator includes only tests with an actual activation whose original checks are jointly evaluable, reduced independently per fault; the full detection numerator is not reused.

|Subject|Response faults with conditional records|Conditional O0 detected|Conditional O1 detected|Conditional O2 detected|
|---|---:|---:|---:|---:|
|conduit|12|0|2|8|
|rwa|17|0|4|12|

## Flow compositions

17 planned (10 reusing original flows and 7 targeting reproduced defects); the composed inputs are new schedules, not byte-for-byte frozen replays, and every added check is listed separately as a manual exploration.

|Composition|Status|Reuses generated assertion|Manual-check alarm|Targets lead|Anchor|
|---|---|---|---|---|---|
|C-C01|completed|True|False|-|relation-test-0c61d3011a|
|C-C02|completed|True|False|-|relation-test-1e65bc0293|
|C-C03|completed|True|False|-|relation-test-c2ff277cfd|
|C-C04|completed|True|False|-|relation-test-009a7ab15d|
|C-C05|completed|True|False|-|relation-test-0d9dcb4b97|
|C-R01|completed|True|False|-|relation-test-db111e8dd2|
|C-R02|completed|False|False|-|relation-test-08b0d61bc6|
|C-R03|completed|True|False|-|relation-test-db111e8dd2|
|C-R04|completed|True|False|-|relation-test-db111e8dd2|
|C-R05|completed|True|False|-|relation-test-0ffa6e0f7e|
|C-R06|completed|True|True|L1|relation-test-02edd982d4|
|C-R07|completed|True|True|L2|relation-test-0ffa6e0f7e|
|C-R08|completed|True|True|L3|relation-test-016c2a90b4|
|C-R09|independent_control_alarm_requires_diagnosis|True|True|L4|relation-test-0ffa6e0f7e|
|C-R10|completed|True|True|L8|relation-test-ccdbaa652d|
|C-C06|completed|True|True|L6|relation-test-0e15923347|
|C-C07|completed|True|False|L7|relation-test-014814836e|

A manual-check alarm is not a confirmed application defect: broken preconditions and composer wiring must be excluded, and the defect reproduced independently and located in the source.

The independent control of C-R02 only verifies that the payment is readable and does not isolate the third-party interaction; the third, pre-existing receiving user has no recorded session, so receiver-side notification clearing is not covered. This item is a partially covering manual exploration and does not count towards generated-assertion capability; an alarm would still require an isolated reproduction of the interaction.
