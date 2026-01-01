"""Generated from a frozen UISemTest M14 suite; do not edit by hand."""

def test_relation_test_6b5feb39f7480de779ae(uisemtest_runtime):
    'Business summary: Observation actor_a GET /notifications; basic constraint P01 requires field observation $.results (array) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0001\nCanonical relation core: c5ee3f2888c17ec095da06f347acf7fb52ee82ade70b280843a2d1db952f796f\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[4].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0001
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/bankaccounts/new',
      'request_ref': 'r20260902-021627-0c54:request:0'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/notifications',
      'request_ref': 'r20260902-021627-0c54:request:138'}]
    assertions = [{'assertion_id': 'v2-candidate-0001-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
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
        test_id='relation-test-6b5feb39f7480de779ae',
        candidate_id='v2-candidate-0001',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='6386ae2069f1e721eb6453477ec08edd224c4849b7efa549d2f04dfe8b7df04c',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_e5e3de1729c9418bd713(uisemtest_runtime):
    'Business summary: Observation actor_a GET /notifications; basic constraint P21 requires observation $.results (array) to have JSON type array; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0002\nCanonical relation core: 5a5c6a8742f79c26bf644ca95fbfbdccb010c5e602f8515f3bf0022f39b72559\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0002
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/bankaccounts/new',
      'request_ref': 'r20260902-021627-0c54:request:0'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/notifications',
      'request_ref': 'r20260902-021627-0c54:request:138'}]
    assertions = [{'assertion_id': 'v2-candidate-0002-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'array',
                    'family': 'P21',
                    'target': {'path': '$.results', 'role': 'observation', 'value_type': 'array'}}},
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
        test_id='relation-test-e5e3de1729c9418bd713',
        candidate_id='v2-candidate-0002',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='6f16c07d37f39527f029dcae739ffcb93692aeb239fca70d43d9bc4ce8d758e5',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_58128296b8ae3aa8aa24(uisemtest_runtime):
    'Business summary: Observation actor_a GET /notifications; basic constraint P15 requires observation $.results (array) (actual_response) to have unique members by strict-tuple identity [$.id]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0003\nCanonical relation core: 2cd93bc696624f213a40d5c1888f4e6ce833cf6e558eb44f7dc4d49030da8ee1\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0003
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/bankaccounts/new',
      'request_ref': 'r20260902-021627-0c54:request:0'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/notifications',
      'request_ref': 'r20260902-021627-0c54:request:138'}]
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
        test_id='relation-test-58128296b8ae3aa8aa24',
        candidate_id='v2-candidate-0003',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='6054c2b780015b6dc2fcceb8ecf47e0d695e2857b5b3cdc10fdf9e523a6d462d',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_409293311ffc4f12af7e(uisemtest_runtime):
    'Business summary: Observation actor_a GET /notifications; basic constraint P15 requires observation $.results (array) (actual_response) to have unique members by strict-tuple identity [$.uuid]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0004\nCanonical relation core: a0efddec0748e5d21bf258d857261f88722cc3a4411b30df444df824edd19547\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0004
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/bankaccounts/new',
      'request_ref': 'r20260902-021627-0c54:request:0'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/notifications',
      'request_ref': 'r20260902-021627-0c54:request:138'}]
    assertions = [{'assertion_id': 'v2-candidate-0004-business-01',
      'class': 'business',
      'predicate_type': 'P15',
      'predicate': {'collection': {'path': '$.results', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P15',
                    'identity': {'paths': ['$.uuid'], 'semantics': 'strict-tuple'},
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
        test_id='relation-test-409293311ffc4f12af7e',
        candidate_id='v2-candidate-0004',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='8e09a4b3212e5b9c51d00a956dbf2b707496790e5b3baa89664c81992e4d8e23',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_aefbd77e33bae3da4be6(uisemtest_runtime):
    'Business summary: Observation actor_a POST /graphql; basic constraint P01 requires field observation $.data.listBankAccount (array) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0005\nCanonical relation core: d3c7ada35b403de8dc0d086a95e2cc1ab064974f6176b6be7b78d9665dad0c02\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[4].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[4].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[5].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0005
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/bankaccounts/new',
      'request_ref': 'r20260902-021627-0c54:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/notifications',
      'request_ref': 'r20260902-021627-0c54:request:138'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021627-0c54:request:139'}]
    assertions = [{'assertion_id': 'v2-candidate-0005-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.data.listBankAccount',
                               'role': 'observation',
                               'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0005-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0005-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.data.listBankAccount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-aefbd77e33bae3da4be6',
        candidate_id='v2-candidate-0005',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='837618ae8aaeb7959db131ab518cd07c875f651a9cf1490064ef0a999dfd0a0c',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_202322704d8f48dd0945(uisemtest_runtime):
    'Business summary: Observation actor_a POST /graphql; basic constraint P21 requires observation $.data.listBankAccount (array) to have JSON type array; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0006\nCanonical relation core: eb5d9f8c39cc0f385308bf3cb16a61f9f3c098c2acb3d80ae73384609c97ceb9\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[5].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[5].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0006
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/bankaccounts/new',
      'request_ref': 'r20260902-021627-0c54:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/notifications',
      'request_ref': 'r20260902-021627-0c54:request:138'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021627-0c54:request:139'}]
    assertions = [{'assertion_id': 'v2-candidate-0006-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'array',
                    'family': 'P21',
                    'target': {'path': '$.data.listBankAccount',
                               'role': 'observation',
                               'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0006-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0006-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.data.listBankAccount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-202322704d8f48dd0945',
        candidate_id='v2-candidate-0006',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='648a993809744745beadd73d466f68f29960a1d5c1b5a9713b680df13874f618',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_e406d492a1c9bd86eb49(uisemtest_runtime):
    'Business summary: Observation actor_a POST /graphql; basic constraint P15 requires observation $.data.listBankAccount (array) (actual_response) to have unique members by strict-tuple identity [$.id]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0007\nCanonical relation core: 18daa76ce812c63f2be988874b5825d4970a3389fbb61742a8d7dac60ce04ad3\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[6].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[6].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0007
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/bankaccounts/new',
      'request_ref': 'r20260902-021627-0c54:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/notifications',
      'request_ref': 'r20260902-021627-0c54:request:138'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021627-0c54:request:139'}]
    assertions = [{'assertion_id': 'v2-candidate-0007-business-01',
      'class': 'business',
      'predicate_type': 'P15',
      'predicate': {'collection': {'path': '$.data.listBankAccount',
                                   'role': 'observation',
                                   'value_type': 'array'},
                    'family': 'P15',
                    'identity': {'paths': ['$.id'], 'semantics': 'strict-tuple'},
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0007-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0007-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.data.listBankAccount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-e406d492a1c9bd86eb49',
        candidate_id='v2-candidate-0007',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='1ff4783f96692a6027e99e9570c7941a903853f9add361c136ca09e92c793a05',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_f8e5413fa9d58c07895b(uisemtest_runtime):
    'Business summary: Observation actor_a POST /graphql; basic constraint P15 requires observation $.data.listBankAccount (array) (actual_response) to have unique members by strict-tuple identity [$.uuid]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0008\nCanonical relation core: 7594b60e9cd093e21e7a6102a732063ca90717b0b28b49d3ef5c1a4e3dadbe1b\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[7].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0008
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/bankaccounts/new',
      'request_ref': 'r20260902-021627-0c54:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/notifications',
      'request_ref': 'r20260902-021627-0c54:request:138'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021627-0c54:request:139'}]
    assertions = [{'assertion_id': 'v2-candidate-0008-business-01',
      'class': 'business',
      'predicate_type': 'P15',
      'predicate': {'collection': {'path': '$.data.listBankAccount',
                                   'role': 'observation',
                                   'value_type': 'array'},
                    'family': 'P15',
                    'identity': {'paths': ['$.uuid'], 'semantics': 'strict-tuple'},
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0008-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0008-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.data.listBankAccount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-f8e5413fa9d58c07895b',
        candidate_id='v2-candidate-0008',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='28028377e3b5058ddb94ae8ad3ba42ff5fa620686d3d7446aa80ff3bf6e8addd',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_8ef262365585e7af82b3(uisemtest_runtime):
    'Business summary: Observation actor_a GET /notifications; basic constraint For every member of observation $.results (array) in actual_response: P21 requires item $.isRead (boolean) to have JSON type boolean; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0009\nCanonical relation core: 35ce288c373133bbdb3a3513f9b1295bfd8eb348506b928811c0254f513c15df\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[8].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0009
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/bankaccounts/new',
      'request_ref': 'r20260902-021627-0c54:request:0'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/notifications',
      'request_ref': 'r20260902-021627-0c54:request:138'}]
    assertions = [{'assertion_id': 'v2-candidate-0009-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'expected_type': 'boolean',
                             'family': 'P21',
                             'target': {'path': '$.isRead', 'role': 'item', 'value_type': 'boolean'}},
                    'collection': {'path': '$.results', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
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
        test_id='relation-test-8ef262365585e7af82b3',
        candidate_id='v2-candidate-0009',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='b17855f9b21131ddc364bc29d177fe019d699e291005bd50d3ee94efaf7d5052',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_ac111ae104fdd173049d(uisemtest_runtime):
    'Business summary: Observation actor_a POST /graphql; basic constraint For every member of observation $.data.listBankAccount (array) in actual_response: P21 requires item $.isDeleted (boolean) to have JSON type boolean; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0010\nCanonical relation core: 104de15223967f2fc268791e275d0381540e9e5c7e079e008cdbafb2156cdc20\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[9].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0010
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/bankaccounts/new',
      'request_ref': 'r20260902-021627-0c54:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/notifications',
      'request_ref': 'r20260902-021627-0c54:request:138'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021627-0c54:request:139'}]
    assertions = [{'assertion_id': 'v2-candidate-0010-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'expected_type': 'boolean',
                             'family': 'P21',
                             'target': {'path': '$.isDeleted',
                                        'role': 'item',
                                        'value_type': 'boolean'}},
                    'collection': {'path': '$.data.listBankAccount',
                                   'role': 'observation',
                                   'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0010-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0010-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.data.listBankAccount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-ac111ae104fdd173049d',
        candidate_id='v2-candidate-0010',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='f12b4bc4fe128e5ec2ba42179112b0daa083e5576a3eb35a3342ffb0ae459635',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_889818f635b1743ef9a9(uisemtest_runtime):
    'Business summary: Observation actor_a GET /notifications; basic constraint For every member of observation $.results (array) in actual_response: P21 requires item $.id (string) to have JSON type string; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0011\nCanonical relation core: 0d5518bae3213f8b939c7fde6ea0bd13607800b19759fd5fb0022cc8c65dbd77\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0011
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/bankaccounts/new',
      'request_ref': 'r20260902-021627-0c54:request:0'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/notifications',
      'request_ref': 'r20260902-021627-0c54:request:138'}]
    assertions = [{'assertion_id': 'v2-candidate-0011-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'expected_type': 'string',
                             'family': 'P21',
                             'target': {'path': '$.id', 'role': 'item', 'value_type': 'string'}},
                    'collection': {'path': '$.results', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0011-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0011-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.results',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-889818f635b1743ef9a9',
        candidate_id='v2-candidate-0011',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='c3f1004ba99bcc635ff82963699550e80e2cd087aaa9c5188fc2f8c5f772e3dd',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_56be2e8c64e24ac7c423(uisemtest_runtime):
    'Business summary: Observation actor_a POST /graphql; basic constraint For every member of observation $.data.listBankAccount (array) in actual_response: P21 requires item $.id (string) to have JSON type string; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0012\nCanonical relation core: b7e7363b07257d3475abf8c22a2158f4e0c1c7ecf4e5fb8af284c02e8dca478c\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[7].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0012
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/bankaccounts/new',
      'request_ref': 'r20260902-021627-0c54:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/notifications',
      'request_ref': 'r20260902-021627-0c54:request:138'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021627-0c54:request:139'}]
    assertions = [{'assertion_id': 'v2-candidate-0012-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'expected_type': 'string',
                             'family': 'P21',
                             'target': {'path': '$.id', 'role': 'item', 'value_type': 'string'}},
                    'collection': {'path': '$.data.listBankAccount',
                                   'role': 'observation',
                                   'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0012-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0012-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.data.listBankAccount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-56be2e8c64e24ac7c423',
        candidate_id='v2-candidate-0012',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='8e87a447f0eb89ef7d1bfbe28e6e4e1c2b5a1211dca1835a8466552bf3155957',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])
