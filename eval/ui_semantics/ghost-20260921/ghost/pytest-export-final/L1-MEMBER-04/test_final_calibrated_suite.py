"""Generated from a frozen UISemTest M14 suite; do not edit by hand."""

def test_relation_test_c6e8ea29d701ac48a3e6(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/labels/; business relation P19 requires observation $.meta.pagination.total (integer) = count(observation $.labels (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0001\nCanonical relation core: 3d24bef0bdd02dfa8cef73b70c242960eb1b2ca709a116c011e7f10c3e0fbef8\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0001
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170651-22bb:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0001-business-01',
      'class': 'business',
      'predicate_type': 'P19',
      'predicate': {'collection': {'path': '$.labels', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P19',
                    'numeric_mode': 'exact',
                    'operator': 'count',
                    'output': {'path': '$.meta.pagination.total',
                               'role': 'observation',
                               'value_type': 'integer'},
                    'scope': 'actual_response',
                    'units': {'evidence_refs': ['r20260920-170651-22bb:request:25'],
                              'rationale': 'proposed unit of the counted page members and the response '
                                           'total field; not prevalidated',
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
                    'target_path': '$.meta.pagination.total',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-c6e8ea29d701ac48a3e6',
        candidate_id='v2-candidate-0001',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='643b316f37ba4f41c95e8ca39e7eeaf24d31855afadff908353b4bd2dfb6733c',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_f0a7e3bbfdaf267ddcbc(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/tiers/; business relation P19 requires observation $.meta.pagination.total (integer) = count(observation $.tiers (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0002\nCanonical relation core: c52c713b22517e1d232e8cb9ad25f7eee5efd32203a7a88ceb1a159384afff57\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0002
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170651-22bb:request:25'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/tiers/',
      'request_ref': 'r20260920-170651-22bb:request:26'}]
    assertions = [{'assertion_id': 'v2-candidate-0002-business-01',
      'class': 'business',
      'predicate_type': 'P19',
      'predicate': {'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P19',
                    'numeric_mode': 'exact',
                    'operator': 'count',
                    'output': {'path': '$.meta.pagination.total',
                               'role': 'observation',
                               'value_type': 'integer'},
                    'scope': 'actual_response',
                    'units': {'evidence_refs': ['r20260920-170651-22bb:request:26'],
                              'rationale': 'proposed unit of the counted page members and the response '
                                           'total field; not prevalidated',
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
                    'target_path': '$.meta.pagination.total',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-f0a7e3bbfdaf267ddcbc',
        candidate_id='v2-candidate-0002',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='986d94233c256ee6ac95f1f6c0a5ffbef02655d9e9c53404eaaaada3b41fa068',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_3fbda882e6baede6f315(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; business relation P19 requires observation $.meta.pagination.total (integer) = count(observation $.newsletters (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0003\nCanonical relation core: 92a329fa52b780bf4efd355da67fa8efb017854c104da25308361b43a6eb33f7\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0003
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170651-22bb:request:25'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/tiers/',
      'request_ref': 'r20260920-170651-22bb:request:26'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/newsletters/',
      'request_ref': 'r20260920-170651-22bb:request:27'}]
    assertions = [{'assertion_id': 'v2-candidate-0003-business-01',
      'class': 'business',
      'predicate_type': 'P19',
      'predicate': {'collection': {'path': '$.newsletters',
                                   'role': 'observation',
                                   'value_type': 'array'},
                    'family': 'P19',
                    'numeric_mode': 'exact',
                    'operator': 'count',
                    'output': {'path': '$.meta.pagination.total',
                               'role': 'observation',
                               'value_type': 'integer'},
                    'scope': 'actual_response',
                    'units': {'evidence_refs': ['r20260920-170651-22bb:request:27'],
                              'rationale': 'proposed unit of the counted page members and the response '
                                           'total field; not prevalidated',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0003-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0003-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.total',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-3fbda882e6baede6f315',
        candidate_id='v2-candidate-0003',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='04e7678a20996a6e98e45c6e3f8c954bf7627b3e7d8b3bd7b48396ed9eea7427',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_0d6152cd9b1f64345161(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P11 requires count(observation $.labels (array)) <= this request's query.limit; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0004\nCanonical relation core: 9d8a5e79a202b8e7dbaf99e00b10d262ded82ae7be7d74cd4403c68f4aa4312a\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0004
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170651-22bb:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0004-business-01',
      'class': 'business',
      'predicate_type': 'P11',
      'predicate': {'collection': {'path': '$.labels', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P11',
                    'operator': 'le',
                    'right': {'ref': {'location': 'query',
                                      'path': '$.limit',
                                      'role': 'observation_request',
                                      'value_type': 'integer'},
                              'source': 'request'}}},
     {'assertion_id': 'v2-candidate-0004-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0004-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-0d6152cd9b1f64345161',
        candidate_id='v2-candidate-0004',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='87e49d7a8c1c8bca6958385e02792c458ebd6ed1105105dc2bf050165ba5cee1',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_8db0b0d02c84156d107e(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P11 requires count(observation $.labels (array); unit=items) eq observation $.meta.pagination.total (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0005\nCanonical relation core: 8c97b92465c1719d1d3af0e98198632e2bafed11a9f79aa79840d4e9e6349d68\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0005
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170651-22bb:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0005-business-01',
      'class': 'business',
      'predicate_type': 'P11',
      'predicate': {'family': 'P11',
                    'operator': 'eq',
                    'projection': 'count',
                    'right': {'ref': {'path': '$.meta.pagination.total',
                                      'role': 'observation',
                                      'value_type': 'integer'},
                              'source': 'role'},
                    'target': {'path': '$.labels', 'role': 'observation', 'value_type': 'array'},
                    'unit': 'items'}},
     {'assertion_id': 'v2-candidate-0005-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0005-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-8db0b0d02c84156d107e',
        candidate_id='v2-candidate-0005',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='9455e2ae522cf5931d101add3d503084982ce7b737299bde67146a1090ee7c69',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_c4508364d78c399afb88(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint P11 requires count(observation $.tiers (array); unit=items) eq observation $.meta.pagination.total (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0006\nCanonical relation core: 1dcab7b65d39bc3ce4c48e9df2a1f9e6f4a3504ff29e743ebbc41a54c1ec41ee\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0006
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170651-22bb:request:25'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/tiers/',
      'request_ref': 'r20260920-170651-22bb:request:26'}]
    assertions = [{'assertion_id': 'v2-candidate-0006-business-01',
      'class': 'business',
      'predicate_type': 'P11',
      'predicate': {'family': 'P11',
                    'operator': 'eq',
                    'projection': 'count',
                    'right': {'ref': {'path': '$.meta.pagination.total',
                                      'role': 'observation',
                                      'value_type': 'integer'},
                              'source': 'role'},
                    'target': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
                    'unit': 'items'}},
     {'assertion_id': 'v2-candidate-0006-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0006-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-c4508364d78c399afb88',
        candidate_id='v2-candidate-0006',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='5e60e2a87be89235e2774d67f2de2f83af57d51bdbe91dab48eee9619cb848f3',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_5322d8ad8ef9cf2f34aa(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint P11 requires count(observation $.newsletters (array); unit=items) eq observation $.meta.pagination.total (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0007\nCanonical relation core: f4f2658bfa1c3cdbcfbffaefa18b56a10cc4dde35ad76eff01ec2ad86351f0e4\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0007
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170651-22bb:request:25'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/tiers/',
      'request_ref': 'r20260920-170651-22bb:request:26'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/newsletters/',
      'request_ref': 'r20260920-170651-22bb:request:27'}]
    assertions = [{'assertion_id': 'v2-candidate-0007-business-01',
      'class': 'business',
      'predicate_type': 'P11',
      'predicate': {'family': 'P11',
                    'operator': 'eq',
                    'projection': 'count',
                    'right': {'ref': {'path': '$.meta.pagination.total',
                                      'role': 'observation',
                                      'value_type': 'integer'},
                              'source': 'role'},
                    'target': {'path': '$.newsletters', 'role': 'observation', 'value_type': 'array'},
                    'unit': 'items'}},
     {'assertion_id': 'v2-candidate-0007-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0007-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.newsletters',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-5322d8ad8ef9cf2f34aa',
        candidate_id='v2-candidate-0007',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='8bac50a082eeca526341854a984a0f62e85433185560bb350373cbeefd68241f',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_3341f700c9a6fcfc7fa0(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint P15 requires observation $.tiers (array) (actual_response) to have unique members by strict-tuple identity [$.id]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0008\nCanonical relation core: f79e87788d14e9c2596cd65cb6665c9c43a813494db312f781ad92db57c90f0e\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[4].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0008
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170651-22bb:request:25'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/tiers/',
      'request_ref': 'r20260920-170651-22bb:request:26'}]
    assertions = [{'assertion_id': 'v2-candidate-0008-business-01',
      'class': 'business',
      'predicate_type': 'P15',
      'predicate': {'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P15',
                    'identity': {'paths': ['$.id'], 'semantics': 'strict-tuple'},
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
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-3341f700c9a6fcfc7fa0',
        candidate_id='v2-candidate-0008',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='9898aaba11925c552f2af239c8d29a9ea56d7e5a2e1c4a2ab43f4db6a4feffed',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_88efb81fea0248cc891d(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint P15 requires observation $.newsletters (array) (actual_response) to have unique members by strict-tuple identity [$.id]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0009\nCanonical relation core: 342eb75d817266ce91f0115a8a5985a75a11f4d41e49f158e791fcecb116dcfe\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[5].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0009
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170651-22bb:request:25'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/tiers/',
      'request_ref': 'r20260920-170651-22bb:request:26'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/newsletters/',
      'request_ref': 'r20260920-170651-22bb:request:27'}]
    assertions = [{'assertion_id': 'v2-candidate-0009-business-01',
      'class': 'business',
      'predicate_type': 'P15',
      'predicate': {'collection': {'path': '$.newsletters',
                                   'role': 'observation',
                                   'value_type': 'array'},
                    'family': 'P15',
                    'identity': {'paths': ['$.id'], 'semantics': 'strict-tuple'},
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
                    'target_path': '$.newsletters',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-88efb81fea0248cc891d',
        candidate_id='v2-candidate-0009',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='2d862ad0d89faa321c485b39d1c4cf9ecfec5504a63be3e835f188c0b6489fbf',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_e4cdfbebd575068b71eb(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint For every member of observation $.tiers (array) in actual_response: P02 requires item $.type (string) to strictly equal frozen hypothesis 'paid' (string); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0010\nCanonical relation core: 0378fcb8e31ca88af9232d8d583333f161c1814c0f4791d63018a62953d09785\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[6].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0010
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170651-22bb:request:25'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/tiers/',
      'request_ref': 'r20260920-170651-22bb:request:26'}]
    assertions = [{'assertion_id': 'v2-candidate-0010-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'family': 'P02',
                             'left': {'path': '$.type', 'role': 'item', 'value_type': 'string'},
                             'operator': 'eq',
                             'right': {'evidence_refs': ['r20260920-170651-22bb:request:26'],
                                       'rationale': 'The visible tier query filter text contains '
                                                    'type:paid; the proposed rule is that every '
                                                    'returned tier member carries that type value.',
                                       'source': 'hypothesis',
                                       'value': 'paid',
                                       'value_type': 'string'}},
                    'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0010-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0010-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-e4cdfbebd575068b71eb',
        candidate_id='v2-candidate-0010',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='4a011e252bb33210bcf94ed3dec23466e09644ca55195d6857abf51d6a84861a',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_7816f9ebea1be71e8e79(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint For every member of observation $.tiers (array) in actual_response: P02 requires item $.active (boolean) to strictly equal frozen hypothesis True (boolean); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0011\nCanonical relation core: 272ce11d8d4ce88b1d57b0bb00d48707e337854461c314eb72b0178222752762\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[7].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0011
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170651-22bb:request:25'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/tiers/',
      'request_ref': 'r20260920-170651-22bb:request:26'}]
    assertions = [{'assertion_id': 'v2-candidate-0011-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'family': 'P02',
                             'left': {'path': '$.active', 'role': 'item', 'value_type': 'boolean'},
                             'operator': 'eq',
                             'right': {'evidence_refs': ['r20260920-170651-22bb:request:26'],
                                       'rationale': 'The visible tier query filter text contains '
                                                    'active:true; the proposed rule is that every '
                                                    'returned tier member carries that boolean active '
                                                    'value.',
                                       'source': 'hypothesis',
                                       'value': True,
                                       'value_type': 'boolean'}},
                    'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
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
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-7816f9ebea1be71e8e79',
        candidate_id='v2-candidate-0011',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='976584c8c9c90af323f8d92e3260306976690041ce61331f9b332bd41e918136',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_27e7892207d6eebe964f(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint For every member of observation $.newsletters (array) in actual_response: P02 requires item $.status (string) to strictly equal frozen hypothesis 'active' (string); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0012\nCanonical relation core: 9fc9db8e57085803e8fd2bda702a98b84601a37b14b9b0ca2205e455aafa0f7b\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[8].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0012
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170651-22bb:request:25'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/tiers/',
      'request_ref': 'r20260920-170651-22bb:request:26'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/newsletters/',
      'request_ref': 'r20260920-170651-22bb:request:27'}]
    assertions = [{'assertion_id': 'v2-candidate-0012-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'family': 'P02',
                             'left': {'path': '$.status', 'role': 'item', 'value_type': 'string'},
                             'operator': 'eq',
                             'right': {'evidence_refs': ['r20260920-170651-22bb:request:27'],
                                       'rationale': 'The visible newsletter query filter text is '
                                                    'status:active; the proposed rule is that every '
                                                    'returned newsletter member carries that status '
                                                    'value.',
                                       'source': 'hypothesis',
                                       'value': 'active',
                                       'value_type': 'string'}},
                    'collection': {'path': '$.newsletters',
                                   'role': 'observation',
                                   'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0012-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0012-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.newsletters',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-27e7892207d6eebe964f',
        candidate_id='v2-candidate-0012',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='623587d08e02ebfa1cb7483548e31eec4d2c46e6110c71750846fd92f657d480',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])
