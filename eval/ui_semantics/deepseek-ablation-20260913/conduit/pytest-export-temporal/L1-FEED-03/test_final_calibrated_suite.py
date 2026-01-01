"""Generated from a frozen UISemTest M14 suite; do not edit by hand."""

def test_relation_test_19262f120f06726df0d7(uisemtest_runtime):
    "Business summary: Queries source_query actor_a GET /api/articles; followup_query:q1 actor_a GET /api/articles; business predicate P17 requires followup_query:q1 $.articles (array) equal source_query $.articles (array); representation=multiset, basis=full_json_value, projection=[], identity=None; query scope={'closures': [], 'scope': 'actual_response'}; input transform={'keys': ['limit', 'offset'], 'kind': 'equivalent_input', 'location': 'query', 'semantics': {'evidence_refs': ['r20260901-190005-369b:request:39', 'r20260901-190005-369b:request:41'], 'rationale': 'Both recorded reads carry the identical observed selector values limit=3 and offset=0 on the same path; the proposed rule freezes them as equivalent inputs.', 'source': 'hypothesis', 'value': 'equivalent', 'value_type': 'string'}}.\nCandidate ID: v2-candidate-0010\nCanonical relation core: 1f7fc928f00f0e82ca09362c74ec034eb090dc37dc8e4aa4f9205e4b8170f5ec\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0004/provider_response_envelope.json#content(from-json).candidates[6].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V3: v2-candidate-0010
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'metamorphic_query', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'source_query/producer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-190005-369b:request:39'},
     {'kind': 'http',
      'phase': 'followup_query[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-190005-369b:request:41'}]
    assertions = [{'assertion_id': 'v2-candidate-0010-business-01',
      'class': 'business',
      'predicate_type': 'P17',
      'predicate': {'comparison_basis': 'full_json_value',
                    'expected_difference': None,
                    'family': 'P17',
                    'identity': None,
                    'left': {'path': '$.articles', 'role': 'followup_query:q1', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'representation': 'multiset',
                    'right': {'path': '$.articles', 'role': 'source_query', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0010-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0010-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0010-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.articles',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-19262f120f06726df0d7',
        candidate_id='v2-candidate-0010',
        protocol_kind='V3',
        normal_runs=1,
        source_test_sha256='7f0d9221d1b60e393a38fdf6c8219b5c1abd41ed059a22d830b2400c763b4d20',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_a29e6e058c6f889c0c2a(uisemtest_runtime):
    "Business summary: Queries source_query actor_a GET /api/articles; followup_query:q1 actor_a GET /api/articles; business predicate P17 requires followup_query:q1 $.articles (array) equal source_query $.articles (array); representation=multiset, basis=full_json_value, projection=[], identity=None; query scope={'closures': [], 'scope': 'actual_response'}; input transform={'keys': ['limit', 'offset'], 'kind': 'equivalent_input', 'location': 'query', 'semantics': {'evidence_refs': ['r20260901-190005-369b:request:39', 'r20260901-190005-369b:request:41'], 'rationale': 'both recorded reads send the identical GET /api/articles selector limit=3&offset=0 from the same actor/session, so the follow-up selector is proposed as equivalent input', 'source': 'hypothesis', 'value': 'equivalent', 'value_type': 'string'}}.\nCandidate ID: v2-candidate-0027\nCanonical relation core: 1f7fc928f00f0e82ca09362c74ec034eb090dc37dc8e4aa4f9205e4b8170f5ec\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0007/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V3: v2-candidate-0027
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'metamorphic_query', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'source_query/producer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-190005-369b:request:39'},
     {'kind': 'http',
      'phase': 'followup_query[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-190005-369b:request:41'}]
    assertions = [{'assertion_id': 'v2-candidate-0027-business-01',
      'class': 'business',
      'predicate_type': 'P17',
      'predicate': {'comparison_basis': 'full_json_value',
                    'expected_difference': None,
                    'family': 'P17',
                    'identity': None,
                    'left': {'path': '$.articles', 'role': 'followup_query:q1', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'representation': 'multiset',
                    'right': {'path': '$.articles', 'role': 'source_query', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0027-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0027-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0027-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.articles',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-a29e6e058c6f889c0c2a',
        candidate_id='v2-candidate-0027',
        protocol_kind='V3',
        normal_runs=1,
        source_test_sha256='d6802cdcd960ce615127d7780c49d0678ad422319e1a40b7ceb4d7b6c948b496',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])
