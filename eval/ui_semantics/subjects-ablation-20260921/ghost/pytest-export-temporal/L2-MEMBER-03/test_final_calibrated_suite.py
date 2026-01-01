"""Generated from a frozen UISemTest M14 suite; do not edit by hand."""

def test_relation_test_c9e79403579f5851269b(uisemtest_runtime):
    'Business summary: Producer actor_a POST /ghost/api/admin/members/; observer actor_a GET /ghost/api/admin/labels/; business predicate P20 requires strict equality between before $.labels (array) and after $.labels (array).\nCandidate ID: v2-candidate-0001\nCanonical relation core: dce7341d4f2333c10e9b52b06bd51dff495e0934c5d1d41ec0c27270d5f14836\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V4: v2-candidate-0001
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'workflow', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'before_observer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'},
     {'kind': 'http',
      'phase': 'producer',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/ghost/api/admin/members/',
      'request_ref': 'r20260920-170620-c734:request:30'},
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
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:34'}]
    assertions = [{'assertion_id': 'v2-candidate-0001-business-01',
      'class': 'business',
      'predicate_type': 'P20',
      'predicate': {'family': 'P20',
                    'left': {'path': '$.labels', 'role': 'before', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'projection_ref': None,
                    'right': {'path': '$.labels', 'role': 'after', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0001-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0001-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0001-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-c9e79403579f5851269b',
        candidate_id='v2-candidate-0001',
        protocol_kind='V4',
        normal_runs=1,
        source_test_sha256='bbacf2be8314fdf7a921d2d8155c6bc06f50a1a3f776e288dad753ad3233f114',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_c58a04ffa4c9f2c29166(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P11 requires count(observation $.labels (array)) <= this request's query.limit; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0006\nCanonical relation core: 9d8a5e79a202b8e7dbaf99e00b10d262ded82ae7be7d74cd4403c68f4aa4312a\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0006
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0006-business-01',
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
     {'assertion_id': 'v2-candidate-0006-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0006-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-c58a04ffa4c9f2c29166',
        candidate_id='v2-candidate-0006',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='f7d3c752b3393826f476208ce6f860810bd1df57d40a8ae478ede02f00b5a95e',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_6d3c2bfa9f4b74f4905a(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P02 requires observation $.meta.pagination.limit (integer) to strictly equal actual request query $.limit (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0007\nCanonical relation core: ea91525ca09597c866b944287c7a555b9ed6b79c2bcc37f0a4511ad03f77c0e1\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0007
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0007-business-01',
      'class': 'business',
      'predicate_type': 'P02',
      'predicate': {'family': 'P02',
                    'left': {'path': '$.meta.pagination.limit',
                             'role': 'observation',
                             'value_type': 'integer'},
                    'operator': 'eq',
                    'right': {'ref': {'location': 'query',
                                      'path': '$.limit',
                                      'role': 'observation_request',
                                      'value_type': 'integer'},
                              'source': 'request'}}},
     {'assertion_id': 'v2-candidate-0007-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0007-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.limit',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-6d3c2bfa9f4b74f4905a',
        candidate_id='v2-candidate-0007',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='cd355982a9f538c6d425e5bf14feec073033a0c0721486d503e9aa24d9fa3114',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_7333d9df5bb53fd40038(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint For every member of observation $.tiers (array) in actual_response: P02 requires item $.type (string) to strictly equal frozen hypothesis 'paid' (string); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0008\nCanonical relation core: 0378fcb8e31ca88af9232d8d583333f161c1814c0f4791d63018a62953d09785\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0008
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/tiers/',
      'request_ref': 'r20260920-170620-c734:request:26'}]
    assertions = [{'assertion_id': 'v2-candidate-0008-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'family': 'P02',
                             'left': {'path': '$.type', 'role': 'item', 'value_type': 'string'},
                             'operator': 'eq',
                             'right': {'evidence_refs': ['r20260920-170620-c734:request:26'],
                                       'rationale': 'the recorded tiers selector filter is '
                                                    'type:paid+active:true; proposes that every '
                                                    'returned tier has type paid',
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
        test_id='relation-test-7333d9df5bb53fd40038',
        candidate_id='v2-candidate-0008',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='4c63d069e40b2113a7a3b0bbd4abe3cc2fc492e87beaf02ae52ffbeb00e5fa4c',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_4bf303bc4f8642a49351(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint For every member of observation $.tiers (array) in actual_response: P02 requires item $.active (boolean) to strictly equal frozen hypothesis True (boolean); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0009\nCanonical relation core: 272ce11d8d4ce88b1d57b0bb00d48707e337854461c314eb72b0178222752762\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0009
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/tiers/',
      'request_ref': 'r20260920-170620-c734:request:26'}]
    assertions = [{'assertion_id': 'v2-candidate-0009-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'family': 'P02',
                             'left': {'path': '$.active', 'role': 'item', 'value_type': 'boolean'},
                             'operator': 'eq',
                             'right': {'evidence_refs': ['r20260920-170620-c734:request:26'],
                                       'rationale': 'the recorded tiers selector filter is '
                                                    'type:paid+active:true; proposes that every '
                                                    'returned tier is active',
                                       'source': 'hypothesis',
                                       'value': True,
                                       'value_type': 'boolean'}},
                    'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
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
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-4bf303bc4f8642a49351',
        candidate_id='v2-candidate-0009',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='dac3b316af6c04d453eaa12914aac9b4231cbdc29ccafa8e752049ead29f0b1c',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_346e45aff9b0196f3e04(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint For every member of observation $.newsletters (array) in actual_response: P02 requires item $.status (string) to strictly equal frozen hypothesis 'active' (string); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0010\nCanonical relation core: 9fc9db8e57085803e8fd2bda702a98b84601a37b14b9b0ca2205e455aafa0f7b\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[4].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0010
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/tiers/',
      'request_ref': 'r20260920-170620-c734:request:26'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/newsletters/',
      'request_ref': 'r20260920-170620-c734:request:27'}]
    assertions = [{'assertion_id': 'v2-candidate-0010-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'family': 'P02',
                             'left': {'path': '$.status', 'role': 'item', 'value_type': 'string'},
                             'operator': 'eq',
                             'right': {'evidence_refs': ['r20260920-170620-c734:request:27'],
                                       'rationale': 'the recorded newsletters selector filter is '
                                                    'status:active; proposes that every returned '
                                                    'newsletter has status active',
                                       'source': 'hypothesis',
                                       'value': 'active',
                                       'value_type': 'string'}},
                    'collection': {'path': '$.newsletters',
                                   'role': 'observation',
                                   'value_type': 'array'},
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
                    'target_path': '$.newsletters',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-346e45aff9b0196f3e04',
        candidate_id='v2-candidate-0010',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='879a84ff8416b6a2ef174b669e1f966e7f58d144a644f0859e95642a7fe403e8',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_11076114f7abc38e2971(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint P15 requires observation $.tiers (array) (actual_response) to have unique members by strict-tuple identity [$.id]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0011\nCanonical relation core: f79e87788d14e9c2596cd65cb6665c9c43a813494db312f781ad92db57c90f0e\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[5].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0011
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/tiers/',
      'request_ref': 'r20260920-170620-c734:request:26'}]
    assertions = [{'assertion_id': 'v2-candidate-0011-business-01',
      'class': 'business',
      'predicate_type': 'P15',
      'predicate': {'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P15',
                    'identity': {'paths': ['$.id'], 'semantics': 'strict-tuple'},
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
        test_id='relation-test-11076114f7abc38e2971',
        candidate_id='v2-candidate-0011',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='dec3998a93264367904726bc7361a0a9822949d4423c991d69bed0ee283234bb',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_99068201b1d33cd34272(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint P15 requires observation $.newsletters (array) (actual_response) to have unique members by strict-tuple identity [$.id]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0012\nCanonical relation core: 342eb75d817266ce91f0115a8a5985a75a11f4d41e49f158e791fcecb116dcfe\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[6].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0012
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/tiers/',
      'request_ref': 'r20260920-170620-c734:request:26'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/newsletters/',
      'request_ref': 'r20260920-170620-c734:request:27'}]
    assertions = [{'assertion_id': 'v2-candidate-0012-business-01',
      'class': 'business',
      'predicate_type': 'P15',
      'predicate': {'collection': {'path': '$.newsletters',
                                   'role': 'observation',
                                   'value_type': 'array'},
                    'family': 'P15',
                    'identity': {'paths': ['$.id'], 'semantics': 'strict-tuple'},
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
        test_id='relation-test-99068201b1d33cd34272',
        candidate_id='v2-candidate-0012',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='35731bf48e71e170fe9e0eb2db5f409d15609c319af14edd0ebf6e610b859567',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_ad4b2b223989f31df978(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/members/; business relation P19 requires observation $.meta.pagination.total (integer) = count(observation $.members (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0017\nCanonical relation core: 3c2189f7daef4b3b67e969b9bd268c756e34b73925e2046336ce1679cb162001\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[5].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0017
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'setup[0]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'},
     {'kind': 'http',
      'phase': 'setup[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/tiers/',
      'request_ref': 'r20260920-170620-c734:request:26'},
     {'kind': 'http',
      'phase': 'setup[2]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/newsletters/',
      'request_ref': 'r20260920-170620-c734:request:27'},
     {'kind': 'http',
      'phase': 'setup[3]',
      'actor': 'actor_a',
      'method': 'POST',
      'path': '/ghost/api/admin/members/',
      'request_ref': 'r20260920-170620-c734:request:30'},
     {'kind': 'http',
      'phase': 'setup[4]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/members/stats/count/',
      'request_ref': 'r20260920-170620-c734:request:31'},
     {'kind': 'http',
      'phase': 'setup[5]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/stats/member_count/',
      'request_ref': 'r20260920-170620-c734:request:32'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/members/',
      'request_ref': 'r20260920-170620-c734:request:33'}]
    assertions = [{'assertion_id': 'v2-candidate-0017-business-01',
      'class': 'business',
      'predicate_type': 'P19',
      'predicate': {'collection': {'path': '$.members', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P19',
                    'numeric_mode': 'exact',
                    'operator': 'count',
                    'output': {'path': '$.meta.pagination.total',
                               'role': 'observation',
                               'value_type': 'integer'},
                    'scope': 'actual_response',
                    'units': {'evidence_refs': ['r20260920-170620-c734:request:33'],
                              'rationale': 'proposed count of the returned members array measured in '
                                           'members',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0017-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0017-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.total',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-ad4b2b223989f31df978',
        candidate_id='v2-candidate-0017',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='0e4ddd5bb44537c68647d098afb0c7a8ffe8e780d0caf7db3f7dccfe3fa9a264',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])
