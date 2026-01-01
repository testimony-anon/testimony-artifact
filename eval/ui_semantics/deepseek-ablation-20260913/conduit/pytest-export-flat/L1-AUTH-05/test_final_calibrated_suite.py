"""Generated from a frozen UISemTest M14 suite; do not edit by hand."""

def test_relation_test_579d3e899fdd360d3236(uisemtest_runtime):
    "Business summary: Observation actor_a GET /api/articles; basic constraint P11 requires count(observation $.articles (array)) <= this request's query.limit; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0001\nCanonical relation core: 12771e7a695c5e2f56d3c3b8d96ad1bfa104223742a96a9e27fdf390e74265b3\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[4].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0001
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185839-bbbd:request:1'}]
    assertions = [{'assertion_id': 'v2-candidate-0001-business-01',
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
     {'assertion_id': 'v2-candidate-0001-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0001-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.articles',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-579d3e899fdd360d3236',
        candidate_id='v2-candidate-0001',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='d5ce5807ddbbb4d8a6e50bb01dca4177e11aa763007506c1b4f93f34ac7abb99',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_524d257d46aa8b3cab76(uisemtest_runtime):
    "Business summary: Observation actor_a GET /api/articles; business relation P19 requires observation $.articlesCount (integer) = count(observation $.articles (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0002\nCanonical relation core: 7a713940260a9a7496fb46b17eee63a4256089a4809389fcc0b354fa7b9edaf1\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[5].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0002
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185839-bbbd:request:1'}]
    assertions = [{'assertion_id': 'v2-candidate-0002-business-01',
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
                    'units': {'evidence_refs': ['r20260901-185839-bbbd:request:1'],
                              'rationale': 'Proposed unit for a member count over the same actual '
                                           'response array; the unit is declared as a hypothesis from '
                                           'the visible response shape, not inferred as a proven '
                                           'server guarantee.',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0002-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0002-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.articlesCount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-524d257d46aa8b3cab76',
        candidate_id='v2-candidate-0002',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='57b706150c32143aa8440f04b749d8088100b38f9bbd9ffa5e60e2b15d4d876b',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_6c4e5b03809da333b143(uisemtest_runtime):
    'Business summary: Observation actor_a GET /api/articles; basic constraint P21 requires observation $.articles (array) to have JSON type array; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0003\nCanonical relation core: 7ea80525265daee3508c6bc960eb2a3a97109055bbd2f0177823768cb4fc96ad\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0003
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185839-bbbd:request:1'}]
    assertions = [{'assertion_id': 'v2-candidate-0003-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'array',
                    'family': 'P21',
                    'target': {'path': '$.articles', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0003-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0003-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.articles',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-6c4e5b03809da333b143',
        candidate_id='v2-candidate-0003',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='65f2e06327ea1bf0b93490386d47ca83e9491012b4c7760ed524a5a424fea5c6',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_fce95b6478ba30ce4925(uisemtest_runtime):
    'Business summary: Observation actor_a GET /api/articles; basic constraint P21 requires observation $.articlesCount (integer) to have JSON type integer; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0004\nCanonical relation core: fe4fab150e4d59da1f0989913c4347ef493bcefd301beeabaf9b6e2e71e89693\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0004
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185839-bbbd:request:1'}]
    assertions = [{'assertion_id': 'v2-candidate-0004-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'integer',
                    'family': 'P21',
                    'target': {'path': '$.articlesCount',
                               'role': 'observation',
                               'value_type': 'integer'}}},
     {'assertion_id': 'v2-candidate-0004-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0004-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.articlesCount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-fce95b6478ba30ce4925',
        candidate_id='v2-candidate-0004',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='bb758dd93874e2892d586ffa16973de18127385a0efc4af089d8a7b52b0ad05b',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_11519cfe79447a2b6fab(uisemtest_runtime):
    'Business summary: Observation actor_a GET /api/articles; basic constraint P01 requires field observation $.articles (array) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0005\nCanonical relation core: 9c1f4d707db2df516634c0b050b2f615571e28356c609e010f045f4a5cc3318d\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0005
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185839-bbbd:request:1'}]
    assertions = [{'assertion_id': 'v2-candidate-0005-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.articles', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0005-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0005-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.articles',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-11519cfe79447a2b6fab',
        candidate_id='v2-candidate-0005',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='967d9b49509353734a72d243f52e381a56f33dd08d6db3ddb7cd390ba7df9cae',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_32186bf1f96eb2485272(uisemtest_runtime):
    'Business summary: Observation actor_a GET /api/articles; basic constraint P01 requires field observation $.articlesCount (integer) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0006\nCanonical relation core: bcfc254d775f887fb95d4653f7cb231d48f4577eb5383046157be4e74d3fa9ad\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0006
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185839-bbbd:request:1'}]
    assertions = [{'assertion_id': 'v2-candidate-0006-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.articlesCount',
                               'role': 'observation',
                               'value_type': 'integer'}}},
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
        test_id='relation-test-32186bf1f96eb2485272',
        candidate_id='v2-candidate-0006',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='29374ede9156750138c3c3e90316b76c0c395cf6d3297e6e78edf5476498a36d',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_2a74d47191baadcffa1c(uisemtest_runtime):
    "Business summary: Observation actor_a GET /api/articles; business relation P19 requires observation $.articlesCount (integer) = count(observation $.articles (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0007\nCanonical relation core: 7a713940260a9a7496fb46b17eee63a4256089a4809389fcc0b354fa7b9edaf1\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0007
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185839-bbbd:request:1'}]
    assertions = [{'assertion_id': 'v2-candidate-0007-business-01',
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
                    'units': {'evidence_refs': ['r20260901-185839-bbbd:request:1'],
                              'rationale': 'Count output is a number of collection members, so the '
                                           'only declared unit is items for the output summary.',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0007-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0007-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.articlesCount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-2a74d47191baadcffa1c',
        candidate_id='v2-candidate-0007',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='e9e78aad5875d846c7149148af1dbfd67bd4064fef79377fd1e3d33aea2338f4',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])
