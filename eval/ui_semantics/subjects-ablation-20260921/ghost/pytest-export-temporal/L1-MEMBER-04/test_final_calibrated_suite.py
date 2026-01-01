"""Generated from a frozen UISemTest M14 suite; do not edit by hand."""

def test_relation_test_9d2ffb8f0a83de6526dd(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P11 requires count(observation $.labels (array)) <= this request's query.limit; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0001\nCanonical relation core: 9d8a5e79a202b8e7dbaf99e00b10d262ded82ae7be7d74cd4403c68f4aa4312a\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0004/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
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
      'predicate_type': 'P11',
      'predicate': {'collection': {'path': '$.labels', 'role': 'observation', 'value_type': 'array'},
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
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-9d2ffb8f0a83de6526dd',
        candidate_id='v2-candidate-0001',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='fa2f1035c8dd86763663dee31c4032304732ed296db0861395d5531f157c0c24',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_5427abc34de440ba856c(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/labels/; business relation P19 requires observation $.meta.pagination.total (integer) = count(observation $.labels (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0002\nCanonical relation core: 3d24bef0bdd02dfa8cef73b70c242960eb1b2ca709a116c011e7f10c3e0fbef8\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0004/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0002
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170651-22bb:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0002-business-01',
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
                              'rationale': 'count of the returned array is expressed in items; the '
                                           'pagination total is proposed to be that same item count in '
                                           'the same response',
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
        test_id='relation-test-5427abc34de440ba856c',
        candidate_id='v2-candidate-0002',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='0fb12208626b5987d066c500ee26e6cf7986b6747812a0eadb25c074ee091710',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_2fa6f0b5a8d982695267(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/tiers/; business relation P19 requires observation $.meta.pagination.total (integer) = count(observation $.tiers (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0003\nCanonical relation core: c52c713b22517e1d232e8cb9ad25f7eee5efd32203a7a88ceb1a159384afff57\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0004/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[4].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0003
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
    assertions = [{'assertion_id': 'v2-candidate-0003-business-01',
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
                              'rationale': 'count of the returned tiers array is expressed in items, '
                                           'proposed equal to the pagination total of the same '
                                           'response',
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
        test_id='relation-test-2fa6f0b5a8d982695267',
        candidate_id='v2-candidate-0003',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='0c078d2155af1088eb09924ba9a754b84ed09f7c7c37924c31c718cb15e1fe62',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_86828518569b605724ff(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; business relation P19 requires observation $.meta.pagination.total (integer) = count(observation $.newsletters (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0004\nCanonical relation core: 92a329fa52b780bf4efd355da67fa8efb017854c104da25308361b43a6eb33f7\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0004/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[6].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0004
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
    assertions = [{'assertion_id': 'v2-candidate-0004-business-01',
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
                              'rationale': 'count of the returned newsletters array is expressed in '
                                           'items, proposed equal to the pagination total of the same '
                                           'response',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0004-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0004-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.total',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-86828518569b605724ff',
        candidate_id='v2-candidate-0004',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='c7c9b9a7be5758372f06e2ad4ea8e10a5fc166313b19ffff462960ff82749185',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_50a00597e06a6744641a(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint P15 requires observation $.tiers (array) (actual_response) to have unique members by strict-tuple identity [$.id]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0005\nCanonical relation core: f79e87788d14e9c2596cd65cb6665c9c43a813494db312f781ad92db57c90f0e\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[4].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0005
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
    assertions = [{'assertion_id': 'v2-candidate-0005-business-01',
      'class': 'business',
      'predicate_type': 'P15',
      'predicate': {'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P15',
                    'identity': {'paths': ['$.id'], 'semantics': 'strict-tuple'},
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
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-50a00597e06a6744641a',
        candidate_id='v2-candidate-0005',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='98cdad8a59536e990b57328fa8f1c57e18388d7e3418b982a61c353b48d039b1',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_fb3d9492a8cd04e399bd(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint P15 requires observation $.newsletters (array) (actual_response) to have unique members by strict-tuple identity [$.id]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0006\nCanonical relation core: 342eb75d817266ce91f0115a8a5985a75a11f4d41e49f158e791fcecb116dcfe\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[5].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0006
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
    assertions = [{'assertion_id': 'v2-candidate-0006-business-01',
      'class': 'business',
      'predicate_type': 'P15',
      'predicate': {'collection': {'path': '$.newsletters',
                                   'role': 'observation',
                                   'value_type': 'array'},
                    'family': 'P15',
                    'identity': {'paths': ['$.id'], 'semantics': 'strict-tuple'},
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0006-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0006-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.newsletters',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-fb3d9492a8cd04e399bd',
        candidate_id='v2-candidate-0006',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='ee2eba1da533c6326e0159845b62a32786da34c8cf51130245ab71214d966273',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_b9262c84b27c47fc053a(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint For every member of observation $.tiers (array) in actual_response: P02 requires item $.active (boolean) to strictly equal frozen hypothesis True (boolean); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0007\nCanonical relation core: 272ce11d8d4ce88b1d57b0bb00d48707e337854461c314eb72b0178222752762\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[6].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0004/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0007
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
    assertions = [{'assertion_id': 'v2-candidate-0007-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'family': 'P02',
                             'left': {'path': '$.active', 'role': 'item', 'value_type': 'boolean'},
                             'operator': 'eq',
                             'right': {'evidence_refs': ['r20260920-170651-22bb:request:26'],
                                       'rationale': 'the recorded selector filter contains the '
                                                    'conjunct active:true; proposed as the per-member '
                                                    'business meaning of that selector, not a proven '
                                                    'server rule',
                                       'source': 'hypothesis',
                                       'value': True,
                                       'value_type': 'boolean'}},
                    'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
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
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-b9262c84b27c47fc053a',
        candidate_id='v2-candidate-0007',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='93f10f3a48a8a04a9eac5e4f754be4237306e2e12a192764cee6281eaf5c26c8',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_9e9c958643b01f3d989f(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint For every member of observation $.tiers (array) in actual_response: P02 requires item $.type (string) to strictly equal frozen hypothesis 'paid' (string); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0008\nCanonical relation core: 0378fcb8e31ca88af9232d8d583333f161c1814c0f4791d63018a62953d09785\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[7].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0004/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
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
      'predicate_type': 'forall',
      'predicate': {'body': {'family': 'P02',
                             'left': {'path': '$.type', 'role': 'item', 'value_type': 'string'},
                             'operator': 'eq',
                             'right': {'evidence_refs': ['r20260920-170651-22bb:request:26'],
                                       'rationale': 'the recorded selector filter contains the '
                                                    'conjunct type:paid; proposed as the per-member '
                                                    'business meaning of that selector, not a proven '
                                                    'server rule',
                                       'source': 'hypothesis',
                                       'value': 'paid',
                                       'value_type': 'string'}},
                    'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
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
        test_id='relation-test-9e9c958643b01f3d989f',
        candidate_id='v2-candidate-0008',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='5bcba55ccff72e5f7f4f230f8cb77c40fbd3980b170ed77a5346a3156f019462',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_bf36e751df3c644a396e(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint For every member of observation $.newsletters (array) in actual_response: P02 requires item $.status (string) to strictly equal frozen hypothesis 'active' (string); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0009\nCanonical relation core: 9fc9db8e57085803e8fd2bda702a98b84601a37b14b9b0ca2205e455aafa0f7b\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[8].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0004/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[5].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
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
      'predicate_type': 'forall',
      'predicate': {'body': {'family': 'P02',
                             'left': {'path': '$.status', 'role': 'item', 'value_type': 'string'},
                             'operator': 'eq',
                             'right': {'evidence_refs': ['r20260920-170651-22bb:request:27'],
                                       'rationale': 'the recorded selector filter is status:active; '
                                                    'proposed as the per-member business meaning of '
                                                    'that selector, not a proven server rule',
                                       'source': 'hypothesis',
                                       'value': 'active',
                                       'value_type': 'string'}},
                    'collection': {'path': '$.newsletters',
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
                    'target_path': '$.newsletters',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-bf36e751df3c644a396e',
        candidate_id='v2-candidate-0009',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='8b8b9acf936cfab966b5bdf0e137c249bd69a2323b0147a13cc28427ee8f17bd',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])
