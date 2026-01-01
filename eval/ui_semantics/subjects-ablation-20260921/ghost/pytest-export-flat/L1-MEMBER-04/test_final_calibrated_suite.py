"""Generated from a frozen UISemTest M14 suite; do not edit by hand."""

def test_relation_test_19b3a546bd2430b6d332(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P11 requires count(observation $.labels (array)) <= this request's query.limit; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0001\nCanonical relation core: 9d8a5e79a202b8e7dbaf99e00b10d262ded82ae7be7d74cd4403c68f4aa4312a\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
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
        test_id='relation-test-19b3a546bd2430b6d332',
        candidate_id='v2-candidate-0001',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='8c9f08b302ce3c248194b0362a94f745dc59a59269cfeb5576063888b5b8ac1c',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_3629c0b270e9ca424122(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/labels/; business relation P19 requires observation $.meta.pagination.total (integer) = count(observation $.labels (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0002\nCanonical relation core: 3d24bef0bdd02dfa8cef73b70c242960eb1b2ca709a116c011e7f10c3e0fbef8\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
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
                              'rationale': 'Proposed unit for the counted labels collection; from the '
                                           'visible array path only, not from any external '
                                           'specification.',
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
        test_id='relation-test-3629c0b270e9ca424122',
        candidate_id='v2-candidate-0002',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='bae5a53cbef599aa605e392215c788cd4dfadfd529b634fb8ce0d03685b14914',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_2814f53c606d6d3b70cd(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint For every member of observation $.tiers (array) in actual_response: P02 requires item $.active (boolean) to strictly equal frozen hypothesis True (boolean); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0003\nCanonical relation core: 272ce11d8d4ce88b1d57b0bb00d48707e337854461c314eb72b0178222752762\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[5].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
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
      'predicate_type': 'forall',
      'predicate': {'body': {'family': 'P02',
                             'left': {'path': '$.active', 'role': 'item', 'value_type': 'boolean'},
                             'operator': 'eq',
                             'right': {'evidence_refs': ['r20260920-170651-22bb:request:26'],
                                       'rationale': 'Proposed reading of the recorded selector '
                                                    'filter=type:paid+active:true as requiring the '
                                                    'boolean member field active to be true; the '
                                                    'selector text is the only evidence and the '
                                                    'recorded members need not already satisfy it.',
                                       'source': 'hypothesis',
                                       'value': True,
                                       'value_type': 'boolean'}},
                    'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0003-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0003-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-2814f53c606d6d3b70cd',
        candidate_id='v2-candidate-0003',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='9b3ccb50432a3fc8ccb6667d6f312d08d2a903ebbb617987326adef5ec4af71a',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_0be2088e44d7b9b908ed(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint For every member of observation $.tiers (array) in actual_response: P02 requires item $.type (string) to strictly equal frozen hypothesis 'paid' (string); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0004\nCanonical relation core: 0378fcb8e31ca88af9232d8d583333f161c1814c0f4791d63018a62953d09785\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[6].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[5].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0004
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
    assertions = [{'assertion_id': 'v2-candidate-0004-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'family': 'P02',
                             'left': {'path': '$.type', 'role': 'item', 'value_type': 'string'},
                             'operator': 'eq',
                             'right': {'evidence_refs': ['r20260920-170651-22bb:request:26'],
                                       'rationale': 'Proposed reading of the recorded selector '
                                                    'filter=type:paid+active:true as requiring the '
                                                    'string member field type to equal "paid"; the '
                                                    'selector text is the only evidence and the '
                                                    'recorded members need not already satisfy it.',
                                       'source': 'hypothesis',
                                       'value': 'paid',
                                       'value_type': 'string'}},
                    'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0004-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0004-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-0be2088e44d7b9b908ed',
        candidate_id='v2-candidate-0004',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='57ea4cc6a3392867b1fa9dee3addd5c1be18fa8cb1eeaa47bf9679b9966e8632',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_c4e8c1b4de32849c2931(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint For every member of observation $.newsletters (array) in actual_response: P02 requires item $.status (string) to strictly equal frozen hypothesis 'active' (string); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0005\nCanonical relation core: 9fc9db8e57085803e8fd2bda702a98b84601a37b14b9b0ca2205e455aafa0f7b\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[4].rationale\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[6].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[5].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[7].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[6].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0005
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
    assertions = [{'assertion_id': 'v2-candidate-0005-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'family': 'P02',
                             'left': {'path': '$.status', 'role': 'item', 'value_type': 'string'},
                             'operator': 'eq',
                             'right': {'evidence_refs': ['r20260920-170651-22bb:request:27'],
                                       'rationale': 'Proposed reading of the recorded selector '
                                                    'filter=status:active as requiring the string '
                                                    'member field status to equal "active"; the '
                                                    'selector text is the only evidence and the '
                                                    'recorded members need not already satisfy it.',
                                       'source': 'hypothesis',
                                       'value': 'active',
                                       'value_type': 'string'}},
                    'collection': {'path': '$.newsletters',
                                   'role': 'observation',
                                   'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
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
                    'target_path': '$.newsletters',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-c4e8c1b4de32849c2931',
        candidate_id='v2-candidate-0005',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='e8e8ef7f45a4889f13d05a4a98738051f9127180f58c5b74e5aa59791a24eb8b',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_4c5cb988be76d69ae70b(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint P15 requires observation $.tiers (array) (actual_response) to have unique members by strict-tuple identity [$.id]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0006\nCanonical relation core: f79e87788d14e9c2596cd65cb6665c9c43a813494db312f781ad92db57c90f0e\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[4].rationale\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[4].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[8].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[6].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
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
      'predicate_type': 'P15',
      'predicate': {'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
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
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-4c5cb988be76d69ae70b',
        candidate_id='v2-candidate-0006',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='cc0d8a3d56fee7954b0afc42adba47c08fba627f59dd3425b65a05345e28ba48',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_54f49f590b3cf68f027a(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint P15 requires observation $.newsletters (array) (actual_response) to have unique members by strict-tuple identity [$.id]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0007\nCanonical relation core: 342eb75d817266ce91f0115a8a5985a75a11f4d41e49f158e791fcecb116dcfe\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[5].rationale\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[7].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[9].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[5].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
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
      'predicate_type': 'P15',
      'predicate': {'collection': {'path': '$.newsletters',
                                   'role': 'observation',
                                   'value_type': 'array'},
                    'family': 'P15',
                    'identity': {'paths': ['$.id'], 'semantics': 'strict-tuple'},
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
                    'target_path': '$.newsletters',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-54f49f590b3cf68f027a',
        candidate_id='v2-candidate-0007',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='5b8011676ff56bf55b367658a2ceaba8f6e1db3fdc820b5975a0dc6150f564da',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_be181bd37f4b7560f61d(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/tiers/; business relation P19 requires observation $.meta.pagination.total (integer) = count(observation $.tiers (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0008\nCanonical relation core: c52c713b22517e1d232e8cb9ad25f7eee5efd32203a7a88ceb1a159384afff57\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
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
                              'rationale': 'Proposed unit for counting the observed tiers array '
                                           'members; not prevalidated.',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0008-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0008-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.total',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-be181bd37f4b7560f61d',
        candidate_id='v2-candidate-0008',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='dc0cb52cb4a46af279bfc24a258a8022ad9db6d6c247b5e0e12be6dc9fd331fe',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_8400a31c3937b9024a4d(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; business relation P19 requires observation $.meta.pagination.total (integer) = count(observation $.newsletters (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0009\nCanonical relation core: 92a329fa52b780bf4efd355da67fa8efb017854c104da25308361b43a6eb33f7\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[5].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
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
                              'rationale': 'Proposed unit for counting the observed newsletters array '
                                           'members; not prevalidated.',
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
                    'target_path': '$.meta.pagination.total',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-8400a31c3937b9024a4d',
        candidate_id='v2-candidate-0009',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='5c2e441c718787ec47ce04411070505ea7c2dd38d3a0055b1033bdeba152165f',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_a2aafd2381c511d25989(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P21 requires observation $.labels (array) to have JSON type array; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0010\nCanonical relation core: 1bf4e2330e20b909459352c461015f87f50ce9c31b8a1b663cad9acd77ee374e\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0010
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170651-22bb:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0010-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'array',
                    'family': 'P21',
                    'target': {'path': '$.labels', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0010-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0010-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-a2aafd2381c511d25989',
        candidate_id='v2-candidate-0010',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='ec25adf66c31e62e91f2b1798e48ed974d602db84021f074825c1921f8dd1de8',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_792298e854d52c37e7bb(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint P21 requires observation $.tiers (array) to have JSON type array; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0011\nCanonical relation core: ebfd633549f2c47aab96bb9c15c212340abfa9ce2ba67d7b77a658ceb9fb9fbf\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[4].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
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
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'array',
                    'family': 'P21',
                    'target': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'}}},
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
        test_id='relation-test-792298e854d52c37e7bb',
        candidate_id='v2-candidate-0011',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='317212d6042cf76d9ad3d08f3390b23322936f64d1dfd0bce79a5ebc81c53062',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_86e2b56fd8d57ff4d3c2(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint P21 requires observation $.newsletters (array) to have JSON type array; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0012\nCanonical relation core: ad65c0f0bef8a983bbb9383eeef84b424c34a22e98c938a6dab306153fbfc5a2\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[6].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
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
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'array',
                    'family': 'P21',
                    'target': {'path': '$.newsletters', 'role': 'observation', 'value_type': 'array'}}},
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
        test_id='relation-test-86e2b56fd8d57ff4d3c2',
        candidate_id='v2-candidate-0012',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='80f8e9d4ed525d0ffb4922ca980953a3074d74bb8101a50b47c4ae679928bb90',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_c46b946edf445f7f4e43(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P02 requires observation $.meta.pagination.limit (integer) to numerically equal actual request query $.limit (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0013\nCanonical relation core: a81e9395cdf7fcc5dee1ac1cb7c7daa0da896d7ae63ece3acf5e2edb8a939678\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[4].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[4].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0013
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170651-22bb:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0013-business-01',
      'class': 'business',
      'predicate_type': 'P02',
      'predicate': {'family': 'P02',
                    'left': {'path': '$.meta.pagination.limit',
                             'role': 'observation',
                             'value_type': 'integer'},
                    'operator': 'numeric_eq',
                    'right': {'ref': {'location': 'query',
                                      'path': '$.limit',
                                      'role': 'observation_request',
                                      'value_type': 'integer'},
                              'source': 'request'}}},
     {'assertion_id': 'v2-candidate-0013-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0013-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.limit',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-c46b946edf445f7f4e43',
        candidate_id='v2-candidate-0013',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='8495e78311acc57762c87608aa3e491abba02fa133c742d132e09eab7e523d56',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_e66d9c120ff4d41a1d9e(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P02 requires observation $.meta.pagination.page (integer) to numerically equal actual request query $.page (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0014\nCanonical relation core: f5cef59ce040adf3c39373e0861c15cc381f519af4bf2722fbe45879fe4557c2\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[5].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0014
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170651-22bb:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0014-business-01',
      'class': 'business',
      'predicate_type': 'P02',
      'predicate': {'family': 'P02',
                    'left': {'path': '$.meta.pagination.page',
                             'role': 'observation',
                             'value_type': 'integer'},
                    'operator': 'numeric_eq',
                    'right': {'ref': {'location': 'query',
                                      'path': '$.page',
                                      'role': 'observation_request',
                                      'value_type': 'integer'},
                              'source': 'request'}}},
     {'assertion_id': 'v2-candidate-0014-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0014-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.page',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-e66d9c120ff4d41a1d9e',
        candidate_id='v2-candidate-0014',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='35f0b8eb1531ceba5aa12faff3c9bab193548fd2a3e8e5389412d20f2ea808a8',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_d822f0234ca02ce88959(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P02 requires observation $.meta.pagination.page (integer) to strictly equal actual request query $.page (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0015\nCanonical relation core: 4613bf61ce3753ba61dbbf3a64cb633f23762100fa12d4b28e57e0b32abc642f\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[4].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0015
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170651-22bb:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0015-business-01',
      'class': 'business',
      'predicate_type': 'P02',
      'predicate': {'family': 'P02',
                    'left': {'path': '$.meta.pagination.page',
                             'role': 'observation',
                             'value_type': 'integer'},
                    'operator': 'eq',
                    'right': {'ref': {'location': 'query',
                                      'path': '$.page',
                                      'role': 'observation_request',
                                      'value_type': 'integer'},
                              'source': 'request'}}},
     {'assertion_id': 'v2-candidate-0015-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0015-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.page',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-d822f0234ca02ce88959',
        candidate_id='v2-candidate-0015',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='a310a233dfdf149ba6607315b316b16aee818911cf232715bf9911e58a69ecef',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_8336b45f42d2d7ad4f5f(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/labels/; business relation P19 requires observation $.meta.pagination.total (integer) = count(observation $.labels (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0016\nCanonical relation core: 3d24bef0bdd02dfa8cef73b70c242960eb1b2ca709a116c011e7f10c3e0fbef8\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0016
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170651-22bb:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0016-business-01',
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
                              'rationale': 'The recorded labels response exposes an array and an '
                                           'integer pagination total; the count output is proposed to '
                                           'be measured in items.',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0016-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0016-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.total',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-8336b45f42d2d7ad4f5f',
        candidate_id='v2-candidate-0016',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='2b0123fbb846216dfa92dfb77905ba5f4efa46df6798dbcc2ce5167e4722e35d',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_7892110dc1cd44d42879(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P01 requires field observation $.labels (array) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0017\nCanonical relation core: aea18ef3894638389e664599ab7e7f73dd06ac566b6b2aa4b0c196bd820d1d1b\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0017
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170651-22bb:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0017-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.labels', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0017-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0017-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-7892110dc1cd44d42879',
        candidate_id='v2-candidate-0017',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='d53339f2153fad5539beaa11d9ef9538745ba357752ce4ce9e73e148739fcd59',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_44c2ff2751845adfdf07(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/tiers/; business relation P19 requires observation $.meta.pagination.total (integer) = count(observation $.tiers (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0018\nCanonical relation core: c52c713b22517e1d232e8cb9ad25f7eee5efd32203a7a88ceb1a159384afff57\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0018
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
    assertions = [{'assertion_id': 'v2-candidate-0018-business-01',
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
                              'rationale': 'The recorded tiers response exposes an array and an '
                                           'integer pagination total; the count output is proposed to '
                                           'be measured in items.',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0018-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0018-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.total',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-44c2ff2751845adfdf07',
        candidate_id='v2-candidate-0018',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='1f4d848bcfe85d07c39fff6afc3d35943a5f34f21288973b1ec0510b2eb28e8e',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_aeba49018043473996e9(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; business relation P19 requires observation $.meta.pagination.total (integer) = count(observation $.newsletters (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0019\nCanonical relation core: 92a329fa52b780bf4efd355da67fa8efb017854c104da25308361b43a6eb33f7\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[4].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0019
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
    assertions = [{'assertion_id': 'v2-candidate-0019-business-01',
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
                              'rationale': 'The recorded newsletters response exposes an array and an '
                                           'integer pagination total; the count output is proposed to '
                                           'be measured in items.',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0019-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0019-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.total',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-aeba49018043473996e9',
        candidate_id='v2-candidate-0019',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='44fe8b4f19b5721af059eafb4453bb66c4c63efe94855e6ae45bfd2b79f39ee0',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_130195b577ebf50e0824(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint P01 requires field observation $.tiers (array) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0020\nCanonical relation core: 4455d92f4b5a11660326199cae6b32ec2935200438a7a1d8d1488632ffa6e0c5\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[7].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0020
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
    assertions = [{'assertion_id': 'v2-candidate-0020-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0020-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0020-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-130195b577ebf50e0824',
        candidate_id='v2-candidate-0020',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='9178f52a8d1910c05cb1cb3c6c18e975ac66c3d98075668af4d8936038cc62da',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_6de60e99bbd1250d790e(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint P01 requires field observation $.newsletters (array) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0021\nCanonical relation core: d3d736e6ad8ffdf044253a23bc534895da722af770079ce1209922c3bdd0ea0f\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[8].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0021
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
    assertions = [{'assertion_id': 'v2-candidate-0021-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.newsletters', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0021-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0021-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.newsletters',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-6de60e99bbd1250d790e',
        candidate_id='v2-candidate-0021',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='5f2005199db6d7b42814f96c703292d7d3d91d1b00d6ad9941c12f5b6a2b3f79',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])
