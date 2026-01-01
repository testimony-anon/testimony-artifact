"""Generated from a frozen UISemTest M14 suite; do not edit by hand."""

def test_relation_test_64dd7649a7949d44235a(uisemtest_runtime):
    'Business summary: Observation guest GET /api/articles; basic constraint P01 requires field observation $.articles (array) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0001\nCanonical relation core: 9c1f4d707db2df516634c0b050b2f615571e28356c609e010f045f4a5cc3318d\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0001
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['guest']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0001-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.articles', 'role': 'observation', 'value_type': 'array'}}},
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
        test_id='relation-test-64dd7649a7949d44235a',
        candidate_id='v2-candidate-0001',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='7d62b7874b8780364ed6ac02c12fb39c03dddc2a50e4e8dd6b9115c1672e080b',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_f439bab972ea22fb6719(uisemtest_runtime):
    'Business summary: Observation guest GET /api/articles; basic constraint P21 requires observation $.articles (array) to have JSON type array; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0002\nCanonical relation core: 7ea80525265daee3508c6bc960eb2a3a97109055bbd2f0177823768cb4fc96ad\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0002
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['guest']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0002-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'array',
                    'family': 'P21',
                    'target': {'path': '$.articles', 'role': 'observation', 'value_type': 'array'}}},
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
        test_id='relation-test-f439bab972ea22fb6719',
        candidate_id='v2-candidate-0002',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='d0cc8639b9620001dc48a794727a61b9bcd4f76c9c21220ac55762d46e570dcb',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_7f01c037a39afc03e18f(uisemtest_runtime):
    'Business summary: Observation guest GET /api/articles; basic constraint P01 requires field observation $.articlesCount (integer) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0003\nCanonical relation core: bcfc254d775f887fb95d4653f7cb231d48f4577eb5383046157be4e74d3fa9ad\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0003
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['guest']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0003-business-01',
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
     {'assertion_id': 'v2-candidate-0003-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0003-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.articlesCount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-7f01c037a39afc03e18f',
        candidate_id='v2-candidate-0003',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='df0576819021586be960bce6a3b41aa6cb81fbc65ecec4ee30c0596a9e7be142',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_8335b2e9197fd57ec2cf(uisemtest_runtime):
    'Business summary: Observation guest GET /api/articles; basic constraint P21 requires observation $.articlesCount (integer) to have JSON type integer; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0004\nCanonical relation core: fe4fab150e4d59da1f0989913c4347ef493bcefd301beeabaf9b6e2e71e89693\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0004
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['guest']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:0'}]
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
        test_id='relation-test-8335b2e9197fd57ec2cf',
        candidate_id='v2-candidate-0004',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='f2db99857b5ab5a05f5f0759ef5f48c5102376bff75fe2cf07737598a726a4f4',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_3867ed1450981b59aba4(uisemtest_runtime):
    "Business summary: Observation guest GET /api/articles; basic constraint P11 requires count(observation $.articles (array)) <= this request's query.limit; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0005\nCanonical relation core: 12771e7a695c5e2f56d3c3b8d96ad1bfa104223742a96a9e27fdf390e74265b3\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[4].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0005
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['guest']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0005-business-01',
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
        test_id='relation-test-3867ed1450981b59aba4',
        candidate_id='v2-candidate-0005',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='9ee63941abe0e83df961b8774d3e5e21c0926c7ae1adce907c1dc8bf1bf56866',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_a9589ab37b05b270b762(uisemtest_runtime):
    'Business summary: Observation guest GET /api/tags; basic constraint P01 requires field observation $.tags (array) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0006\nCanonical relation core: c9b9b39e21accf282495a24a810435a5eea40e0cbc8beeba9c86396acc4f2912\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[5].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[4].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[5].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0006
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['guest']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:0'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:1'}]
    assertions = [{'assertion_id': 'v2-candidate-0006-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.tags', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0006-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0006-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tags',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-a9589ab37b05b270b762',
        candidate_id='v2-candidate-0006',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='0fd553da3d5a0bdb31290e315f3a079f433366d00ccd6e2f1eaac9db6804486a',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_6eca580e700c2fd92862(uisemtest_runtime):
    'Business summary: Observation guest GET /api/tags; basic constraint P21 requires observation $.tags (array) to have JSON type array; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0007\nCanonical relation core: e12d1f34c67f17d204aafe64e443b462bfd6f6f6ed154aac8000da1cf949c98a\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[6].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[5].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[4].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0007
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['guest']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:0'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:1'}]
    assertions = [{'assertion_id': 'v2-candidate-0007-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'array',
                    'family': 'P21',
                    'target': {'path': '$.tags', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0007-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0007-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tags',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-6eca580e700c2fd92862',
        candidate_id='v2-candidate-0007',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='281b9a22c345812122bb5e8b067eb5e6aab7595f5e7ad451e347a743d9ab7bdb',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_2ce27af948c04b4aaa52(uisemtest_runtime):
    "Business summary: Observation guest GET /api/articles; basic constraint P11 requires count(observation $.articles (array)) <= this request's query.limit; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0008\nCanonical relation core: 12771e7a695c5e2f56d3c3b8d96ad1bfa104223742a96a9e27fdf390e74265b3\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[4].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0008
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['guest']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:1'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:4'}]
    assertions = [{'assertion_id': 'v2-candidate-0008-business-01',
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
     {'assertion_id': 'v2-candidate-0008-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0008-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.articles',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-2ce27af948c04b4aaa52',
        candidate_id='v2-candidate-0008',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='06e95f7219fcf8bdf8a9a90b64f6273bd96b295861b80f4aff6e0cf4149df2a7',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_5debc440926ed7bca244(uisemtest_runtime):
    "Business summary: Observation guest GET /api/articles; business relation P19 requires observation $.articlesCount (integer) = count(observation $.articles (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0009\nCanonical relation core: 7a713940260a9a7496fb46b17eee63a4256089a4809389fcc0b354fa7b9edaf1\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[4].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0009
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['guest']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:1'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:4'}]
    assertions = [{'assertion_id': 'v2-candidate-0009-business-01',
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
                    'units': {'evidence_refs': ['r20260901-185856-ed8a:request:4'],
                              'rationale': 'count of array members is proposed to be measured in '
                                           'items, the only summary unit for a plain count',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0009-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0009-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.articlesCount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-5debc440926ed7bca244',
        candidate_id='v2-candidate-0009',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='b524c176926e3f0e993541874c2ad758b24af5e9d6de8b01450050c1b5805ea4',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_b673a5e4b601bfaca364(uisemtest_runtime):
    "Business summary: Observation guest GET /api/articles; business relation P19 requires observation $.articlesCount (integer) = count(observation $.articles (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0010\nCanonical relation core: 7a713940260a9a7496fb46b17eee63a4256089a4809389fcc0b354fa7b9edaf1\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0010
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['guest']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:1'},
     {'kind': 'http',
      'phase': 'setup[2]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:4'},
     {'kind': 'http',
      'phase': 'setup[3]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:5'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:8'}]
    assertions = [{'assertion_id': 'v2-candidate-0010-business-01',
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
                    'units': {'evidence_refs': ['r20260901-185856-ed8a:request:8'],
                              'rationale': 'The observed response carries one array member and one '
                                           'integer summary member; the summary counts the array '
                                           'members.',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0010-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0010-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.articlesCount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-b673a5e4b601bfaca364',
        candidate_id='v2-candidate-0010',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='0ddf69558ec534a1024d35c53841430d56bb57cdd429b00839eef2ae4cd55700',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_3b184e22b84e662473b7(uisemtest_runtime):
    "Business summary: Observation guest GET /api/articles; basic constraint P11 requires count(observation $.articles (array)) <= this request's query.limit; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0011\nCanonical relation core: 12771e7a695c5e2f56d3c3b8d96ad1bfa104223742a96a9e27fdf390e74265b3\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0011
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['guest']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:1'},
     {'kind': 'http',
      'phase': 'setup[2]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:4'},
     {'kind': 'http',
      'phase': 'setup[3]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:5'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:8'}]
    assertions = [{'assertion_id': 'v2-candidate-0011-business-01',
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
     {'assertion_id': 'v2-candidate-0011-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0011-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.articles',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-3b184e22b84e662473b7',
        candidate_id='v2-candidate-0011',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='ecb3c8357fd37bbe4cc2ee60923781ffbbb37cbf2adf5cc4375621381c1d4d57',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_baf9dfbff41e40e3bc77(uisemtest_runtime):
    'Business summary: Observation guest GET /api/articles; basic constraint P01 requires field observation $.articles (array) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0012\nCanonical relation core: 9c1f4d707db2df516634c0b050b2f615571e28356c609e010f045f4a5cc3318d\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0012
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['guest']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:1'},
     {'kind': 'http',
      'phase': 'setup[2]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:4'},
     {'kind': 'http',
      'phase': 'setup[3]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:5'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:8'}]
    assertions = [{'assertion_id': 'v2-candidate-0012-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.articles', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0012-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0012-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.articles',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-baf9dfbff41e40e3bc77',
        candidate_id='v2-candidate-0012',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='ee873158a806883e262e3d2568b6c74c4c865c2e094cc16046bd297d39e5d378',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_7c058ba78930f2520fa2(uisemtest_runtime):
    'Business summary: Observation guest GET /api/articles; basic constraint P01 requires field observation $.articlesCount (integer) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0013\nCanonical relation core: bcfc254d775f887fb95d4653f7cb231d48f4577eb5383046157be4e74d3fa9ad\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0013
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['guest']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:1'},
     {'kind': 'http',
      'phase': 'setup[2]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:4'},
     {'kind': 'http',
      'phase': 'setup[3]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:5'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:8'}]
    assertions = [{'assertion_id': 'v2-candidate-0013-business-01',
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
     {'assertion_id': 'v2-candidate-0013-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0013-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.articlesCount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-7c058ba78930f2520fa2',
        candidate_id='v2-candidate-0013',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='dd203562423ffc17e73dd2ae07d3d0622abbbeccf28c630c88e196c0c0cd5528',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_f3477a1ba2cdfe557e6b(uisemtest_runtime):
    'Business summary: Observation guest GET /api/tags; basic constraint P01 requires field observation $.tags (array) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0014\nCanonical relation core: c9b9b39e21accf282495a24a810435a5eea40e0cbc8beeba9c86396acc4f2912\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[4].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0014
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['guest']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:1'},
     {'kind': 'http',
      'phase': 'setup[2]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:4'},
     {'kind': 'http',
      'phase': 'setup[3]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:5'},
     {'kind': 'http',
      'phase': 'setup[4]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:8'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:9'}]
    assertions = [{'assertion_id': 'v2-candidate-0014-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.tags', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0014-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0014-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tags',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-f3477a1ba2cdfe557e6b',
        candidate_id='v2-candidate-0014',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='3e2824a9ae7552e21b6bd984aec6fe5f1562e03ee26bfeb87bd1f894763a3f6b',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_4b46e8c93daf25f67d7e(uisemtest_runtime):
    "Business summary: Observation guest GET /api/articles; business relation P19 requires observation $.articlesCount (integer) = count(observation $.articles (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0015\nCanonical relation core: 7a713940260a9a7496fb46b17eee63a4256089a4809389fcc0b354fa7b9edaf1\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0015
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['guest']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:0'}]
    assertions = [{'assertion_id': 'v2-candidate-0015-business-01',
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
                    'units': {'evidence_refs': ['r20260901-185856-ed8a:request:0'],
                              'rationale': 'Proposed unit for the counted array members and the '
                                           'summary field in the visible articles response; the '
                                           'business rule itself is a hypothesis and need not already '
                                           'hold.',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0015-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0015-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.articlesCount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-4b46e8c93daf25f67d7e',
        candidate_id='v2-candidate-0015',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='438789f5df0163bab1a8a84dea320c3788754d730e26de0291258bc803a9ccd9',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_51c8d095cdf308d0f5b3(uisemtest_runtime):
    'Business summary: Observation guest GET /api/articles; basic constraint P21 requires observation $.articles (array) to have JSON type array; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0016\nCanonical relation core: 7ea80525265daee3508c6bc960eb2a3a97109055bbd2f0177823768cb4fc96ad\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[6].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0016
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['guest']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:1'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:4'}]
    assertions = [{'assertion_id': 'v2-candidate-0016-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'array',
                    'family': 'P21',
                    'target': {'path': '$.articles', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0016-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0016-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.articles',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-51c8d095cdf308d0f5b3',
        candidate_id='v2-candidate-0016',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='ac141964a02eb2720e15edbf2b90a3edc82747fa6cb3e75ef105eaca9e8b421b',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_d344c40c3d29f9a11b62(uisemtest_runtime):
    'Business summary: Observation guest GET /api/articles; basic constraint P21 requires observation $.articlesCount (integer) to have JSON type integer; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0017\nCanonical relation core: fe4fab150e4d59da1f0989913c4347ef493bcefd301beeabaf9b6e2e71e89693\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[5].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0017
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['guest']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:1'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:4'}]
    assertions = [{'assertion_id': 'v2-candidate-0017-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'integer',
                    'family': 'P21',
                    'target': {'path': '$.articlesCount',
                               'role': 'observation',
                               'value_type': 'integer'}}},
     {'assertion_id': 'v2-candidate-0017-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0017-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.articlesCount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-d344c40c3d29f9a11b62',
        candidate_id='v2-candidate-0017',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='f0ef21aa5d1d76a18d993b60f9f740f705723d8566ca2476f9a9b971c639a148',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_94fe62482a79a906ecba(uisemtest_runtime):
    'Business summary: Observation guest GET /api/tags; basic constraint P21 requires observation $.tags (array) to have JSON type array; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0018\nCanonical relation core: e12d1f34c67f17d204aafe64e443b462bfd6f6f6ed154aac8000da1cf949c98a\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[7].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0018
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['guest']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:1'},
     {'kind': 'http',
      'phase': 'setup[2]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:4'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:5'}]
    assertions = [{'assertion_id': 'v2-candidate-0018-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'array',
                    'family': 'P21',
                    'target': {'path': '$.tags', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0018-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0018-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tags',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-94fe62482a79a906ecba',
        candidate_id='v2-candidate-0018',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='83fcc50fb44973f240594a328e04a9b6350a2463faeb6a0542f09d1996f981ab',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_dba9aefc625fba435b58(uisemtest_runtime):
    'Business summary: Observation guest GET /api/articles; basic constraint P01 requires field observation $.articles (array) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0019\nCanonical relation core: 9c1f4d707db2df516634c0b050b2f615571e28356c609e010f045f4a5cc3318d\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0019
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['guest']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:1'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:4'}]
    assertions = [{'assertion_id': 'v2-candidate-0019-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.articles', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0019-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0019-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.articles',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-dba9aefc625fba435b58',
        candidate_id='v2-candidate-0019',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='53a78e2a79a4f767ee4d034a143dab485dc1e6c79f0e0fc537e69260eee4dbe2',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_03ce04d1a75187da7a9a(uisemtest_runtime):
    'Business summary: Observation guest GET /api/articles; basic constraint P01 requires field observation $.articlesCount (integer) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0020\nCanonical relation core: bcfc254d775f887fb95d4653f7cb231d48f4577eb5383046157be4e74d3fa9ad\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0020
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['guest']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:1'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:4'}]
    assertions = [{'assertion_id': 'v2-candidate-0020-business-01',
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
     {'assertion_id': 'v2-candidate-0020-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0020-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.articlesCount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-03ce04d1a75187da7a9a',
        candidate_id='v2-candidate-0020',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='6255fac842c271d481098feea0ac4d2ee4b5b50ddb2f68324c4d9d04827dbc7a',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_55c19ab44bddacdbc03e(uisemtest_runtime):
    'Business summary: Observation guest GET /api/tags; basic constraint P01 requires field observation $.tags (array) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0021\nCanonical relation core: c9b9b39e21accf282495a24a810435a5eea40e0cbc8beeba9c86396acc4f2912\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0021
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['guest']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:1'},
     {'kind': 'http',
      'phase': 'setup[2]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:4'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:5'}]
    assertions = [{'assertion_id': 'v2-candidate-0021-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.tags', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0021-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0021-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tags',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-55c19ab44bddacdbc03e',
        candidate_id='v2-candidate-0021',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='9c2c62985170db70b35a8ad173a94cd9e531126e10bc4fa661c62d7ad7aba6f1',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_1def8bb84b5d87d74a66(uisemtest_runtime):
    "Business summary: Observation guest GET /api/articles; business relation P19 requires observation $.articlesCount (integer) = count(observation $.articles (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0022\nCanonical relation core: 7a713940260a9a7496fb46b17eee63a4256089a4809389fcc0b354fa7b9edaf1\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0022
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['guest']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:0'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:1'},
     {'kind': 'http',
      'phase': 'setup[2]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:4'},
     {'kind': 'http',
      'phase': 'setup[3]',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/tags',
      'request_ref': 'r20260901-185856-ed8a:request:5'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'guest',
      'method': 'GET',
      'path': '/api/articles',
      'request_ref': 'r20260901-185856-ed8a:request:8'}]
    assertions = [{'assertion_id': 'v2-candidate-0022-business-01',
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
                    'units': {'evidence_refs': ['r20260901-185856-ed8a:request:8'],
                              'rationale': 'Proposed rule grounded in the visible response shape: the '
                                           'summary integer counts the same array members. Not '
                                           'prevalidated; the recorded values need not already satisfy '
                                           'it.',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0022-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0022-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.articlesCount',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-1def8bb84b5d87d74a66',
        candidate_id='v2-candidate-0022',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='9f59cd06cf86b5515ca914de497e98857decbce706bb3e63834a5d26a69dc765',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])
