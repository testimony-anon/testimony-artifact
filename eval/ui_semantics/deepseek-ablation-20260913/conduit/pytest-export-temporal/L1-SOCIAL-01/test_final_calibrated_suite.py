"""Generated from a frozen UISemTest M14 suite; do not edit by hand."""

def test_relation_test_8720b08ba98529c7e9cb(uisemtest_runtime):
    "Business summary: Observation actor_a GET /api/articles; business relation P19 requires observation $.articlesCount (integer) = count(observation $.articles (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0001\nCanonical relation core: 7a713940260a9a7496fb46b17eee63a4256089a4809389fcc0b354fa7b9edaf1\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0001
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/api/profiles/uisemtest_actor_b',
      'request_ref': 'r20260901-190427-8ca5:request:0'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-190427-8ca5:request:1'}]
    assertions = [{'assertion_id': 'v2-candidate-0001-business-01',
      'class': 'business',
      'predicate_type': 'P19',
      'predicate': {'collection': {'path': '$.articles', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P19',
                    'numeric_mode': 'exact',
                    'operator': 'count',
                    'output': {'path': '$.articlesCount',
                               'role': 'observation',
                               'value_type': 'integer'},
                    'scope': 'actual_response',
                    'units': {'evidence_refs': ['r20260901-190427-8ca5:request:1'],
                              'rationale': 'Proposed rule grounded in the cited visible request; not '
                                           'prevalidated.',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0001-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0001-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.articlesCount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-8720b08ba98529c7e9cb',
        candidate_id='v2-candidate-0001',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='ebc0c5e0ab3d430319737bd74c2d8f08d6e526d7012347f3d2baffb4562d37eb',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_a2646d5f963f9abe0d05(uisemtest_runtime):
    "Business summary: Observation actor_a GET /api/articles; basic constraint P11 requires count(observation $.articles (array)) <= this request's query.limit; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0002\nCanonical relation core: 12771e7a695c5e2f56d3c3b8d96ad1bfa104223742a96a9e27fdf390e74265b3\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0004/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[6].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0002
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/api/profiles/uisemtest_actor_b',
      'request_ref': 'r20260901-190427-8ca5:request:0'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-190427-8ca5:request:1'}]
    assertions = [{'assertion_id': 'v2-candidate-0002-business-01',
      'class': 'business',
      'predicate_type': 'P11',
      'predicate': {'collection': {'path': '$.articles', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P11',
                    'operator': 'le',
                    'right': {'ref': {'location': 'query',
                                      'path': '$.limit',
                                      'role': 'observation_request',
                                      'value_type': 'integer'},
                              'source': 'request'}}},
     {'assertion_id': 'v2-candidate-0002-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0002-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.articles',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-a2646d5f963f9abe0d05',
        candidate_id='v2-candidate-0002',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='80b867b5ea98b1b6f2a1436c9284d85cbd92d4ca0360833b0df5a36a30cddaf6',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_b13a1cf98976879e3311(uisemtest_runtime):
    'Business summary: Observation actor_a GET /api/profiles/uisemtest_actor_b; basic constraint P21 requires observation $.profile.followersCount (integer) to have JSON type integer; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0003\nCanonical relation core: 80ef411b0d2243e25e800998d35f8025f7cdb058a8565ee0b6af5dcd97c2768d\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0003
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/api/profiles/uisemtest_actor_b',
      'request_ref': 'r20260901-190427-8ca5:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0003-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'integer',
                    'family': 'P21',
                    'target': {'path': '$.profile.followersCount',
                               'role': 'observation',
                               'value_type': 'integer'}}},
     {'assertion_id': 'v2-candidate-0003-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0003-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.profile.followersCount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-b13a1cf98976879e3311',
        candidate_id='v2-candidate-0003',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='fa29b96593f0ac1d7551e56b8d00d487b13a4ea2088e0e74776867d4c84f8be7',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_db0b2e1d30c23dad0c52(uisemtest_runtime):
    "Business summary: Observation actor_a GET /api/profiles/uisemtest_actor_b; basic constraint P02 requires observation $.profile.username (string) to strictly equal frozen hypothesis 'uisemtest_actor_b' (string); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0004\nCanonical relation core: a9f3f18b3091a872b655803b08d37d05267e1c8dad4497c79cb592b8a2d4aa02\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[4].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0004
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/api/profiles/uisemtest_actor_b',
      'request_ref': 'r20260901-190427-8ca5:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0004-business-01',
      'class': 'business',
      'predicate_type': 'P02',
      'predicate': {'family': 'P02',
                    'left': {'path': '$.profile.username',
                             'role': 'observation',
                             'value_type': 'string'},
                    'operator': 'eq',
                    'right': {'evidence_refs': ['r20260901-190427-8ca5:request:0'],
                              'rationale': 'Proposed rule grounded in the cited visible request; not '
                                           'prevalidated.',
                              'source': 'hypothesis',
                              'value': 'uisemtest_actor_b',
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
                    'target_path': '$.profile.username',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-db0b2e1d30c23dad0c52',
        candidate_id='v2-candidate-0004',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='02f1e96b62367e67727ef0d2a4f21b19541b164ac4a3e6e93c04716fea4addc5',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_2e5ac340164d1f21f698(uisemtest_runtime):
    "Business summary: Observation actor_a GET /api/articles; business relation P19 requires observation $.articlesCount (integer) = count(observation $.articles (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0006\nCanonical relation core: 7a713940260a9a7496fb46b17eee63a4256089a4809389fcc0b354fa7b9edaf1\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0006
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/api/profiles/uisemtest_actor_b',
      'request_ref': 'r20260901-190427-8ca5:request:0'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-190427-8ca5:request:1'}]
    assertions = [{'assertion_id': 'v2-candidate-0006-business-01',
      'class': 'business',
      'predicate_type': 'P19',
      'predicate': {'collection': {'path': '$.articles', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P19',
                    'numeric_mode': 'exact',
                    'operator': 'count',
                    'output': {'path': '$.articlesCount',
                               'role': 'observation',
                               'value_type': 'integer'},
                    'scope': 'actual_response',
                    'units': {'evidence_refs': ['r20260901-190427-8ca5:request:1'],
                              'rationale': "Count of the response's own article array is proposed to "
                                           'equal its own integer summary field; frozen before '
                                           'execution.',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0006-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0006-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.articlesCount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-2e5ac340164d1f21f698',
        candidate_id='v2-candidate-0006',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='d8c0b8a6f98e68e6ab46705d0f09a1270c2ff516368e7e9e43efa61ab90024b2',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_9c10f9a98f2ec332e078(uisemtest_runtime):
    'Business summary: Observation actor_a GET /api/profiles/uisemtest_actor_b; basic constraint P21 requires observation $.profile.following (boolean) to have JSON type boolean; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0007\nCanonical relation core: 92400e5a377b34532e82163d8a68b6f6d6d2c700fee25dd746fc79b1d9d66b7b\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0007
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/api/profiles/uisemtest_actor_b',
      'request_ref': 'r20260901-190427-8ca5:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0007-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'boolean',
                    'family': 'P21',
                    'target': {'path': '$.profile.following',
                               'role': 'observation',
                               'value_type': 'boolean'}}},
     {'assertion_id': 'v2-candidate-0007-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0007-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'boolean',
                    'response_ref': 'observation',
                    'target_path': '$.profile.following',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-9c10f9a98f2ec332e078',
        candidate_id='v2-candidate-0007',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='c801bb0d3b61872107d737d197c0046709be3c2fbf498a03e7ed16a15869c096',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_b9d42a9529f552d0b669(uisemtest_runtime):
    'Business summary: Producer actor_a POST /api/profiles/uisemtest_actor_b/follow; observer actor_a GET /api/profiles/uisemtest_actor_b; business predicate P01 requires after $.profile.following (boolean) to be true/present.\nCandidate ID: v2-candidate-0008\nCanonical relation core: 5b491a1af21084629619d8b496ac735ade4b07f94d03e8238fe4dc4da38783a0\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V1: v2-candidate-0008
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'treatment', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'before_observer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/api/profiles/uisemtest_actor_b',
      'request_ref': 'r20260901-190427-8ca5:request:0'},
     {'kind': 'http',
      'phase': 'producer',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/api/profiles/uisemtest_actor_b/follow',
      'request_ref': 'r20260901-190427-8ca5:request:4'},
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
      'method': 'GET',
      'path': '/api/profiles/uisemtest_actor_b',
      'request_ref': 'r20260901-190427-8ca5:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0008-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'exists',
                    'target': {'path': '$.profile.following',
                               'role': 'after',
                               'value_type': 'boolean'}}},
     {'assertion_id': 'v2-candidate-0008-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0008-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0008-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'boolean',
                    'response_ref': 'after',
                    'target_path': '$.profile.following',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-b9d42a9529f552d0b669',
        candidate_id='v2-candidate-0008',
        protocol_kind='V1',
        normal_runs=1,
        source_test_sha256='62bf162959a76741697628680d69f0669534639abd42f00ddedec7ecdde7ab1f',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])
