"""Generated from a frozen UISemTest M14 suite; do not edit by hand."""

def test_relation_test_0d159682454a97fc2fc8(uisemtest_runtime):
    'Business summary: Observation actor_a POST /graphql; basic constraint P01 requires field observation $.data.listBankAccount (array) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0001\nCanonical relation core: d3c7ada35b403de8dc0d086a95e2cc1ab064974f6176b6be7b78d9665dad0c02\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0001
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
    assertions = [{'assertion_id': 'v2-candidate-0001-business-01',
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
     {'assertion_id': 'v2-candidate-0001-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0001-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.data.listBankAccount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-0d159682454a97fc2fc8',
        candidate_id='v2-candidate-0001',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='25f6ae28aea9a97de2a27da0755e13ca4532e88de214fdab26aebbe788f840aa',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_04248a93e15da63dee98(uisemtest_runtime):
    'Business summary: Observation actor_a GET /notifications; basic constraint P01 requires field observation $.results (array) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0002\nCanonical relation core: c5ee3f2888c17ec095da06f347acf7fb52ee82ade70b280843a2d1db952f796f\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[8].rationale\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
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
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
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
        test_id='relation-test-04248a93e15da63dee98',
        candidate_id='v2-candidate-0002',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='1df989465a76ad2f10d2b8a8b4e059b95420307a4a4f8b00312a95bdf456db0a',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_6eb8fdf1ecd63b74eaf7(uisemtest_runtime):
    'Business summary: Observation actor_a GET /notifications; basic constraint P15 requires observation $.results (array) (actual_response) to have unique members by strict-tuple identity [$.id]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0003\nCanonical relation core: 2cd93bc696624f213a40d5c1888f4e6ce833cf6e558eb44f7dc4d49030da8ee1\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
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
        test_id='relation-test-6eb8fdf1ecd63b74eaf7',
        candidate_id='v2-candidate-0003',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='064dff6a0202029e3cb281a0b8ade372e7e0afbe1eea08ef14574a91a6cff49d',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_00b16b374dfcd7889cdd(uisemtest_runtime):
    'Business summary: Observation actor_a POST /graphql; basic constraint P15 requires observation $.data.listBankAccount (array) (actual_response) to have unique members by strict-tuple identity [$.id]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0004\nCanonical relation core: 18daa76ce812c63f2be988874b5825d4970a3389fbb61742a8d7dac60ce04ad3\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[5].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0004
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
    assertions = [{'assertion_id': 'v2-candidate-0004-business-01',
      'class': 'business',
      'predicate_type': 'P15',
      'predicate': {'collection': {'path': '$.data.listBankAccount',
                                   'role': 'observation',
                                   'value_type': 'array'},
                    'family': 'P15',
                    'identity': {'paths': ['$.id'], 'semantics': 'strict-tuple'},
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
                    'target_path': '$.data.listBankAccount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-00b16b374dfcd7889cdd',
        candidate_id='v2-candidate-0004',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='721a86a70680d11e75ef36f518890e5ff8d3f8a8815167ee37180d23459a1414',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_aa64557612f517b7117c(uisemtest_runtime):
    'Business summary: Observation actor_a GET /notifications; basic constraint P21 requires observation $.results (array) to have JSON type array; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0005\nCanonical relation core: 5a5c6a8742f79c26bf644ca95fbfbdccb010c5e602f8515f3bf0022f39b72559\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0005
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
    assertions = [{'assertion_id': 'v2-candidate-0005-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'array',
                    'family': 'P21',
                    'target': {'path': '$.results', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0005-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0005-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.results',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-aa64557612f517b7117c',
        candidate_id='v2-candidate-0005',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='fd09fbc171c42284649b9c6066fb90cdd913e861152fa0d635ec6ed118054d34',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_9b128fb63218ba48bc8a(uisemtest_runtime):
    'Business summary: Observation actor_a GET /notifications; basic constraint For every member of observation $.results (array) in actual_response: P01 requires field item $.id (string) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0006\nCanonical relation core: ba49c5eac48b3b3a31e57fe2331ff30762d25180d6f3e6726401c06c8acba314\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0006
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
    assertions = [{'assertion_id': 'v2-candidate-0006-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'absent_statuses': [],
                             'family': 'P01',
                             'identity': None,
                             'member': None,
                             'operator': 'present',
                             'target': {'path': '$.id', 'role': 'item', 'value_type': 'string'}},
                    'collection': {'path': '$.results', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
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
        test_id='relation-test-9b128fb63218ba48bc8a',
        candidate_id='v2-candidate-0006',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='48c30f4cef5c1f37038d7dc83333e1a051bdf75b69b29f272e66e06e01915bfb',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_2f8b06fdd6cce4b56fa0(uisemtest_runtime):
    'Business summary: Observation actor_a POST /graphql; basic constraint P21 requires observation $.data.listBankAccount (array) to have JSON type array; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0007\nCanonical relation core: eb5d9f8c39cc0f385308bf3cb16a61f9f3c098c2acb3d80ae73384609c97ceb9\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[4].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
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
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'array',
                    'family': 'P21',
                    'target': {'path': '$.data.listBankAccount',
                               'role': 'observation',
                               'value_type': 'array'}}},
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
        test_id='relation-test-2f8b06fdd6cce4b56fa0',
        candidate_id='v2-candidate-0007',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='843e9f8994f1e5c6524bac64718cebeb7b75b866ff075beadb393377d813286f',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_021e909cc39e99a5c9e0(uisemtest_runtime):
    'Business summary: Observation actor_a POST /graphql; basic constraint For every member of observation $.data.listBankAccount (array) in actual_response: P21 requires item $.isDeleted (boolean) to have JSON type boolean; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0008\nCanonical relation core: 104de15223967f2fc268791e275d0381540e9e5c7e079e008cdbafb2156cdc20\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
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
        test_id='relation-test-021e909cc39e99a5c9e0',
        candidate_id='v2-candidate-0008',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='4cac64c3a59410ebe8c67dea3846126303d51eedaf399e4e51b391ccf90b1396',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_40447d5af3d4111accf8(uisemtest_runtime):
    'Business summary: Observation actor_a GET /notifications; basic constraint For every member of observation $.results (array) in actual_response: P21 requires item $.isRead (boolean) to have JSON type boolean; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0009\nCanonical relation core: 35ce288c373133bbdb3a3513f9b1295bfd8eb348506b928811c0254f513c15df\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
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
        test_id='relation-test-40447d5af3d4111accf8',
        candidate_id='v2-candidate-0009',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='1525e4940b7ede3d39fec39fbaf1d183194d7662212d179073cc91c466da8b18',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])
