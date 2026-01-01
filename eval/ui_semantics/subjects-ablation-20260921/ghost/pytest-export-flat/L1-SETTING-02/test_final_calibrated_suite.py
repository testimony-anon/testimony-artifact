"""Generated from a frozen UISemTest M14 suite; do not edit by hand."""

def test_relation_test_54d0501ca5adb10100e2(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/settings/; basic constraint P15 requires observation $.settings (array) (actual_response) to have unique members by strict-tuple identity [$.key]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0001\nCanonical relation core: 844567f611c2089ba314afc6f1a64503470c1665a03f3d8408ac5b4954fa9d0d\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0001
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'PUT',
      'path': '/ghost/api/admin/settings/',
      'request_ref': 'r20260920-170815-cf1e:request:4'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/settings/',
      'request_ref': 'r20260920-170815-cf1e:request:5'}]
    assertions = [{'assertion_id': 'v2-candidate-0001-business-01',
      'class': 'business',
      'predicate_type': 'P15',
      'predicate': {'collection': {'path': '$.settings', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P15',
                    'identity': {'paths': ['$.key'], 'semantics': 'strict-tuple'},
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0001-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0001-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.settings',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-54d0501ca5adb10100e2',
        candidate_id='v2-candidate-0001',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='1bb139e96a55a286a2be76dc7e238015ff26e3aed8aeba6d3ea473f2cef58300',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_fdc4e0dfa7da5d3c9ddd(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/settings/; basic constraint P02 requires observation $.meta.filters.group (string) to strictly equal actual request query $.group (string); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0002\nCanonical relation core: e2ee7575dd5ab6932dced4af90844c5273eb37b8eedc93cd537a4eb9aafea95d\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[4].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0002
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'PUT',
      'path': '/ghost/api/admin/settings/',
      'request_ref': 'r20260920-170815-cf1e:request:4'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/settings/',
      'request_ref': 'r20260920-170815-cf1e:request:5'}]
    assertions = [{'assertion_id': 'v2-candidate-0002-business-01',
      'class': 'business',
      'predicate_type': 'P02',
      'predicate': {'family': 'P02',
                    'left': {'path': '$.meta.filters.group',
                             'role': 'observation',
                             'value_type': 'string'},
                    'operator': 'eq',
                    'right': {'ref': {'location': 'query',
                                      'path': '$.group',
                                      'role': 'observation_request',
                                      'value_type': 'string'},
                              'source': 'request'}}},
     {'assertion_id': 'v2-candidate-0002-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0002-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'string',
                    'response_ref': 'observation',
                    'target_path': '$.meta.filters.group',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-fdc4e0dfa7da5d3c9ddd',
        candidate_id='v2-candidate-0002',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='80083daac4158e3b12d172d46122eee543beb9557991db1a2f330db97007dcb6',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_01251448002785704628(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/settings/; basic constraint P21 requires observation $.settings (array) to have JSON type array; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0003\nCanonical relation core: 753dec677458c4c9f2849f90c0d56c9fd2a4939dbab3cbc8c8e81b5dd45b7525\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0003
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'PUT',
      'path': '/ghost/api/admin/settings/',
      'request_ref': 'r20260920-170815-cf1e:request:4'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/settings/',
      'request_ref': 'r20260920-170815-cf1e:request:5'}]
    assertions = [{'assertion_id': 'v2-candidate-0003-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'array',
                    'family': 'P21',
                    'target': {'path': '$.settings', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0003-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0003-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.settings',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-01251448002785704628',
        candidate_id='v2-candidate-0003',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='c672b4e95b1d56a06ee07c5da0d1091ba8d6f81af3da7be85d9fbb2f02c0a15f',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_0e63294c1982fe2013d6(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/settings/; basic constraint P21 requires observation $.meta.filters.group (string) to have JSON type string; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0004\nCanonical relation core: ca7d04e44aaa86dab4962fc8585488bbf2fe7a82f43a87354aed38c5e9c2c263\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0004
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'PUT',
      'path': '/ghost/api/admin/settings/',
      'request_ref': 'r20260920-170815-cf1e:request:4'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/settings/',
      'request_ref': 'r20260920-170815-cf1e:request:5'}]
    assertions = [{'assertion_id': 'v2-candidate-0004-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'string',
                    'family': 'P21',
                    'target': {'path': '$.meta.filters.group',
                               'role': 'observation',
                               'value_type': 'string'}}},
     {'assertion_id': 'v2-candidate-0004-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0004-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'string',
                    'response_ref': 'observation',
                    'target_path': '$.meta.filters.group',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-0e63294c1982fe2013d6',
        candidate_id='v2-candidate-0004',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='f31b5c5f32a70298072c9267cf0e429c1a7694e390fcc68c5f9f89393b457d64',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])
