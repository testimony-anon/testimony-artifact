"""Generated from a frozen UISemTest M14 suite; do not edit by hand."""

def test_relation_test_0cec65d0d938801cf218(uisemtest_runtime):
    'Business summary: Observation actor_b GET /api/2fa/status; basic constraint P21 requires observation $.isEnabled (boolean) to have JSON type boolean; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0001\nCanonical relation core: be261853458627cc9bfc1b6058c3fd6727948710f18e43dbc285e04de88b42ce\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0001
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_b']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_b',
      'method': 'GET',
      'path': '/settings/profile',
      'request_ref': 'r20260920-082849-5031:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'actor_b',
      'method': 'POST',
      'path': '/api/auth/verify',
      'request_ref': 'r20260920-082849-5031:request:19'},
     {'kind': 'http',
      'phase': 'setup[2]',
      'actor': 'actor_b',
      'method': 'GET',
      'path': '/api/config',
      'request_ref': 'r20260920-082849-5031:request:20'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_b',
      'method': 'GET',
      'path': '/api/2fa/status',
      'request_ref': 'r20260920-082849-5031:request:21'}]
    assertions = [{'assertion_id': 'v2-candidate-0001-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'boolean',
                    'family': 'P21',
                    'target': {'path': '$.isEnabled', 'role': 'observation', 'value_type': 'boolean'}}},
     {'assertion_id': 'v2-candidate-0001-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0001-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'boolean',
                    'response_ref': 'observation',
                    'target_path': '$.isEnabled',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-0cec65d0d938801cf218',
        candidate_id='v2-candidate-0001',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='fa87aecb38998bcc184d241ae0c3f9b510bf1bc37e5a39b0104ab146143befb3',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_8d015901580ef8fec452(uisemtest_runtime):
    'Business summary: Observation actor_b GET /api/config; basic constraint P21 requires observation $.cloudMode (boolean) to have JSON type boolean; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0002\nCanonical relation core: c2f24eb6cdf6834d9e40a292442b80b441a7c520bfbc4bbd688acdfffb3500c3\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0002
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_b']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_b',
      'method': 'GET',
      'path': '/settings/profile',
      'request_ref': 'r20260920-082849-5031:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'actor_b',
      'method': 'POST',
      'path': '/api/auth/verify',
      'request_ref': 'r20260920-082849-5031:request:19'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_b',
      'method': 'GET',
      'path': '/api/config',
      'request_ref': 'r20260920-082849-5031:request:20'}]
    assertions = [{'assertion_id': 'v2-candidate-0002-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'boolean',
                    'family': 'P21',
                    'target': {'path': '$.cloudMode', 'role': 'observation', 'value_type': 'boolean'}}},
     {'assertion_id': 'v2-candidate-0002-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0002-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'boolean',
                    'response_ref': 'observation',
                    'target_path': '$.cloudMode',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-8d015901580ef8fec452',
        candidate_id='v2-candidate-0002',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='b5db28698259ae614fe3ff6016e8f7475ed607707f1ee6142091d3358ec3a40e',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])
