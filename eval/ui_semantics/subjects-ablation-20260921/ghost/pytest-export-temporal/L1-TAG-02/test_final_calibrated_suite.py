"""Generated from a frozen UISemTest M14 suite; do not edit by hand."""

def test_relation_test_206e3afe50f3cc29885e(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tags/6ab001613440c500013ba8f8/; basic constraint P15 requires observation $.tags (array) (actual_response) to have unique members by strict-tuple identity [$.id]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0001\nCanonical relation core: 52c8643284908340f212a88cd0390caab4269b865cb730ae4a936edaa47e773b\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0001
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/tags/6ab001613440c500013ba8f8/',
      'request_ref': 'r20260920-170425-9c2b:request:24'}]
    assertions = [{'assertion_id': 'v2-candidate-0001-business-01',
      'class': 'business',
      'predicate_type': 'P15',
      'predicate': {'collection': {'path': '$.tags', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P15',
                    'identity': {'paths': ['$.id'], 'semantics': 'strict-tuple'},
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
                    'target_path': '$.tags',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-206e3afe50f3cc29885e',
        candidate_id='v2-candidate-0001',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='276a55bfa7bc9892885ae160e5fcc122d023a0c65ba6a5b5cf5024512552e621',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_5e9bf44b6d779a35ff32(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tags/6ab001613440c500013ba8f8/; basic constraint P01 requires field observation $.tags (array) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0002\nCanonical relation core: 8e4d451de19819cfbedb040f3e58eb032f515a4a0486ccf0863cc2f98fe17572\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0002
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/tags/6ab001613440c500013ba8f8/',
      'request_ref': 'r20260920-170425-9c2b:request:24'}]
    assertions = [{'assertion_id': 'v2-candidate-0002-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.tags', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0002-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0002-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tags',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-5e9bf44b6d779a35ff32',
        candidate_id='v2-candidate-0002',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='fd78f28cb0ed3b5e75a5eb2585938e8233ef346d214ac5c68b9a531cca27989b',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])
