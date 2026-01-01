"""Generated from a frozen UISemTest M14 suite; do not edit by hand."""

def test_relation_test_6b16da5b7ea3750e7184(uisemtest_runtime):
    'Business summary: Observation actor_a GET /transactions/contacts; basic constraint P21 requires observation $.results (array) to have JSON type array; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0001\nCanonical relation core: 53fac9cff7b078b56184c55c74d15e49ec1a83682d247d9e2fe802a0cb03b72a\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0001
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions/contacts',
      'request_ref': 'r20260902-022623-a3ed:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0001-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'array',
                    'family': 'P21',
                    'target': {'path': '$.results', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0001-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0001-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.results',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-6b16da5b7ea3750e7184',
        candidate_id='v2-candidate-0001',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='1b92949f29614ed4ccf3082d35a37aa81536a74c967f8cb3c0885886c0f775af',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_fb3b86bad3f2366d66cd(uisemtest_runtime):
    'Business summary: Observation actor_a GET /transactions/contacts; basic constraint P11 requires count(observation $.results (array); unit=items) le observation $.pageData.limit (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0002\nCanonical relation core: 1cf181cf3120bdcdb54e74f99eb07cef4b6102edb82a27185f089f73b1bf77b2\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[9].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0002
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions/contacts',
      'request_ref': 'r20260902-022623-a3ed:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0002-business-01',
      'class': 'business',
      'predicate_type': 'P11',
      'predicate': {'family': 'P11',
                    'operator': 'le',
                    'projection': 'count',
                    'right': {'ref': {'path': '$.pageData.limit',
                                      'role': 'observation',
                                      'value_type': 'integer'},
                              'source': 'role'},
                    'target': {'path': '$.results', 'role': 'observation', 'value_type': 'array'},
                    'unit': 'items'}},
     {'assertion_id': 'v2-candidate-0002-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0002-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.results',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-fb3b86bad3f2366d66cd',
        candidate_id='v2-candidate-0002',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='eff065ac521996c7167656d3f962499e36fea0d74cbf9b28b6a28d539cf8a751',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_0d5bcc6d45cdeb1d8b39(uisemtest_runtime):
    'Business summary: Observation actor_a GET /transactions/contacts; basic constraint P15 requires observation $.results (array) (actual_response) to have unique members by strict-tuple identity [$.id]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0003\nCanonical relation core: 2a1b4d82ba1fffd1420d2c1b7dcd60d68bd771e44333fe4beac15626c079feca\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[10].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0003
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions/contacts',
      'request_ref': 'r20260902-022623-a3ed:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0003-business-01',
      'class': 'business',
      'predicate_type': 'P15',
      'predicate': {'collection': {'path': '$.results', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P15',
                    'identity': {'paths': ['$.id'], 'semantics': 'strict-tuple'},
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0003-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0003-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.results',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-0d5bcc6d45cdeb1d8b39',
        candidate_id='v2-candidate-0003',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='2ae1efd0e561af0b3c7ac84eb32a219b2049db92bbc5b9408db85a7fc9001340',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_9661f53bf6ac4934b9f6(uisemtest_runtime):
    'Business summary: Observation actor_a GET /transactions/contacts; basic constraint For every member of observation $.results (array) in actual_response: P21 requires item $.id (string) to have JSON type string; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0004\nCanonical relation core: c9662aaf41d01df223bcc30ca188f033ab742ab20003f489770ab8aebce24e6a\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0004
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions/contacts',
      'request_ref': 'r20260902-022623-a3ed:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0004-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'expected_type': 'string',
                             'family': 'P21',
                             'target': {'path': '$.id', 'role': 'item', 'value_type': 'string'}},
                    'collection': {'path': '$.results', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0004-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0004-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.results',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-9661f53bf6ac4934b9f6',
        candidate_id='v2-candidate-0004',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='b505ba4ca5df583f3316902b546d6b42108bae469d20d7ea5337cfee24a00475',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_8034c593237317e44501(uisemtest_runtime):
    'Business summary: Observation actor_a GET /transactions/contacts; basic constraint P21 requires observation $.pageData.hasNextPages (boolean) to have JSON type boolean; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0005\nCanonical relation core: 61cfd93b4ef12379f25aba944df76f91ec7fa71b9d749f51798ded81d01ddbd1\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[4].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[5].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0005
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions/contacts',
      'request_ref': 'r20260902-022623-a3ed:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0005-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'boolean',
                    'family': 'P21',
                    'target': {'path': '$.pageData.hasNextPages',
                               'role': 'observation',
                               'value_type': 'boolean'}}},
     {'assertion_id': 'v2-candidate-0005-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0005-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'boolean',
                    'response_ref': 'observation',
                    'target_path': '$.pageData.hasNextPages',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-8034c593237317e44501',
        candidate_id='v2-candidate-0005',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='5ffe6af3b505b5950dcf2a0d22d26e0a4234532252d1d71467b80516960ecc7e',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_ed60d0cf86bb8e90c404(uisemtest_runtime):
    'Business summary: Observation actor_a GET /transactions; basic constraint P15 requires observation $.results (array) (actual_response) to have unique members by strict-tuple identity [$.id]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0006\nCanonical relation core: 50484dbb22ce7c0f7bd4490c7d411055e95b1f9921f3bdf8fc796c7ac40c9906\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0006
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions/contacts',
      'request_ref': 'r20260902-022623-a3ed:request:0'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions',
      'request_ref': 'r20260902-022623-a3ed:request:2'}]
    assertions = [{'assertion_id': 'v2-candidate-0006-business-01',
      'class': 'business',
      'predicate_type': 'P15',
      'predicate': {'collection': {'path': '$.results', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P15',
                    'identity': {'paths': ['$.id'], 'semantics': 'strict-tuple'},
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0006-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0006-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.results',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-ed60d0cf86bb8e90c404',
        candidate_id='v2-candidate-0006',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='7b332f54e8726440369d08aa77591a5de35511a998e12b62de210fa03da80f1b',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_c604f5387f39e17b5098(uisemtest_runtime):
    'Business summary: Observation actor_a GET /transactions; basic constraint P11 requires count(observation $.results (array); unit=items) le observation $.pageData.limit (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0007\nCanonical relation core: 6f7170d64324ce1e5defde5eea8a613722b34825f8134181fc987e8637860110\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0007
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions/contacts',
      'request_ref': 'r20260902-022623-a3ed:request:0'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions',
      'request_ref': 'r20260902-022623-a3ed:request:2'}]
    assertions = [{'assertion_id': 'v2-candidate-0007-business-01',
      'class': 'business',
      'predicate_type': 'P11',
      'predicate': {'family': 'P11',
                    'operator': 'le',
                    'projection': 'count',
                    'right': {'ref': {'path': '$.pageData.limit',
                                      'role': 'observation',
                                      'value_type': 'integer'},
                              'source': 'role'},
                    'target': {'path': '$.results', 'role': 'observation', 'value_type': 'array'},
                    'unit': 'items'}},
     {'assertion_id': 'v2-candidate-0007-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0007-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.results',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-c604f5387f39e17b5098',
        candidate_id='v2-candidate-0007',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='e178e3f7b987f835fd76da1c88bc540349402991c5efc96dd2f3b88783453d95',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_6b12df353a330c10f817(uisemtest_runtime):
    'Business summary: Observation actor_a GET /transactions/contacts; basic constraint P01 requires field observation $.pageData (object) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0008\nCanonical relation core: 7edf0520d5f3e0e2bde9dd0b0e9b9f4f69822018c8506af607ebab5cff24bcde\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0008
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions/contacts',
      'request_ref': 'r20260902-022623-a3ed:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0008-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.pageData', 'role': 'observation', 'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0008-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0008-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'object',
                    'response_ref': 'observation',
                    'target_path': '$.pageData',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-6b12df353a330c10f817',
        candidate_id='v2-candidate-0008',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='f65d02121f07d9cd96c49f67537d8c0f40d84ed7585e3950fa09f1fc3c5fa69b',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_a8d9e96e41382f9450da(uisemtest_runtime):
    'Business summary: Observation actor_a GET /transactions/contacts; basic constraint P01 requires field observation $.results (array) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0009\nCanonical relation core: 54e7026f7761ac82990cb3d2748cdc81b7a0db67dde76b181e77536c1d163d67\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0009
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions/contacts',
      'request_ref': 'r20260902-022623-a3ed:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0009-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.results', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0009-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0009-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.results',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-a8d9e96e41382f9450da',
        candidate_id='v2-candidate-0009',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='cc287bfe7e24c8a4886395807ceb88855df19e8e20f7ef4a29b6665f5992843a',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_03b498e3af41d486e8bf(uisemtest_runtime):
    'Business summary: Observation actor_a GET /transactions/contacts; basic constraint P21 requires observation $.pageData.limit (integer) to have JSON type integer; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0010\nCanonical relation core: 8bb242d33b3d0784a2e0f18151bc707e91ec0cae0ec7b139f297bc4f6d7423ae\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0010
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions/contacts',
      'request_ref': 'r20260902-022623-a3ed:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0010-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'integer',
                    'family': 'P21',
                    'target': {'path': '$.pageData.limit',
                               'role': 'observation',
                               'value_type': 'integer'}}},
     {'assertion_id': 'v2-candidate-0010-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0010-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.pageData.limit',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-03b498e3af41d486e8bf',
        candidate_id='v2-candidate-0010',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='18ee41f5f05e30dfcf0f2478cc1ba065def60972238687ed6e7ac3200ac9ecb0',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_0fad6200641b0c41b4b5(uisemtest_runtime):
    'Business summary: Observation actor_a GET /transactions/contacts; basic constraint P21 requires observation $.pageData.page (integer) to have JSON type integer; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0011\nCanonical relation core: 8c82519b5523f685fb94f7fbedf265a3d6dbb6d5240372b0e19a14580955c7d4\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0011
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions/contacts',
      'request_ref': 'r20260902-022623-a3ed:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0011-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'integer',
                    'family': 'P21',
                    'target': {'path': '$.pageData.page',
                               'role': 'observation',
                               'value_type': 'integer'}}},
     {'assertion_id': 'v2-candidate-0011-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0011-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.pageData.page',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-0fad6200641b0c41b4b5',
        candidate_id='v2-candidate-0011',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='5bbfa3dcdd7fc4e5f0d4f81c52f807a66fb4435ca8d063e8c1efc39e2afee866',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_9472b02cc263adbc9f82(uisemtest_runtime):
    'Business summary: Observation actor_a GET /transactions/contacts; basic constraint P21 requires observation $.pageData.totalPages (integer) to have JSON type integer; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0012\nCanonical relation core: 730c8f1cb5f5c242728349db7dd10ca1ca05593fe66fe3811e75b3a0982d9062\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[4].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0012
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions/contacts',
      'request_ref': 'r20260902-022623-a3ed:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0012-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'integer',
                    'family': 'P21',
                    'target': {'path': '$.pageData.totalPages',
                               'role': 'observation',
                               'value_type': 'integer'}}},
     {'assertion_id': 'v2-candidate-0012-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0012-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.pageData.totalPages',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-9472b02cc263adbc9f82',
        candidate_id='v2-candidate-0012',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='5025d2e9813b9f7dca06ab11a47208c9da9a03b0c2d19bc059fcfc577c5c89f1',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_d04ee51f013fd4ebb07e(uisemtest_runtime):
    'Business summary: Observation actor_a GET /transactions/contacts; basic constraint P02 requires observation $.pageData.page (integer) to strictly equal frozen hypothesis 1 (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0013\nCanonical relation core: 6266fe3aa560f851cd334661be84abbe3a99809abc0e7d05d3eba6700584588f\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[7].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0013
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions/contacts',
      'request_ref': 'r20260902-022623-a3ed:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0013-business-01',
      'class': 'business',
      'predicate_type': 'P02',
      'predicate': {'family': 'P02',
                    'left': {'path': '$.pageData.page', 'role': 'observation', 'value_type': 'integer'},
                    'operator': 'eq',
                    'right': {'evidence_refs': ['r20260902-022623-a3ed:request:0'],
                              'rationale': 'Proposed page number equal to one.',
                              'source': 'hypothesis',
                              'value': 1,
                              'value_type': 'integer'}}},
     {'assertion_id': 'v2-candidate-0013-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0013-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.pageData.page',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-d04ee51f013fd4ebb07e',
        candidate_id='v2-candidate-0013',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='8bdf293118e76d62e1f8032066056a5d5cb258a73427fbc9ce7c82a5644d4e41',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_9ea9afacf72a542385c3(uisemtest_runtime):
    'Business summary: Observation actor_a GET /transactions/contacts; basic constraint P03 requires frozen hypothesis 1 (integer) <= observation $.pageData.limit (integer) <= frozen hypothesis 100 (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0014\nCanonical relation core: 30049c7302919974ded3e1f3a3a4452a355d4deded701da35665636bc9ebc1a8\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[8].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0014
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions/contacts',
      'request_ref': 'r20260902-022623-a3ed:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0014-business-01',
      'class': 'business',
      'predicate_type': 'P03',
      'predicate': {'domain': None,
                    'family': 'P03',
                    'lower': {'evidence_refs': ['r20260902-022623-a3ed:request:0'],
                              'rationale': 'Proposed lower bound for page size.',
                              'source': 'hypothesis',
                              'value': 1,
                              'value_type': 'integer'},
                    'lower_inclusive': True,
                    'operator': 'range',
                    'target': {'path': '$.pageData.limit',
                               'role': 'observation',
                               'value_type': 'integer'},
                    'upper': {'evidence_refs': ['r20260902-022623-a3ed:request:0'],
                              'rationale': 'Proposed upper bound for page size.',
                              'source': 'hypothesis',
                              'value': 100,
                              'value_type': 'integer'},
                    'upper_inclusive': True}},
     {'assertion_id': 'v2-candidate-0014-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0014-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.pageData.limit',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-9ea9afacf72a542385c3',
        candidate_id='v2-candidate-0014',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='488c438d95b2ba3a564eaec8789bb2ec9fc36552d20e081bc8dd052492a401b1',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_04157fb41276437f5028(uisemtest_runtime):
    'Business summary: Observation actor_a GET /transactions/contacts; basic constraint For every member of observation $.results (array) in actual_response: P02 requires item $.amount (integer) to be at least frozen hypothesis 0 (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0015\nCanonical relation core: 6e7f895c82593f6b5ab607328737f8b2ed0a04c1aa2541ddfad735b9db1e9f67\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[11].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0015
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions/contacts',
      'request_ref': 'r20260902-022623-a3ed:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0015-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'family': 'P02',
                             'left': {'path': '$.amount', 'role': 'item', 'value_type': 'integer'},
                             'operator': 'ge',
                             'right': {'evidence_refs': ['r20260902-022623-a3ed:request:0'],
                                       'rationale': 'Proposed non-negative transaction amount.',
                                       'source': 'hypothesis',
                                       'value': 0,
                                       'value_type': 'integer'}},
                    'collection': {'path': '$.results', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0015-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0015-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.results',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-04157fb41276437f5028',
        candidate_id='v2-candidate-0015',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='0c43efc449dc37bc57bdf1bbb43e5b2d922806fb6c764f2268404735b0cad5d6',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_4476cac0f5c5c52f553f(uisemtest_runtime):
    'Business summary: Observation actor_a GET /transactions/contacts; basic constraint For every member of observation $.results (array) in actual_response: P15 requires item $.comments (array) (actual_response) to have unique members by strict-tuple identity [$.id]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0016\nCanonical relation core: 469e7bd851a6f66d5a3f7e908207cdae5f8a028098539cfa247ee420d4ec8c35\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[12].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0016
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions/contacts',
      'request_ref': 'r20260902-022623-a3ed:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0016-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'collection': {'path': '$.comments',
                                            'role': 'item',
                                            'value_type': 'array'},
                             'family': 'P15',
                             'identity': {'paths': ['$.id'], 'semantics': 'strict-tuple'},
                             'scope': 'actual_response'},
                    'collection': {'path': '$.results', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0016-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0016-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.results',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-4476cac0f5c5c52f553f',
        candidate_id='v2-candidate-0016',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='f7d7d95c067eb6dbc89470556359382d0f71b5ec1e5abb8e84a8f0550fc641c5',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_890972b0c1733ba54b67(uisemtest_runtime):
    'Business summary: Observation actor_a GET /transactions; basic constraint P02 requires observation $.pageData.page (integer) to be at most observation $.pageData.totalPages (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0017\nCanonical relation core: d0c662308ce1ef0afc646040c2f8c2e03a669f6d0b96cab295025b65d6fe26b7\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0017
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions/contacts',
      'request_ref': 'r20260902-022623-a3ed:request:0'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions',
      'request_ref': 'r20260902-022623-a3ed:request:2'}]
    assertions = [{'assertion_id': 'v2-candidate-0017-business-01',
      'class': 'business',
      'predicate_type': 'P02',
      'predicate': {'family': 'P02',
                    'left': {'path': '$.pageData.page', 'role': 'observation', 'value_type': 'integer'},
                    'operator': 'le',
                    'right': {'ref': {'path': '$.pageData.totalPages',
                                      'role': 'observation',
                                      'value_type': 'integer'},
                              'source': 'role'}}},
     {'assertion_id': 'v2-candidate-0017-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0017-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.pageData.page',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-890972b0c1733ba54b67',
        candidate_id='v2-candidate-0017',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='6d152ad5ec38769580d2551ba653b1052732256f420a6846c57bf8ed3f100052',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_15e81815f84820987249(uisemtest_runtime):
    'Business summary: Observation actor_a GET /transactions; basic constraint For every member of observation $.results (array) in actual_response: P15 requires item $.likes (array) (actual_response) to have unique members by strict-tuple identity [$.uuid]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0018\nCanonical relation core: 06c91f0259fc8a7fc75df61ef6103dacdf2d9625d8ed9904912c5fe1b080ed31\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0018
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions/contacts',
      'request_ref': 'r20260902-022623-a3ed:request:0'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions',
      'request_ref': 'r20260902-022623-a3ed:request:2'}]
    assertions = [{'assertion_id': 'v2-candidate-0018-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'collection': {'path': '$.likes', 'role': 'item', 'value_type': 'array'},
                             'family': 'P15',
                             'identity': {'paths': ['$.uuid'], 'semantics': 'strict-tuple'},
                             'scope': 'actual_response'},
                    'collection': {'path': '$.results', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0018-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0018-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.results',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-15e81815f84820987249',
        candidate_id='v2-candidate-0018',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='1e8f7a8ea1d85736abf72ec4a049ef7439d6ce75e887e0ccb3c1da7a7325ac6c',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_dfb8a0dc2fd9f04afd52(uisemtest_runtime):
    'Business summary: Observation actor_a GET /transactions/contacts; basic constraint P02 requires observation $.pageData.page (integer) to be at most observation $.pageData.totalPages (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0019\nCanonical relation core: a4d6254de93a4468e36a2de166b675d132b2db7e46753e01362480c5e311b57b\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0019
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions/contacts',
      'request_ref': 'r20260902-022623-a3ed:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0019-business-01',
      'class': 'business',
      'predicate_type': 'P02',
      'predicate': {'family': 'P02',
                    'left': {'path': '$.pageData.page', 'role': 'observation', 'value_type': 'integer'},
                    'operator': 'le',
                    'right': {'ref': {'path': '$.pageData.totalPages',
                                      'role': 'observation',
                                      'value_type': 'integer'},
                              'source': 'role'}}},
     {'assertion_id': 'v2-candidate-0019-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0019-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.pageData.page',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-dfb8a0dc2fd9f04afd52',
        candidate_id='v2-candidate-0019',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='0f63604fc870b089d20263630e55f06fcbaba106357c161867e019ea018ba3bc',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_7513e54d45be088d770a(uisemtest_runtime):
    'Business summary: Observation actor_a GET /transactions; basic constraint P01 requires field observation $.results (array) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0020\nCanonical relation core: f5e4efd30ff127e8824afbdd967f03dbf0a0e302d90022b81670124061ce22a1\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0020
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions/contacts',
      'request_ref': 'r20260902-022623-a3ed:request:0'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions',
      'request_ref': 'r20260902-022623-a3ed:request:2'}]
    assertions = [{'assertion_id': 'v2-candidate-0020-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.results', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0020-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0020-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.results',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-7513e54d45be088d770a',
        candidate_id='v2-candidate-0020',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='9976e7137ab2ba461b46e9cd59a3a60b167bebebf987fbc4bde85e95d5e74af1',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_20eb8f88ee7b5384d79b(uisemtest_runtime):
    'Business summary: Observation actor_a GET /transactions; basic constraint P21 requires observation $.results (array) to have JSON type array; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0021\nCanonical relation core: 2ab9e7b7757b571b7cf30d079f0cac331e23e39b1d45a74a37568556b27f02cb\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0021
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions/contacts',
      'request_ref': 'r20260902-022623-a3ed:request:0'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions',
      'request_ref': 'r20260902-022623-a3ed:request:2'}]
    assertions = [{'assertion_id': 'v2-candidate-0021-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'array',
                    'family': 'P21',
                    'target': {'path': '$.results', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0021-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0021-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.results',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-20eb8f88ee7b5384d79b',
        candidate_id='v2-candidate-0021',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='e7f97a3852d98edd40c94ad443b7ecc31b0c73b13cae104278b4e8e6e36efa9a',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_a4e757f5d9cfaadc6e3a(uisemtest_runtime):
    'Business summary: Observation actor_a GET /transactions; basic constraint P01 requires field observation $.pageData.hasNextPages (boolean) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0022\nCanonical relation core: bc9ce8a2d979753fa3efd3e14a365638a3d0a859abe1456a76e30994bad819d8\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0022
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions/contacts',
      'request_ref': 'r20260902-022623-a3ed:request:0'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions',
      'request_ref': 'r20260902-022623-a3ed:request:2'}]
    assertions = [{'assertion_id': 'v2-candidate-0022-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.pageData.hasNextPages',
                               'role': 'observation',
                               'value_type': 'boolean'}}},
     {'assertion_id': 'v2-candidate-0022-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0022-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'boolean',
                    'response_ref': 'observation',
                    'target_path': '$.pageData.hasNextPages',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-a4e757f5d9cfaadc6e3a',
        candidate_id='v2-candidate-0022',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='bb5822936b814676ff98c8d99d2915f79df13dcb4b26939a505a5092b51c781d',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_891e7dc1799f738ca2ee(uisemtest_runtime):
    "Business summary: Observation actor_a GET /transactions; business relation P19 requires observation $.pageData.limit (integer) = count(observation $.results (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0023\nCanonical relation core: be2ba2ffcad8169bb8eb9211dcce469d1e14b133acb824ac0a082267cd783183\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[4].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0023
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions/contacts',
      'request_ref': 'r20260902-022623-a3ed:request:0'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/transactions',
      'request_ref': 'r20260902-022623-a3ed:request:2'}]
    assertions = [{'assertion_id': 'v2-candidate-0023-business-01',
      'class': 'business',
      'predicate_type': 'P19',
      'predicate': {'collection': {'path': '$.results', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P19',
                    'numeric_mode': 'exact',
                    'operator': 'count',
                    'output': {'path': '$.pageData.limit',
                               'role': 'observation',
                               'value_type': 'integer'},
                    'scope': 'actual_response',
                    'units': {'evidence_refs': ['r20260902-022623-a3ed:request:2'],
                              'rationale': 'Proposed unit: the counted members of the transactions '
                                           'array are items, and the same-response page limit scalar '
                                           'is compared in that item unit. Frozen before execution; '
                                           'not prevalidated.',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0023-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0023-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.pageData.limit',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-891e7dc1799f738ca2ee',
        candidate_id='v2-candidate-0023',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='f0d248413f58c2fc477e416457c3790714c7130337cceb0de384c4907eca4cfc',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])
