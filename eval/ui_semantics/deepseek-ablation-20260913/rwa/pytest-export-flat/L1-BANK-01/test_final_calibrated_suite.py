"""Generated from a frozen UISemTest M14 suite; do not edit by hand."""

def test_relation_test_c2b0f8ec42d0a3fdde23(uisemtest_runtime):
    'Business summary: Observation actor_a POST /graphql; basic constraint P01 requires field observation $.data.listBankAccount (array) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0001\nCanonical relation core: d3c7ada35b403de8dc0d086a95e2cc1ab064974f6176b6be7b78d9665dad0c02\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0001
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021525-3189:request:0'}]
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
        test_id='relation-test-c2b0f8ec42d0a3fdde23',
        candidate_id='v2-candidate-0001',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='9a9c364eea31ce57ae062759f1611d5ce7294817ee74f78f8461e36fd4d55942',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_65a52f8003be759e5cf6(uisemtest_runtime):
    'Business summary: Observation actor_a POST /graphql; basic constraint P21 requires observation $.data.listBankAccount (array) to have JSON type array; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0002\nCanonical relation core: eb5d9f8c39cc0f385308bf3cb16a61f9f3c098c2acb3d80ae73384609c97ceb9\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0002
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021525-3189:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0002-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'array',
                    'family': 'P21',
                    'target': {'path': '$.data.listBankAccount',
                               'role': 'observation',
                               'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0002-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0002-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.data.listBankAccount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-65a52f8003be759e5cf6',
        candidate_id='v2-candidate-0002',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='d32113d34e2cc2a7bff5f5c1fa405949e15075454259dcfbc15b7b5dc2a934eb',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_dd460b5fab3e3b31d21d(uisemtest_runtime):
    'Business summary: Observation actor_a POST /graphql; basic constraint P15 requires observation $.data.listBankAccount (array) (actual_response) to have unique members by strict-tuple identity [$.id]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0003\nCanonical relation core: 18daa76ce812c63f2be988874b5825d4970a3389fbb61742a8d7dac60ce04ad3\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0003
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021525-3189:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0003-business-01',
      'class': 'business',
      'predicate_type': 'P15',
      'predicate': {'collection': {'path': '$.data.listBankAccount',
                                   'role': 'observation',
                                   'value_type': 'array'},
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
                    'target_path': '$.data.listBankAccount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-dd460b5fab3e3b31d21d',
        candidate_id='v2-candidate-0003',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='5017ae9fed4a1d5fbcffa57f8ba72ab9c1de41669cbb1c15588ecbd3ccbd178e',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_55d6ea88bef8a04288d3(uisemtest_runtime):
    'Business summary: Observation actor_a POST /graphql; basic constraint For every member of observation $.data.listBankAccount (array) in actual_response: P21 requires item $.isDeleted (boolean) to have JSON type boolean; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0004\nCanonical relation core: 104de15223967f2fc268791e275d0381540e9e5c7e079e008cdbafb2156cdc20\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0004
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021525-3189:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0004-business-01',
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
        test_id='relation-test-55d6ea88bef8a04288d3',
        candidate_id='v2-candidate-0004',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='a6ac6743ce8e012c3336b5312df867e85b1dc034a2a6e75055bbebb380bdafed',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_f2ed7dae342eaebbf1f2(uisemtest_runtime):
    'Business summary: Observation actor_a POST /graphql; basic constraint For every member of observation $.data.listBankAccount (array) in actual_response: P01 requires field item $.id (string) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0005\nCanonical relation core: 08206e3c37c08884a56143942ff9467fb6ca22804ff8c4e95d1d4e459ed937f2\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[4].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0005
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021525-3189:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0005-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'absent_statuses': [],
                             'family': 'P01',
                             'identity': None,
                             'member': None,
                             'operator': 'present',
                             'target': {'path': '$.id', 'role': 'item', 'value_type': 'string'}},
                    'collection': {'path': '$.data.listBankAccount',
                                   'role': 'observation',
                                   'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
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
        test_id='relation-test-f2ed7dae342eaebbf1f2',
        candidate_id='v2-candidate-0005',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='79239b85ff2550bb14fea942081f71b4632a767bbaeb714a6aafc8b40693f4b9',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_742740a8c9878610a783(uisemtest_runtime):
    'Business summary: Producer actor_a POST /graphql; observer actor_a POST /graphql; business predicate P14 requires producer_response $.data.createBankAccount (object) to be added between before $.data.listBankAccount (array) and after $.data.listBankAccount (array) by strict-tuple identity [$.id->$.id].\nCandidate ID: v2-candidate-0006\nCanonical relation core: d827d500ab73e7b544d2b15361095c87880c6e84ba07f199e0698043d068efac\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V4: v2-candidate-0006
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'workflow', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021525-3189:request:0'},
     {'kind': 'http',
      'phase': 'before_observer',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021525-3189:request:0'},
     {'kind': 'http',
      'phase': 'producer',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021525-3189:request:4'},
     {'kind': 'settle',
      'policy': {'consecutive_identical_observations': 3,
                 'maximum_duration_ms': 2000,
                 'minimum_duration_ms': 500,
                 'poll_interval_ms': 100,
                 'rule': 'bounded_semantic_stability_v1',
                 'schema_version': 'uisemtest-current-settle-policy-v2'}},
     {'kind': 'http',
      'phase': 'after_observer',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021525-3189:request:6'}]
    assertions = [{'assertion_id': 'v2-candidate-0006-business-01',
      'class': 'business',
      'predicate_type': 'P14',
      'predicate': {'after': {'path': '$.data.listBankAccount', 'role': 'after', 'value_type': 'array'},
                    'before': {'path': '$.data.listBankAccount',
                               'role': 'before',
                               'value_type': 'array'},
                    'family': 'P14',
                    'identity': {'field_pairs': [{'collection_item_path': '$.id',
                                                  'member_path': '$.id'}],
                                 'semantics': 'strict-tuple'},
                    'member': {'ref': {'path': '$.data.createBankAccount',
                                       'role': 'producer_response',
                                       'value_type': 'object'},
                               'source': 'role'},
                    'operator': 'added'}},
     {'assertion_id': 'v2-candidate-0006-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0006-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0006-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.data.listBankAccount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-742740a8c9878610a783',
        candidate_id='v2-candidate-0006',
        protocol_kind='V4',
        normal_runs=1,
        source_test_sha256='94f62ee0b8463b676d4df7235c45bb2ce1c93000cecc03c072825c34a0174cc1',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_ceffac21072c797a9791(uisemtest_runtime):
    'Business summary: Observation actor_a POST /graphql; basic constraint P15 requires observation $.data.listBankAccount (array) (actual_response) to have unique members by strict-tuple identity [$.id]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0007\nCanonical relation core: 18daa76ce812c63f2be988874b5825d4970a3389fbb61742a8d7dac60ce04ad3\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0007
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021525-3189:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021525-3189:request:4'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021525-3189:request:6'}]
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
        test_id='relation-test-ceffac21072c797a9791',
        candidate_id='v2-candidate-0007',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='7f1cae8f8db796f6d7cea28fc8d6a401ea19e50d363e62ed96c63e9e7be97057',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_5b076cea9d055f8fc64c(uisemtest_runtime):
    'Business summary: Observation actor_a POST /graphql; basic constraint P01 requires field observation $.data.listBankAccount (array) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0008\nCanonical relation core: d3c7ada35b403de8dc0d086a95e2cc1ab064974f6176b6be7b78d9665dad0c02\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0008
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021525-3189:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021525-3189:request:4'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021525-3189:request:6'}]
    assertions = [{'assertion_id': 'v2-candidate-0008-business-01',
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
        test_id='relation-test-5b076cea9d055f8fc64c',
        candidate_id='v2-candidate-0008',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='525c04c5e994db0cb0bfb3b65adc7f3358fa707330e15aba79bfd7c9c943f354',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_e433d7fa5730064b2b77(uisemtest_runtime):
    'Business summary: Observation actor_a POST /graphql; basic constraint For every member of observation $.data.listBankAccount (array) in actual_response: P21 requires item $.id (string) to have JSON type string; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0009\nCanonical relation core: b7e7363b07257d3475abf8c22a2158f4e0c1c7ecf4e5fb8af284c02e8dca478c\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0009
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021525-3189:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0009-business-01',
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
     {'assertion_id': 'v2-candidate-0009-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0009-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.data.listBankAccount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-e433d7fa5730064b2b77',
        candidate_id='v2-candidate-0009',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='2291f6b0712329a74f5913642c4f07771191860734b65a4782d0633d49611dd1',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_0061a6c4d26dd67af403(uisemtest_runtime):
    'Business summary: Observation actor_a POST /graphql; basic constraint For every member of observation $.data.listBankAccount (array) in actual_response: P02 requires item $.isDeleted (boolean) to strictly equal frozen hypothesis False (boolean); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0011\nCanonical relation core: b4e965a90c255d1c6201be675756931e486275e3ee0b14007f64a2aa6f9ff946\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[4].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0011
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021525-3189:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0011-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'family': 'P02',
                             'left': {'path': '$.isDeleted', 'role': 'item', 'value_type': 'boolean'},
                             'operator': 'eq',
                             'right': {'evidence_refs': ['r20260902-021525-3189:request:0'],
                                       'rationale': 'The ListBankAccount selection exposes a boolean '
                                                    'isDeleted member field; propose that this listing '
                                                    'returns only non-deleted bank accounts. Frozen '
                                                    'business hypothesis, not a proven requirement, '
                                                    'not prevalidated against the recording.',
                                       'source': 'hypothesis',
                                       'value': False,
                                       'value_type': 'boolean'}},
                    'collection': {'path': '$.data.listBankAccount',
                                   'role': 'observation',
                                   'value_type': 'array'},
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
                    'target_path': '$.data.listBankAccount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-0061a6c4d26dd67af403',
        candidate_id='v2-candidate-0011',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='7d038d7d72c5acc42532d29fce429e4f9c0f7de154aef151da623c50070d9615',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_28ed28dcaf76612359d7(uisemtest_runtime):
    'Business summary: Producer actor_a POST /graphql; observer actor_a POST /graphql; business predicate P14 requires producer_request $.variables (object) to be added between before $.data.listBankAccount (array) and after $.data.listBankAccount (array) by strict-tuple identity [$.bankName->$.bankName, $.accountNumber->$.accountNumber, $.routingNumber->$.routingNumber].\nCandidate ID: v2-candidate-0012\nCanonical relation core: 6b72b6d60324e25a6a67f71c550274fa814124b8507bf1d0ca0bf5c5857a030e\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V4: v2-candidate-0012
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'workflow', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021525-3189:request:0'},
     {'kind': 'http',
      'phase': 'before_observer',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021525-3189:request:0'},
     {'kind': 'http',
      'phase': 'producer',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021525-3189:request:4'},
     {'kind': 'settle',
      'policy': {'consecutive_identical_observations': 3,
                 'maximum_duration_ms': 2000,
                 'minimum_duration_ms': 500,
                 'poll_interval_ms': 100,
                 'rule': 'bounded_semantic_stability_v1',
                 'schema_version': 'uisemtest-current-settle-policy-v2'}},
     {'kind': 'http',
      'phase': 'after_observer',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/graphql',
      'request_ref': 'r20260902-021525-3189:request:6'}]
    assertions = [{'assertion_id': 'v2-candidate-0012-business-01',
      'class': 'business',
      'predicate_type': 'P14',
      'predicate': {'after': {'path': '$.data.listBankAccount', 'role': 'after', 'value_type': 'array'},
                    'before': {'path': '$.data.listBankAccount',
                               'role': 'before',
                               'value_type': 'array'},
                    'family': 'P14',
                    'identity': {'field_pairs': [{'collection_item_path': '$.bankName',
                                                  'member_path': '$.bankName'},
                                                 {'collection_item_path': '$.accountNumber',
                                                  'member_path': '$.accountNumber'},
                                                 {'collection_item_path': '$.routingNumber',
                                                  'member_path': '$.routingNumber'}],
                                 'semantics': 'strict-tuple'},
                    'member': {'ref': {'path': '$.variables',
                                       'role': 'producer_request',
                                       'value_type': 'object'},
                               'source': 'role'},
                    'operator': 'added'}},
     {'assertion_id': 'v2-candidate-0012-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0012-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0012-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.data.listBankAccount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-28ed28dcaf76612359d7',
        candidate_id='v2-candidate-0012',
        protocol_kind='V4',
        normal_runs=1,
        source_test_sha256='73dab82e03d36f2c170c5257d9739dec0f2e1062532f79feeb1134a35e771864',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])
