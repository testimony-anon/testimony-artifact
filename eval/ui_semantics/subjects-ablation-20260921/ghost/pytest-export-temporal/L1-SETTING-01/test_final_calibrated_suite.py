"""Generated from a frozen UISemTest M14 suite; do not edit by hand."""

def test_relation_test_2166074ab22426e22e4c(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/settings/; basic constraint P15 requires observation $.settings (array) (actual_response) to have unique members by strict-tuple identity [$.key]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0001\nCanonical relation core: 844567f611c2089ba314afc6f1a64503470c1665a03f3d8408ac5b4954fa9d0d\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0001
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'PUT',
      'path': '/ghost/api/admin/settings/',
      'request_ref': 'r20260920-170747-9e70:request:4'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/settings/',
      'request_ref': 'r20260920-170747-9e70:request:5'}]
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
        test_id='relation-test-2166074ab22426e22e4c',
        candidate_id='v2-candidate-0001',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='0a311d13158f8f5c5218b829c158f32678100ac934ed4f58acc5c1ca0432f238',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_13ef99ff962e7b238480(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/settings/; basic constraint P02 requires observation $.meta.filters.group (string) to strictly equal actual request query $.group (string); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0002\nCanonical relation core: e2ee7575dd5ab6932dced4af90844c5273eb37b8eedc93cd537a4eb9aafea95d\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0002
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'PUT',
      'path': '/ghost/api/admin/settings/',
      'request_ref': 'r20260920-170747-9e70:request:4'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/settings/',
      'request_ref': 'r20260920-170747-9e70:request:5'}]
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
        test_id='relation-test-13ef99ff962e7b238480',
        candidate_id='v2-candidate-0002',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='cc8f65a466a5c4bbc1c9608facc9228e48a9b3c8d67a75ca8621dba484146102',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])
