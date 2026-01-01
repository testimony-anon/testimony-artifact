"""Generated from a frozen UISemTest M14 suite; do not edit by hand."""

def test_relation_test_54b00707192cb085bea7(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P11 requires count(observation $.labels (array)) <= this request's query.limit; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0001\nCanonical relation core: 9d8a5e79a202b8e7dbaf99e00b10d262ded82ae7be7d74cd4403c68f4aa4312a\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[12].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0001
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'}]
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
        test_id='relation-test-54b00707192cb085bea7',
        candidate_id='v2-candidate-0001',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='da63f8ed0bc14a7f4cfba72ea8cc32e67fd0db2c8f40cf6b95ca75a473cfeea5',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_eda9cddacb1a3803145a(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint For every member of observation $.tiers (array) in actual_response: P02 requires item $.active (boolean) to strictly equal frozen hypothesis True (boolean); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0002\nCanonical relation core: 272ce11d8d4ce88b1d57b0bb00d48707e337854461c314eb72b0178222752762\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[38].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[7].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0002
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
    assertions = [{'assertion_id': 'v2-candidate-0002-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'family': 'P02',
                             'left': {'path': '$.active', 'role': 'item', 'value_type': 'boolean'},
                             'operator': 'eq',
                             'right': {'evidence_refs': ['r20260920-170620-c734:request:26'],
                                       'rationale': "Proposed that the visible 'active:true' component "
                                                    "of the recorded filter 'type:paid+active:true' "
                                                    'selects only active tiers; the recorded values '
                                                    'need not already satisfy this proposed request '
                                                    'semantic.',
                                       'source': 'hypothesis',
                                       'value': True,
                                       'value_type': 'boolean'}},
                    'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0002-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0002-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-eda9cddacb1a3803145a',
        candidate_id='v2-candidate-0002',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='e19634daa1ba3e59cb0ffe90e93958e9a05cebbf0364fcb2c1bf87d1b9c594ab',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_49473bd561758e579b32(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint For every member of observation $.newsletters (array) in actual_response: P02 requires item $.status (string) to strictly equal frozen hypothesis 'active' (string); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0003\nCanonical relation core: 9fc9db8e57085803e8fd2bda702a98b84601a37b14b9b0ca2205e455aafa0f7b\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[4].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[56].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[8].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[6].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[5].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0003
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
    assertions = [{'assertion_id': 'v2-candidate-0003-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'family': 'P02',
                             'left': {'path': '$.status', 'role': 'item', 'value_type': 'string'},
                             'operator': 'eq',
                             'right': {'evidence_refs': ['r20260920-170620-c734:request:27'],
                                       'rationale': "Proposed that the recorded filter 'status:active' "
                                                    'selects only newsletters whose status equals '
                                                    "'active'; the recorded members need not already "
                                                    'satisfy this proposed request semantic.',
                                       'source': 'hypothesis',
                                       'value': 'active',
                                       'value_type': 'string'}},
                    'collection': {'path': '$.newsletters',
                                   'role': 'observation',
                                   'value_type': 'array'},
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
                    'target_path': '$.newsletters',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-49473bd561758e579b32',
        candidate_id='v2-candidate-0003',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='f94f2969826fdd1636da08fc338d9d84a2c7c268291aa58bcea6b53af4f11e35',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_8673dbdd85c05c0c8f54(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P11 requires count(observation $.labels (array); unit=items) eq observation $.meta.pagination.total (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0004\nCanonical relation core: 8c97b92465c1719d1d3af0e98198632e2bafed11a9f79aa79840d4e9e6349d68\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0004
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0004-business-01',
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
        test_id='relation-test-8673dbdd85c05c0c8f54',
        candidate_id='v2-candidate-0004',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='d2f3d489b8105122de99ea1ec9e53a8b445c31c31ba1df7b68d0503c3e0375d3',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_ac7319bbe834e0a6970b(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint P11 requires count(observation $.tiers (array); unit=items) eq observation $.meta.pagination.total (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0005\nCanonical relation core: 1dcab7b65d39bc3ce4c48e9df2a1f9e6f4a3504ff29e743ebbc41a54c1ec41ee\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0005
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
                    'target': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
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
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-ac7319bbe834e0a6970b',
        candidate_id='v2-candidate-0005',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='77a984e97b97c6841b53c13347274a9529d8ed333f309e09a4529e07b1f357b1',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_24197cab27c54470923b(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint P11 requires count(observation $.tiers (array); unit=items) le observation $.meta.pagination.limit (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0006\nCanonical relation core: 8d1681632d39534577d1919698faf8399cb845ff938b811af6a6d52361f5b652\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0006
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
    assertions = [{'assertion_id': 'v2-candidate-0006-business-01',
      'class': 'business',
      'predicate_type': 'P11',
      'predicate': {'family': 'P11',
                    'operator': 'le',
                    'projection': 'count',
                    'right': {'ref': {'path': '$.meta.pagination.limit',
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
        test_id='relation-test-24197cab27c54470923b',
        candidate_id='v2-candidate-0006',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='06671c67c6d4aea8490ac98dd8ac1f520e8dc3ed1a73712e787025d9980b7665',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_a8e60aef159a04b72d28(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint For every member of observation $.tiers (array) in actual_response: P02 requires item $.monthly_price (integer) to be at most item $.yearly_price (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0007\nCanonical relation core: a91ff84992f00d3a54d1a6c78eb869aadfc4176f10680006f1bfec79575e43d4\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[4].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0007
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
    assertions = [{'assertion_id': 'v2-candidate-0007-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'family': 'P02',
                             'left': {'path': '$.monthly_price',
                                      'role': 'item',
                                      'value_type': 'integer'},
                             'operator': 'le',
                             'right': {'ref': {'path': '$.yearly_price',
                                               'role': 'item',
                                               'value_type': 'integer'},
                                       'source': 'role'}},
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
        test_id='relation-test-a8e60aef159a04b72d28',
        candidate_id='v2-candidate-0007',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='fa0f35f724b7a46e4d441185d365bca2710af2c3512c21d4dc1652702ca76f87',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_7a54899eb18bbea9dad7(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint P15 requires observation $.tiers (array) (actual_response) to have unique members by strict-tuple identity [$.id]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0008\nCanonical relation core: f79e87788d14e9c2596cd65cb6665c9c43a813494db312f781ad92db57c90f0e\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[5].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[27].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[4].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[5].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
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
        test_id='relation-test-7a54899eb18bbea9dad7',
        candidate_id='v2-candidate-0008',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='8c6c09270d988c0344edbf4c1959bb38476971aa9f97e0327c0403543fa99715',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_e7fea54ffcbb000afbc8(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint P11 requires count(observation $.newsletters (array); unit=items) eq observation $.meta.pagination.total (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0009\nCanonical relation core: f4f2658bfa1c3cdbcfbffaefa18b56a10cc4dde35ad76eff01ec2ad86351f0e4\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[6].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0009
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
    assertions = [{'assertion_id': 'v2-candidate-0009-business-01',
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
        test_id='relation-test-e7fea54ffcbb000afbc8',
        candidate_id='v2-candidate-0009',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='e9018c88601ed3d653bfdd50d2d014d01d705d8f2158645b9c119596adc31712',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_f4acfb409d9aea8acfa3(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint P11 requires count(observation $.newsletters (array); unit=items) le observation $.meta.pagination.limit (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0010\nCanonical relation core: 43b2348cd30a7d7ace3ade391331b2a463773453534508093596dd24c8074807\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[7].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
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
      'predicate_type': 'P11',
      'predicate': {'family': 'P11',
                    'operator': 'le',
                    'projection': 'count',
                    'right': {'ref': {'path': '$.meta.pagination.limit',
                                      'role': 'observation',
                                      'value_type': 'integer'},
                              'source': 'role'},
                    'target': {'path': '$.newsletters', 'role': 'observation', 'value_type': 'array'},
                    'unit': 'items'}},
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
        test_id='relation-test-f4acfb409d9aea8acfa3',
        candidate_id='v2-candidate-0010',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='3524aab9f2cc9571766efb9bbb75254281b92a6c8ebdeaa63c2c43b154ddf3d7',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_062e9a759c6e3d5825dd(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint P15 requires observation $.newsletters (array) (actual_response) to have unique members by strict-tuple identity [$.id]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0011\nCanonical relation core: 342eb75d817266ce91f0115a8a5985a75a11f4d41e49f158e791fcecb116dcfe\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[8].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[51].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[5].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[7].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0011
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
    assertions = [{'assertion_id': 'v2-candidate-0011-business-01',
      'class': 'business',
      'predicate_type': 'P15',
      'predicate': {'collection': {'path': '$.newsletters',
                                   'role': 'observation',
                                   'value_type': 'array'},
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
                    'target_path': '$.newsletters',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-062e9a759c6e3d5825dd',
        candidate_id='v2-candidate-0011',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='59c8b3f36de01e6567c12e18b0b57620c26b72b04769dcab1d593d21b56dd498',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_ef4d9358b630f88ff7df(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint P15 requires observation $.newsletters (array) (actual_response) to have unique members by strict-tuple identity [$.uuid]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0012\nCanonical relation core: b39b6b0215965b1653856c7569ec6511b094cf1e8145d239adbadb1655d226df\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[9].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[52].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
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
                    'identity': {'paths': ['$.uuid'], 'semantics': 'strict-tuple'},
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
        test_id='relation-test-ef4d9358b630f88ff7df',
        candidate_id='v2-candidate-0012',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='514b8e1c7e0c60e8621f9f256414bac1bff8f1e3aa6f45da4641e97f8b6b8a2c',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_6f07196c963b3de0f928(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint For every member of observation $.tiers (array) in actual_response: P02 requires item $.type (string) to strictly equal frozen hypothesis 'paid' (string); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0013\nCanonical relation core: 0378fcb8e31ca88af9232d8d583333f161c1814c0f4791d63018a62953d09785\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[37].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[6].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[4].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0013
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
    assertions = [{'assertion_id': 'v2-candidate-0013-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'family': 'P02',
                             'left': {'path': '$.type', 'role': 'item', 'value_type': 'string'},
                             'operator': 'eq',
                             'right': {'evidence_refs': ['r20260920-170620-c734:request:26'],
                                       'rationale': 'The recorded selector filter '
                                                    "'type:paid+active:true' on this same read "
                                                    'proposes that every returned tier has type '
                                                    "'paid'. The conjunct decomposition is a proposed "
                                                    'rule that is not prevalidated by the recording.',
                                       'source': 'hypothesis',
                                       'value': 'paid',
                                       'value_type': 'string'}},
                    'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0013-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0013-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-6f07196c963b3de0f928',
        candidate_id='v2-candidate-0013',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='99137028c70c4c0f06630743a631afb054a081934a714c0794593bf640a5bfe2',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_85b1c6be48df2e0fc8a7(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/tiers/; business relation P19 requires observation $.meta.pagination.total (integer) = count(observation $.tiers (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0014\nCanonical relation core: c52c713b22517e1d232e8cb9ad25f7eee5efd32203a7a88ceb1a159384afff57\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[4].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0014
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
    assertions = [{'assertion_id': 'v2-candidate-0014-business-01',
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
                    'units': {'evidence_refs': ['r20260920-170620-c734:request:26'],
                              'rationale': 'The counted collection and the summary field are both '
                                           'members of the same recorded response; the output unit is '
                                           'proposed as items.',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0014-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0014-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.total',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-85b1c6be48df2e0fc8a7',
        candidate_id='v2-candidate-0014',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='3e219a0464a3ac18a047083840d12dfc00b7ab6fb892036e461632ff35106436',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_1bf24f4e659bf447b04f(uisemtest_runtime):
    "Business summary: Producer actor_a POST /ghost/api/admin/members/; observer actor_a GET /ghost/api/admin/labels/; business predicate P20 requires strict equality between before $ (object) and after $ (object) for every frozen field ['$.labels']; known false survives another unavailable field.\nCandidate ID: v2-candidate-0015\nCanonical relation core: 4bfa4f815466f9d42b51bbf209c4851ac2f5d0d611d99e569ba5c0a83044a0d0\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0004/provider_response_envelope.json#content(from-json).candidates[0].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0004/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V4: v2-candidate-0015
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
    assertions = [{'assertion_id': 'v2-candidate-0015-business-01',
      'class': 'business',
      'predicate_type': 'P20',
      'predicate': {'family': 'P20',
                    'left': {'path': '$', 'role': 'before', 'value_type': 'object'},
                    'operator': 'equal',
                    'projection': ['$.labels'],
                    'projection_ref': None,
                    'right': {'path': '$', 'role': 'after', 'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0015-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0015-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0015-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'object',
                    'response_ref': 'after',
                    'target_path': '$',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-1bf24f4e659bf447b04f',
        candidate_id='v2-candidate-0015',
        protocol_kind='V4',
        normal_runs=1,
        source_test_sha256='4a0faf1a2e0e183f75f1eb6c1448e76a081be31268d84811f85e068fa59b044c',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_f35a5bdf693d1ffbf907(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/members/; basic constraint P11 requires count(observation $.members (array)) <= this request's query.limit; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0016\nCanonical relation core: f2b4c912feb2a79c4547ed603281cb5ae48cabf62034d58daac5f49ab88720e5\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0005/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0001/M10/calls/detail-0006/provider_response_envelope.json#content(from-json).candidates[4].rationale\n- ../attempts/attempt-0001/M10/calls/detail-0008/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0001/M10/calls/detail-0009/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0001/M10/calls/detail-0011/provider_response_envelope.json#content(from-json).candidates[4].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0005/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0006/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0007/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0008/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0005/provider_response_envelope.json#content(from-json).candidates[2].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0009/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0010/provider_response_envelope.json#content(from-json).candidates[4].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0016
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
    assertions = [{'assertion_id': 'v2-candidate-0016-business-01',
      'class': 'business',
      'predicate_type': 'P11',
      'predicate': {'collection': {'path': '$.members', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P11',
                    'operator': 'le',
                    'right': {'ref': {'location': 'query',
                                      'path': '$.limit',
                                      'role': 'observation_request',
                                      'value_type': 'integer'},
                              'source': 'request'}}},
     {'assertion_id': 'v2-candidate-0016-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0016-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.members',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-f35a5bdf693d1ffbf907',
        candidate_id='v2-candidate-0016',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='325a75a57369c95cec72f6d01da09404cb5ffa736f8cc33b020f3704ccb2d209',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_c701879b114e1091cff7(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/stats/member_count/; basic constraint P15 requires observation $.stats (array) (actual_response) to have unique members by strict-tuple identity [$.date]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0017\nCanonical relation core: 66eef6601d0331a3a25303e8d358c2f164546e4ce9e4e88d7a8c81ef6507fd1c\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0005/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
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
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/stats/member_count/',
      'request_ref': 'r20260920-170620-c734:request:32'}]
    assertions = [{'assertion_id': 'v2-candidate-0017-business-01',
      'class': 'business',
      'predicate_type': 'P15',
      'predicate': {'collection': {'path': '$.stats', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P15',
                    'identity': {'paths': ['$.date'], 'semantics': 'strict-tuple'},
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0017-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0017-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.stats',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-c701879b114e1091cff7',
        candidate_id='v2-candidate-0017',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='16016dc948ac860ec8a3a0dbb01165b7093f67f9bd64a3281c46f7292ffcc839',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_5579bbec41a9574a1aff(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/stats/member_count/; business relation P19 requires observation $.meta.totals.free (integer) = sum(observation $.stats (array)); scope=actual_response, item={'path': '$.free', 'role': 'item', 'value_type': 'integer'}, factor=None, numeric_mode=exact, units={'item': 'members', 'output': 'members'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0019\nCanonical relation core: db1f989d4b24626ef5b0dd936d64309d129304e0e26df61205c4f3dbd1f8907d\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0006/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0019
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
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/stats/member_count/',
      'request_ref': 'r20260920-170620-c734:request:32'}]
    assertions = [{'assertion_id': 'v2-candidate-0019-business-01',
      'class': 'business',
      'predicate_type': 'P19',
      'predicate': {'collection': {'path': '$.stats', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P19',
                    'item': {'path': '$.free', 'role': 'item', 'value_type': 'integer'},
                    'numeric_mode': 'exact',
                    'operator': 'sum',
                    'output': {'path': '$.meta.totals.free',
                               'role': 'observation',
                               'value_type': 'integer'},
                    'scope': 'actual_response',
                    'units': {'evidence_refs': ['r20260920-170620-c734:request:32'],
                              'rationale': 'Daily free member counts sum to the total free count.',
                              'source': 'hypothesis',
                              'value': {'item': 'members', 'output': 'members'},
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
                    'target_path': '$.meta.totals.free',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-5579bbec41a9574a1aff',
        candidate_id='v2-candidate-0019',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='c6421d0e5228a96df17d35adbea50135e1f40f7d836c3f8650c06355c5a41e44',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_50cad0744b7315a5e91b(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/stats/member_count/; business relation P19 requires observation $.meta.totals.paid (integer) = sum(observation $.stats (array)); scope=actual_response, item={'path': '$.paid', 'role': 'item', 'value_type': 'integer'}, factor=None, numeric_mode=exact, units={'item': 'members', 'output': 'members'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0020\nCanonical relation core: b0c83452e89eccb014c1e98f01cdc66911827e287936f597201e7d46f0784d34\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0006/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0020
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
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/stats/member_count/',
      'request_ref': 'r20260920-170620-c734:request:32'}]
    assertions = [{'assertion_id': 'v2-candidate-0020-business-01',
      'class': 'business',
      'predicate_type': 'P19',
      'predicate': {'collection': {'path': '$.stats', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P19',
                    'item': {'path': '$.paid', 'role': 'item', 'value_type': 'integer'},
                    'numeric_mode': 'exact',
                    'operator': 'sum',
                    'output': {'path': '$.meta.totals.paid',
                               'role': 'observation',
                               'value_type': 'integer'},
                    'scope': 'actual_response',
                    'units': {'evidence_refs': ['r20260920-170620-c734:request:32'],
                              'rationale': 'Daily paid member counts sum to the total paid count.',
                              'source': 'hypothesis',
                              'value': {'item': 'members', 'output': 'members'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0020-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0020-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.totals.paid',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-50cad0744b7315a5e91b',
        candidate_id='v2-candidate-0020',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='0d3861eabf1d51e91a0f365d4a84f3f77e2b9c41725448e1afecc26e0ade8ee1',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_f6e59994bc878e3eb793(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/stats/member_count/; business relation P19 requires observation $.meta.totals.comped (integer) = sum(observation $.stats (array)); scope=actual_response, item={'path': '$.comped', 'role': 'item', 'value_type': 'integer'}, factor=None, numeric_mode=exact, units={'item': 'members', 'output': 'members'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0021\nCanonical relation core: aa9ed76d90c98754e95ea21c91d59d95cef91b5a82fbe76ec76956e48f8eb44c\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0006/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0021
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
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/stats/member_count/',
      'request_ref': 'r20260920-170620-c734:request:32'}]
    assertions = [{'assertion_id': 'v2-candidate-0021-business-01',
      'class': 'business',
      'predicate_type': 'P19',
      'predicate': {'collection': {'path': '$.stats', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P19',
                    'item': {'path': '$.comped', 'role': 'item', 'value_type': 'integer'},
                    'numeric_mode': 'exact',
                    'operator': 'sum',
                    'output': {'path': '$.meta.totals.comped',
                               'role': 'observation',
                               'value_type': 'integer'},
                    'scope': 'actual_response',
                    'units': {'evidence_refs': ['r20260920-170620-c734:request:32'],
                              'rationale': 'Daily comped member counts sum to the total comped count.',
                              'source': 'hypothesis',
                              'value': {'item': 'members', 'output': 'members'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0021-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0021-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.totals.comped',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-f6e59994bc878e3eb793',
        candidate_id='v2-candidate-0021',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='0a3cc2960fac080af46e22489c8efac4bf6aeef49243822d4a2f9fc9d5fb9fad',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_39129e71cc070c2ca51d(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P11 requires count(observation $.labels (array)) <= this request's query.limit; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0022\nCanonical relation core: 9d8a5e79a202b8e7dbaf99e00b10d262ded82ae7be7d74cd4403c68f4aa4312a\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0006/provider_response_envelope.json#content(from-json).candidates[5].rationale\n- ../attempts/attempt-0001/M10/calls/detail-0009/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0005/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0006/provider_response_envelope.json#content(from-json).candidates[3].rationale\n- ../attempts/attempt-0002/M10/calls/detail-0007/provider_response_envelope.json#content(from-json).candidates[4].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0005/provider_response_envelope.json#content(from-json).candidates[5].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0009/provider_response_envelope.json#content(from-json).candidates[4].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0022
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
      'phase': 'setup[6]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/members/',
      'request_ref': 'r20260920-170620-c734:request:33'},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:34'}]
    assertions = [{'assertion_id': 'v2-candidate-0022-business-01',
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
     {'assertion_id': 'v2-candidate-0022-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0022-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-39129e71cc070c2ca51d',
        candidate_id='v2-candidate-0022',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='647c4311a359ea862dba487dbe47ef8411a940a457f9906a457da6acaed792ff',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_488423f4eea9704a5d31(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/stats/member_count/; basic constraint P21 requires observation $.meta.totals.free (integer) to have JSON type integer; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0025\nCanonical relation core: 95b8532333f5f28f3fce82630a33ce0cfdbdebf8ea73c1cc97da91c8a474b47f\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0006/provider_response_envelope.json#content(from-json).candidates[12].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0025
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
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/stats/member_count/',
      'request_ref': 'r20260920-170620-c734:request:32'}]
    assertions = [{'assertion_id': 'v2-candidate-0025-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'integer',
                    'family': 'P21',
                    'target': {'path': '$.meta.totals.free',
                               'role': 'observation',
                               'value_type': 'integer'}}},
     {'assertion_id': 'v2-candidate-0025-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0025-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.totals.free',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-488423f4eea9704a5d31',
        candidate_id='v2-candidate-0025',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='a23ceb81b48233d59d80b17f7ea4b5cf880021b7be0c1f7dd2601fb7b2b0ad61',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_b718d922f6727bdd9624(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/stats/member_count/; basic constraint P01 requires field observation $.stats (array) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0026\nCanonical relation core: bc71973f07ef378a7019a901566003729fb6ddf07a2345aae3db36e7db2ea218\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0006/provider_response_envelope.json#content(from-json).candidates[13].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0026
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
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/stats/member_count/',
      'request_ref': 'r20260920-170620-c734:request:32'}]
    assertions = [{'assertion_id': 'v2-candidate-0026-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.stats', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0026-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0026-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.stats',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-b718d922f6727bdd9624',
        candidate_id='v2-candidate-0026',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='02a87274ae14ff95d6eb2b5206942896baf383d856958fb5b90b8b4a3adfbbaa',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_00b7aa9738d760e08941(uisemtest_runtime):
    "Business summary: Queries source_query actor_a GET /ghost/api/admin/labels/; followup_query:q1 actor_a GET /ghost/api/admin/labels/; business predicate P17 requires followup_query:q1 $.labels (array) equal source_query $.labels (array); representation=multiset, basis=full_json_value, projection=[], identity=None; query scope={'closures': [], 'scope': 'actual_response'}; input transform={'keys': ['limit', 'page'], 'kind': 'equivalent_input', 'location': 'query', 'semantics': {'evidence_refs': ['r20260920-170620-c734:request:43', 'r20260920-170620-c734:request:44'], 'rationale': 'Both recorded labels reads carry the same query selectors limit=100 and page=1; the frozen selector meaning is proposed equivalence, not a proven specification.', 'source': 'hypothesis', 'value': 'equivalent', 'value_type': 'string'}}.\nCandidate ID: v2-candidate-0030\nCanonical relation core: 226d0bd75172329395bb90b1777e60815ba9d1142b189a7de53341aea5580206\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0013/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V3: v2-candidate-0030
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'metamorphic_query', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'source_query/producer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:43'},
     {'kind': 'http',
      'phase': 'followup_query[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:44'}]
    assertions = [{'assertion_id': 'v2-candidate-0030-business-01',
      'class': 'business',
      'predicate_type': 'P17',
      'predicate': {'comparison_basis': 'full_json_value',
                    'expected_difference': None,
                    'family': 'P17',
                    'identity': None,
                    'left': {'path': '$.labels', 'role': 'followup_query:q1', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'representation': 'multiset',
                    'right': {'path': '$.labels', 'role': 'source_query', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0030-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0030-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0030-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-00b7aa9738d760e08941',
        candidate_id='v2-candidate-0030',
        protocol_kind='V3',
        normal_runs=1,
        source_test_sha256='8c0dc771354e7ef1559a97f20887a413502b2033c9b32bd12b026bd4d044f5ed',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_2466cea35c817d3a4aac(uisemtest_runtime):
    "Business summary: Queries source_query actor_a GET /ghost/api/admin/labels/; followup_query:q1 actor_a GET /ghost/api/admin/labels/; business predicate P17 requires followup_query:q1 $.labels (array) equal source_query $.labels (array); representation=multiset, basis=full_json_value, projection=[], identity=None; query scope={'closures': [], 'scope': 'actual_response'}; input transform={'keys': ['limit', 'page'], 'kind': 'equivalent_input', 'location': 'query', 'semantics': {'evidence_refs': ['r20260920-170620-c734:request:43', 'r20260920-170620-c734:request:44'], 'rationale': 'Both recorded actor_a labels GETs carry the same visible selectors limit=100 and page=1; only the recorded order differs.', 'source': 'hypothesis', 'value': 'equivalent', 'value_type': 'string'}}.\nCandidate ID: v2-candidate-0037\nCanonical relation core: 226d0bd75172329395bb90b1777e60815ba9d1142b189a7de53341aea5580206\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0014/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V3: v2-candidate-0037
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'metamorphic_query', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'source_query/producer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:43'},
     {'kind': 'http',
      'phase': 'followup_query[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:44'}]
    assertions = [{'assertion_id': 'v2-candidate-0037-business-01',
      'class': 'business',
      'predicate_type': 'P17',
      'predicate': {'comparison_basis': 'full_json_value',
                    'expected_difference': None,
                    'family': 'P17',
                    'identity': None,
                    'left': {'path': '$.labels', 'role': 'followup_query:q1', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'representation': 'multiset',
                    'right': {'path': '$.labels', 'role': 'source_query', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0037-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0037-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0037-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-2466cea35c817d3a4aac',
        candidate_id='v2-candidate-0037',
        protocol_kind='V3',
        normal_runs=1,
        source_test_sha256='62462fc4a6618567c3569f05ad21a771380afb688b66ab1a25837c83ebb53d9f',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_38bd68fdf75527164d4a(uisemtest_runtime):
    "Business summary: Queries source_query actor_a GET /ghost/api/admin/labels/; followup_query:q1 actor_a GET /ghost/api/admin/labels/; business predicate P17 requires followup_query:q1 $.labels (array) equal source_query $.labels (array); representation=multiset, basis=full_json_value, projection=[], identity=None; query scope={'closures': [], 'scope': 'actual_response'}; input transform={'keys': ['limit', 'page'], 'kind': 'equivalent_input', 'location': 'query', 'semantics': {'evidence_refs': ['r20260920-170620-c734:request:43', 'r20260920-170620-c734:request:44'], 'rationale': 'Both recorded /ghost/api/admin/labels/ reads carry exactly limit=100 and page=1 and no other selector, so the frozen selector relation is equivalent input.', 'source': 'hypothesis', 'value': 'equivalent', 'value_type': 'string'}}.\nCandidate ID: v2-candidate-0038\nCanonical relation core: 226d0bd75172329395bb90b1777e60815ba9d1142b189a7de53341aea5580206\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0016/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V3: v2-candidate-0038
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'metamorphic_query', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'source_query/producer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:43'},
     {'kind': 'http',
      'phase': 'followup_query[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:44'}]
    assertions = [{'assertion_id': 'v2-candidate-0038-business-01',
      'class': 'business',
      'predicate_type': 'P17',
      'predicate': {'comparison_basis': 'full_json_value',
                    'expected_difference': None,
                    'family': 'P17',
                    'identity': None,
                    'left': {'path': '$.labels', 'role': 'followup_query:q1', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'representation': 'multiset',
                    'right': {'path': '$.labels', 'role': 'source_query', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0038-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0038-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0038-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-38bd68fdf75527164d4a',
        candidate_id='v2-candidate-0038',
        protocol_kind='V3',
        normal_runs=1,
        source_test_sha256='ad28751aba9b165275d15956016b269dfe2de4f705466108737cad4e033223be',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_7a6b3b7254630699b43b(uisemtest_runtime):
    "Business summary: Queries source_query actor_a GET /ghost/api/admin/labels/; followup_query:q1 actor_a GET /ghost/api/admin/labels/; business predicate P17 requires followup_query:q1 $.labels (array) equal source_query $.labels (array); representation=multiset, basis=full_json_value, projection=[], identity=None; query scope={'closures': [], 'scope': 'actual_response'}; input transform={'keys': ['limit', 'page'], 'kind': 'equivalent_input', 'location': 'query', 'semantics': {'evidence_refs': ['r20260920-170620-c734:request:43', 'r20260920-170620-c734:request:44'], 'rationale': 'Both recorded reads target the same labels path with identical visible selectors limit=100 and page=1; the frozen hypothesis is that the follow-up selector is an equivalent input, so the returned label collections should be equal as a multiset.', 'source': 'hypothesis', 'value': 'equivalent', 'value_type': 'string'}}.\nCandidate ID: v2-candidate-0040\nCanonical relation core: 226d0bd75172329395bb90b1777e60815ba9d1142b189a7de53341aea5580206\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0018/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V3: v2-candidate-0040
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'metamorphic_query', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'source_query/producer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:43'},
     {'kind': 'http',
      'phase': 'followup_query[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:44'}]
    assertions = [{'assertion_id': 'v2-candidate-0040-business-01',
      'class': 'business',
      'predicate_type': 'P17',
      'predicate': {'comparison_basis': 'full_json_value',
                    'expected_difference': None,
                    'family': 'P17',
                    'identity': None,
                    'left': {'path': '$.labels', 'role': 'followup_query:q1', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'representation': 'multiset',
                    'right': {'path': '$.labels', 'role': 'source_query', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0040-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0040-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0040-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-7a6b3b7254630699b43b',
        candidate_id='v2-candidate-0040',
        protocol_kind='V3',
        normal_runs=1,
        source_test_sha256='e3cac6af28f201a9d1614278892142af511aed111f44b89faac2c94f4e6d76d9',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_ac2f5e843b9610eca1c3(uisemtest_runtime):
    "Business summary: Queries source_query actor_a GET /ghost/api/admin/labels/; followup_query:q1 actor_a GET /ghost/api/admin/labels/; business predicate P17 requires followup_query:q1 $.labels (array) equal source_query $.labels (array); representation=multiset, basis=full_json_value, projection=[], identity=None; query scope={'closures': [], 'scope': 'actual_response'}; input transform={'keys': ['limit', 'page'], 'kind': 'equivalent_input', 'location': 'query', 'semantics': {'evidence_refs': ['r20260920-170620-c734:request:43', 'r20260920-170620-c734:request:44'], 'rationale': 'Both recorded label reads carry identical query selectors limit=100 and page=1, so the observed selector change is proposed to be an equivalent input.', 'source': 'hypothesis', 'value': 'equivalent', 'value_type': 'string'}}.\nCandidate ID: v2-candidate-0046\nCanonical relation core: 226d0bd75172329395bb90b1777e60815ba9d1142b189a7de53341aea5580206\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0001/M10/calls/detail-0021/provider_response_envelope.json#content(from-json).candidates[5].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V3: v2-candidate-0046
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'metamorphic_query', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'source_query/producer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:43'},
     {'kind': 'http',
      'phase': 'followup_query[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:44'}]
    assertions = [{'assertion_id': 'v2-candidate-0046-business-01',
      'class': 'business',
      'predicate_type': 'P17',
      'predicate': {'comparison_basis': 'full_json_value',
                    'expected_difference': None,
                    'family': 'P17',
                    'identity': None,
                    'left': {'path': '$.labels', 'role': 'followup_query:q1', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'representation': 'multiset',
                    'right': {'path': '$.labels', 'role': 'source_query', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0046-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0046-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0046-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-ac2f5e843b9610eca1c3',
        candidate_id='v2-candidate-0046',
        protocol_kind='V3',
        normal_runs=1,
        source_test_sha256='4dec26a130e748e052c8ee41c51ea06763e1642903f5896a0936360c39ccf058',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_f3e1be605b181e149dea(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P21 requires observation $ (object) to have JSON type object; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0047\nCanonical relation core: 6be9cd55f5243feda9f58ae12d1eb0399cd531446f1cdaac292c570d0c1c7be3\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0047
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0047-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'object',
                    'family': 'P21',
                    'target': {'path': '$', 'role': 'observation', 'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0047-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0047-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'object',
                    'response_ref': 'observation',
                    'target_path': '$',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-f3e1be605b181e149dea',
        candidate_id='v2-candidate-0047',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='f2571a14f7bcc7a8c9db68a1c2ccd26bac085320062e1fc9cc50a93478686d14',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_bf1a63ade88ea999259a(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P21 requires observation $.labels (array) to have JSON type array; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0048\nCanonical relation core: 1bf4e2330e20b909459352c461015f87f50ce9c31b8a1b663cad9acd77ee374e\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0048
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0048-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'array',
                    'family': 'P21',
                    'target': {'path': '$.labels', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0048-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0048-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-bf1a63ade88ea999259a',
        candidate_id='v2-candidate-0048',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='426d6073774fc68234ad38b0c46a50d557522951f76e5680abc1fb57d40d7ce7',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_2648ec7c8ab868fcb20a(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P21 requires observation $.meta (object) to have JSON type object; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0049\nCanonical relation core: 9aee90e8721e5c00ad523da6e05db65cd7256fda3e8eab6e14a0eaeb27dd15cb\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0049
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0049-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'object',
                    'family': 'P21',
                    'target': {'path': '$.meta', 'role': 'observation', 'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0049-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0049-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'object',
                    'response_ref': 'observation',
                    'target_path': '$.meta',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-2648ec7c8ab868fcb20a',
        candidate_id='v2-candidate-0049',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='521a1087b94b2d9f3252a24fff7d717a24fd8fbd91f40248e18b59fa1804f2f2',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_43ad3ad047bae8949077(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P21 requires observation $.meta.pagination (object) to have JSON type object; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0050\nCanonical relation core: 77cec239228ba7d37d9de5b73241d67fb0dda89089a2d2d15557c1a9195577e4\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0050
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0050-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'object',
                    'family': 'P21',
                    'target': {'path': '$.meta.pagination',
                               'role': 'observation',
                               'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0050-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0050-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'object',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-43ad3ad047bae8949077',
        candidate_id='v2-candidate-0050',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='625c45177e0aeeeae1544026e2e32d6c8d806b39599f66831fb7a6cb7a4fb44c',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_5b544e3ea6efb0e99eaf(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P21 requires observation $.meta.pagination.limit (integer) to have JSON type integer; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0051\nCanonical relation core: 51adf6de632f36a3f7a0f1dff32b0e3329586b5f6804f5398bf4621171eecbb6\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[4].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0051
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0051-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'integer',
                    'family': 'P21',
                    'target': {'path': '$.meta.pagination.limit',
                               'role': 'observation',
                               'value_type': 'integer'}}},
     {'assertion_id': 'v2-candidate-0051-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0051-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.limit',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-5b544e3ea6efb0e99eaf',
        candidate_id='v2-candidate-0051',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='e1e1345b857f552d837ab33726f2e7c9f7616f5ef11ee5019dea5aadd0be33fc',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_401dbb35d5ecb4ce5d28(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P21 requires observation $.meta.pagination.next (null) to have JSON type null; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0052\nCanonical relation core: a6779e7a7fd53f8547570e22e6d070ac2fb446b0cb43be17432015dbd467c188\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[5].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0052
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0052-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'null',
                    'family': 'P21',
                    'target': {'path': '$.meta.pagination.next',
                               'role': 'observation',
                               'value_type': 'null'}}},
     {'assertion_id': 'v2-candidate-0052-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0052-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'null',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.next',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-401dbb35d5ecb4ce5d28',
        candidate_id='v2-candidate-0052',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='e40bf540d502618b6646edf86d1cb2f6f1272032f6963a837b965c36dfeaf0e0',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_22a55620cf64a9435ad4(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P21 requires observation $.meta.pagination.page (integer) to have JSON type integer; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0053\nCanonical relation core: bf82b0c164fb5f165071672afa29e3f3ce75829abb9c7bcdbba525d1a62a6af6\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[6].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0053
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0053-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'integer',
                    'family': 'P21',
                    'target': {'path': '$.meta.pagination.page',
                               'role': 'observation',
                               'value_type': 'integer'}}},
     {'assertion_id': 'v2-candidate-0053-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0053-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.page',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-22a55620cf64a9435ad4',
        candidate_id='v2-candidate-0053',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='77e0be549b22e5934be9dd224fd1fafce8caf486b4ac6ec260ab7900c852b233',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_1a20077f5d022b3ca34f(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P21 requires observation $.meta.pagination.pages (integer) to have JSON type integer; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0054\nCanonical relation core: cf4b35b8d837d95e6fd2827b75901f10f426587fe7b54faf388cbc1ba9628fd8\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[7].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0054
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0054-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'integer',
                    'family': 'P21',
                    'target': {'path': '$.meta.pagination.pages',
                               'role': 'observation',
                               'value_type': 'integer'}}},
     {'assertion_id': 'v2-candidate-0054-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0054-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.pages',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-1a20077f5d022b3ca34f',
        candidate_id='v2-candidate-0054',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='2b5dea33b407a9e8bafb87c142a7a599f188555295c8f8b5b55a9bbce91f4999',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_c2f310d9dfa2b834400e(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P21 requires observation $.meta.pagination.prev (null) to have JSON type null; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0055\nCanonical relation core: 52a3e09ab2e6b9e3d9e601e832ad367c1ef7d56bba0f11f02598f4f9690aea4a\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[8].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0055
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0055-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'null',
                    'family': 'P21',
                    'target': {'path': '$.meta.pagination.prev',
                               'role': 'observation',
                               'value_type': 'null'}}},
     {'assertion_id': 'v2-candidate-0055-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0055-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'null',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.prev',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-c2f310d9dfa2b834400e',
        candidate_id='v2-candidate-0055',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='1a19faa7cb10ab081cb10bfc77194502e8e6172ff64105f993ef71a7b86172e0',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_f9ed14d93531fb4d1004(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P21 requires observation $.meta.pagination.total (integer) to have JSON type integer; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0056\nCanonical relation core: d7ec1bce7b1672e68373c4ebe98fefc3c151a6036c7de785717c70e5d91e17a7\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[9].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0056
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0056-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'integer',
                    'family': 'P21',
                    'target': {'path': '$.meta.pagination.total',
                               'role': 'observation',
                               'value_type': 'integer'}}},
     {'assertion_id': 'v2-candidate-0056-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0056-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.total',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-f9ed14d93531fb4d1004',
        candidate_id='v2-candidate-0056',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='9ea5181ba6ec6444143b44da264b5cfb2712d4327a9a2422fe5206bccb79db0c',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_6ada759094d17e3b191b(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P01 requires field observation $.labels (array) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0057\nCanonical relation core: aea18ef3894638389e664599ab7e7f73dd06ac566b6b2aa4b0c196bd820d1d1b\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[10].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0057
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0057-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.labels', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0057-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0057-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-6ada759094d17e3b191b',
        candidate_id='v2-candidate-0057',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='cb2ef5615f6ef18656e061bc63d4cdf65651f881d2d57acfd61109ee0dc69e8d',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_46312c242032a99c8554(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P01 requires field observation $.meta (object) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0058\nCanonical relation core: c8ecbd97591d1f028ac11885eee09786c55a0e421eeda42b628e6841f83501f0\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[11].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0058
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0058-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.meta', 'role': 'observation', 'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0058-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0058-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'object',
                    'response_ref': 'observation',
                    'target_path': '$.meta',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-46312c242032a99c8554',
        candidate_id='v2-candidate-0058',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='dd58d218c78be034dd09fb05984a9a589b236c9b9ef7bb2c78681caa0322fa3e',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_88ff3ee7f41ab607cd88(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P02 requires observation $.meta.pagination.limit (integer) to numerically equal actual request query $.limit (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0059\nCanonical relation core: a81e9395cdf7fcc5dee1ac1cb7c7daa0da896d7ae63ece3acf5e2edb8a939678\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[13].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0059
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0059-business-01',
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
     {'assertion_id': 'v2-candidate-0059-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0059-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.limit',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-88ff3ee7f41ab607cd88',
        candidate_id='v2-candidate-0059',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='89bfcc90362e7ff5513f630e1a921be5903dae8270498b4953ff122323ff98da',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_e01bcadea1abbc87b5dd(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P02 requires observation $.meta.pagination.page (integer) to numerically equal actual request query $.page (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0060\nCanonical relation core: f5cef59ce040adf3c39373e0861c15cc381f519af4bf2722fbe45879fe4557c2\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[14].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0060
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0060-business-01',
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
     {'assertion_id': 'v2-candidate-0060-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0060-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.page',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-e01bcadea1abbc87b5dd',
        candidate_id='v2-candidate-0060',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='14e3c0ae4d9ba49f4ef2dfa7b403c09ab17829e9dff8a3349c0d1ec4f1d97be6',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_439c272f729314b01dd9(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint P21 requires observation $ (object) to have JSON type object; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0061\nCanonical relation core: 1206b8246abdd6c8572c4e10787ac68bb3ae11a72dfbd3c9ebf73bf66dca9c5d\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[15].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0061
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
    assertions = [{'assertion_id': 'v2-candidate-0061-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'object',
                    'family': 'P21',
                    'target': {'path': '$', 'role': 'observation', 'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0061-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0061-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'object',
                    'response_ref': 'observation',
                    'target_path': '$',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-439c272f729314b01dd9',
        candidate_id='v2-candidate-0061',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='3b2547fba5a8efdd383663b6fe43fd45649b9d7734e995e3d76077997bfd292e',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_eb8be89ee4f24fdbe3c8(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint P21 requires observation $.tiers (array) to have JSON type array; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0062\nCanonical relation core: ebfd633549f2c47aab96bb9c15c212340abfa9ce2ba67d7b77a658ceb9fb9fbf\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[16].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0062
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
    assertions = [{'assertion_id': 'v2-candidate-0062-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'array',
                    'family': 'P21',
                    'target': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0062-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0062-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-eb8be89ee4f24fdbe3c8',
        candidate_id='v2-candidate-0062',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='82a0c34360d037195e7c806f2e147cd62efd5bb3d715e00bfa729b00b7cc211c',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_6738a1a736a88d3d3a69(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint P21 requires observation $.meta (object) to have JSON type object; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0063\nCanonical relation core: 9da7378629213e51e2de44e58701c1712adbabdb02e18f5eb2e2618d8cc959fe\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[17].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0063
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
    assertions = [{'assertion_id': 'v2-candidate-0063-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'object',
                    'family': 'P21',
                    'target': {'path': '$.meta', 'role': 'observation', 'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0063-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0063-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'object',
                    'response_ref': 'observation',
                    'target_path': '$.meta',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-6738a1a736a88d3d3a69',
        candidate_id='v2-candidate-0063',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='d143ed80f71b597cad08685510a274d10840322dbd9ae9a9072a196dfaae0c5c',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_93ff91a5b1dfccbd4d26(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint P21 requires observation $.meta.pagination (object) to have JSON type object; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0064\nCanonical relation core: 7f3ba86df1d29412818290886fc3b0f6ecf33f86dd38e79f8495873d4f8f1cab\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[18].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0064
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
    assertions = [{'assertion_id': 'v2-candidate-0064-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'object',
                    'family': 'P21',
                    'target': {'path': '$.meta.pagination',
                               'role': 'observation',
                               'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0064-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0064-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'object',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-93ff91a5b1dfccbd4d26',
        candidate_id='v2-candidate-0064',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='f4b9674f85369aa3637f7430607cafbaaac770a18bedd55fec855cadcc103b66',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_66ba37a6c453de5dccdb(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint P21 requires observation $.meta.pagination.limit (integer) to have JSON type integer; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0065\nCanonical relation core: b9708f0a0a5a8a02a47a207b8424957cd45848ac6ab0dd342b86338603c21867\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[19].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0065
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
    assertions = [{'assertion_id': 'v2-candidate-0065-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'integer',
                    'family': 'P21',
                    'target': {'path': '$.meta.pagination.limit',
                               'role': 'observation',
                               'value_type': 'integer'}}},
     {'assertion_id': 'v2-candidate-0065-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0065-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.limit',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-66ba37a6c453de5dccdb',
        candidate_id='v2-candidate-0065',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='a9d661722e55608b299c137e5c608616e512822ebfa615280acf0bcd00d64147',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_f7591a7d478e82ce0b1b(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint P21 requires observation $.meta.pagination.next (null) to have JSON type null; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0066\nCanonical relation core: 72fde66d864b26b8ffbb68af17b84f3c1265494f4118acd619362b4627a77f4f\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[20].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0066
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
    assertions = [{'assertion_id': 'v2-candidate-0066-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'null',
                    'family': 'P21',
                    'target': {'path': '$.meta.pagination.next',
                               'role': 'observation',
                               'value_type': 'null'}}},
     {'assertion_id': 'v2-candidate-0066-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0066-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'null',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.next',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-f7591a7d478e82ce0b1b',
        candidate_id='v2-candidate-0066',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='221714014d490d87ea4763d220958d36d21bddca7c0b44e8074d6c81124c079a',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_96baa806a45507f42e72(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint P21 requires observation $.meta.pagination.page (integer) to have JSON type integer; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0067\nCanonical relation core: 3fdc69aad624321bda85cdca35204a7f6b08d637e23b1ed7e096946e7920a0ca\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[21].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0067
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
    assertions = [{'assertion_id': 'v2-candidate-0067-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'integer',
                    'family': 'P21',
                    'target': {'path': '$.meta.pagination.page',
                               'role': 'observation',
                               'value_type': 'integer'}}},
     {'assertion_id': 'v2-candidate-0067-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0067-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.page',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-96baa806a45507f42e72',
        candidate_id='v2-candidate-0067',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='613d5a63154f3bd3dde3499b3287ba9468e01b55d94518f8ec5c3f4745334aa0',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_54e86e317534ee59f548(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint P21 requires observation $.meta.pagination.pages (integer) to have JSON type integer; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0068\nCanonical relation core: 0707eae3f480d2b8c1b6c3a0eeb84286824df8a5cf5c9ef5c5fba9fed0c25a59\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[22].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0068
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
    assertions = [{'assertion_id': 'v2-candidate-0068-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'integer',
                    'family': 'P21',
                    'target': {'path': '$.meta.pagination.pages',
                               'role': 'observation',
                               'value_type': 'integer'}}},
     {'assertion_id': 'v2-candidate-0068-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0068-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.pages',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-54e86e317534ee59f548',
        candidate_id='v2-candidate-0068',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='ac76909123d5922def37232ac79bdee35e931c2b8db44dac96005a2109586434',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_035f880dae6983cc9d53(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint P21 requires observation $.meta.pagination.prev (null) to have JSON type null; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0069\nCanonical relation core: df06b7ff72ca6da690b37e52be4d5abe448adad57559d77f0b9e34ad627f29b8\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[23].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0069
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
    assertions = [{'assertion_id': 'v2-candidate-0069-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'null',
                    'family': 'P21',
                    'target': {'path': '$.meta.pagination.prev',
                               'role': 'observation',
                               'value_type': 'null'}}},
     {'assertion_id': 'v2-candidate-0069-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0069-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'null',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.prev',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-035f880dae6983cc9d53',
        candidate_id='v2-candidate-0069',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='aa1a31c4e297d34302ff48a36cd000f45474c0f914ca57d2b812093b652a0f68',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_76587c472035cab92dff(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint P21 requires observation $.meta.pagination.total (integer) to have JSON type integer; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0070\nCanonical relation core: 9fb5b9a26ca188d4a1c58901d44b723b435472e8c0263c5c3e898eacdb7e601c\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[24].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0070
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
    assertions = [{'assertion_id': 'v2-candidate-0070-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'integer',
                    'family': 'P21',
                    'target': {'path': '$.meta.pagination.total',
                               'role': 'observation',
                               'value_type': 'integer'}}},
     {'assertion_id': 'v2-candidate-0070-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0070-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.total',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-76587c472035cab92dff',
        candidate_id='v2-candidate-0070',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='a7bdd683292cfd761bcba05cce61c93d39f93d5237c26e5f6a3c1c2fd86f1f9a',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_ebf231d964b25ae71ee0(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint P01 requires field observation $.tiers (array) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0071\nCanonical relation core: 4455d92f4b5a11660326199cae6b32ec2935200438a7a1d8d1488632ffa6e0c5\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[25].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0071
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
    assertions = [{'assertion_id': 'v2-candidate-0071-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0071-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0071-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-ebf231d964b25ae71ee0',
        candidate_id='v2-candidate-0071',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='03cc79b8950b61b5519e66488d519f4ab887bf5d41052a4f994ede36cfb59619',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_33805a3737cabbd4b7b3(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint P01 requires field observation $.meta (object) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0072\nCanonical relation core: 10bf9a9dece3eee6de20a0ccc3dddfa5efb7391f9753d5e85f7bc09ec743fffd\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[26].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0072
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
    assertions = [{'assertion_id': 'v2-candidate-0072-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.meta', 'role': 'observation', 'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0072-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0072-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'object',
                    'response_ref': 'observation',
                    'target_path': '$.meta',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-33805a3737cabbd4b7b3',
        candidate_id='v2-candidate-0072',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='f62275c851c19a72461297d21b081ae16fe18e8651400cf8ae355486934c4719',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_11c82319942fac2b8d3f(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint For every member of observation $.tiers (array) in actual_response: P21 requires item $.id (string) to have JSON type string; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0073\nCanonical relation core: 4ed4cc351002c1a743bf0a82cb9dca9177b420c463dc555abd0343bb15a2b976\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[28].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0073
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
    assertions = [{'assertion_id': 'v2-candidate-0073-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'expected_type': 'string',
                             'family': 'P21',
                             'target': {'path': '$.id', 'role': 'item', 'value_type': 'string'}},
                    'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0073-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0073-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-11c82319942fac2b8d3f',
        candidate_id='v2-candidate-0073',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='120b56bf27849529709ba0bf29e45fbeac2464dee2bdf82182471815a959cf59',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_0cc70d34ed538bb4a3de(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint For every member of observation $.tiers (array) in actual_response: P21 requires item $.name (string) to have JSON type string; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0074\nCanonical relation core: 36c8e38c027ca1172d824f018326210e5a37a7e29ef0d2175cdffcba3ffe8320\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[29].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0074
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
    assertions = [{'assertion_id': 'v2-candidate-0074-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'expected_type': 'string',
                             'family': 'P21',
                             'target': {'path': '$.name', 'role': 'item', 'value_type': 'string'}},
                    'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0074-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0074-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-0cc70d34ed538bb4a3de',
        candidate_id='v2-candidate-0074',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='e5dad98db05b6da89e86146a78b78e6260028613b1243e91006c6c55e05328b4',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_f033e507cb5359c06614(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint For every member of observation $.tiers (array) in actual_response: P21 requires item $.active (boolean) to have JSON type boolean; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0075\nCanonical relation core: 1140712877ae0391bd921e43b4e04d5f426dcbf7dccbe79338040f8486f32d89\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[30].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0075
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
    assertions = [{'assertion_id': 'v2-candidate-0075-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'expected_type': 'boolean',
                             'family': 'P21',
                             'target': {'path': '$.active', 'role': 'item', 'value_type': 'boolean'}},
                    'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0075-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0075-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-f033e507cb5359c06614',
        candidate_id='v2-candidate-0075',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='6efa3d0b095d344eae2421ee186253d56a1e27e2a29d560db49d799c1a34bcb2',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_45a34a4cca4757190aec(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint For every member of observation $.tiers (array) in actual_response: P21 requires item $.monthly_price (integer) to have JSON type integer; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0076\nCanonical relation core: a6f8f2e3faf7e4e73aef143b1b7819d150a8f09e404bf4db5fa2bcecfc208a2c\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[31].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0076
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
    assertions = [{'assertion_id': 'v2-candidate-0076-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'expected_type': 'integer',
                             'family': 'P21',
                             'target': {'path': '$.monthly_price',
                                        'role': 'item',
                                        'value_type': 'integer'}},
                    'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0076-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0076-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-45a34a4cca4757190aec',
        candidate_id='v2-candidate-0076',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='5817980406aa03d873c0bc4a7fdf1e812b57ecf90adca246bc6302484d1d7360',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_b33306354c85fbaf400d(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint For every member of observation $.tiers (array) in actual_response: P21 requires item $.yearly_price (integer) to have JSON type integer; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0077\nCanonical relation core: 45e42d4719b18d409a6c760240583339c274879229ba0702b88aa7353d7a66f5\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[32].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0077
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
    assertions = [{'assertion_id': 'v2-candidate-0077-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'expected_type': 'integer',
                             'family': 'P21',
                             'target': {'path': '$.yearly_price',
                                        'role': 'item',
                                        'value_type': 'integer'}},
                    'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0077-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0077-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-b33306354c85fbaf400d',
        candidate_id='v2-candidate-0077',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='0ebbb535bc235cc6ba625579a8a3b80c3ab722f41159f56ef1aff0b2969cbe20',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_2622cc96a0aa905ea190(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint For every member of observation $.tiers (array) in actual_response: P21 requires item $.currency (string) to have JSON type string; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0078\nCanonical relation core: 27843c013868fca232345e518c01d7e1a11b744817dd7d22d8ecfd7123dcf700\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[33].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0078
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
    assertions = [{'assertion_id': 'v2-candidate-0078-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'expected_type': 'string',
                             'family': 'P21',
                             'target': {'path': '$.currency', 'role': 'item', 'value_type': 'string'}},
                    'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0078-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0078-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-2622cc96a0aa905ea190',
        candidate_id='v2-candidate-0078',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='5845f01c937e4f5775a17433710326ab791f1e1971434b41bea02c5ec94e0998',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_bdcceff8216a5464f266(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint For every member of observation $.tiers (array) in actual_response: P21 requires item $.slug (string) to have JSON type string; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0079\nCanonical relation core: 2fd065adbfb33556da22efb84df360a406a7c54db9154be7a44fb85a31547f98\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[34].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0079
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
    assertions = [{'assertion_id': 'v2-candidate-0079-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'expected_type': 'string',
                             'family': 'P21',
                             'target': {'path': '$.slug', 'role': 'item', 'value_type': 'string'}},
                    'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0079-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0079-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-bdcceff8216a5464f266',
        candidate_id='v2-candidate-0079',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='aea79f1812e65c42c53ca2af60c83fcbf04437664042d6b3ae668665e9c47a2c',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_5a155e39a8ed0c8026c7(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint For every member of observation $.tiers (array) in actual_response: P21 requires item $.type (string) to have JSON type string; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0080\nCanonical relation core: de04ae2bebfb59f845a6daf413d22df90017ccad303ef6c89fa2b76abca5a02b\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[35].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0080
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
    assertions = [{'assertion_id': 'v2-candidate-0080-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'expected_type': 'string',
                             'family': 'P21',
                             'target': {'path': '$.type', 'role': 'item', 'value_type': 'string'}},
                    'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0080-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0080-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-5a155e39a8ed0c8026c7',
        candidate_id='v2-candidate-0080',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='e92925fa4a87ca7444bdf1a2ba4cd650638f90f431a99d5fb846d27f6ed5fc2f',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_cf8dc2576dca7b649e73(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint For every member of observation $.tiers (array) in actual_response: P21 requires item $.visibility (string) to have JSON type string; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0081\nCanonical relation core: f78dd5e76b63ed0e30c679c55333b481e6c295a0f5f0ebb0438b855a75519eac\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[36].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0081
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
    assertions = [{'assertion_id': 'v2-candidate-0081-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'expected_type': 'string',
                             'family': 'P21',
                             'target': {'path': '$.visibility',
                                        'role': 'item',
                                        'value_type': 'string'}},
                    'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0081-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0081-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-cf8dc2576dca7b649e73',
        candidate_id='v2-candidate-0081',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='7e740522c82109df825674df78482b4042a71e7ef35a510583c5148d05c7ab9f',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_fa7472362e05238f713a(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint P21 requires observation $ (object) to have JSON type object; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0082\nCanonical relation core: d7feac3e89f1005164c6765e58d1dcbb7658e9ad5b0a928e19980a6ceefe09e9\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[39].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0082
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
    assertions = [{'assertion_id': 'v2-candidate-0082-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'object',
                    'family': 'P21',
                    'target': {'path': '$', 'role': 'observation', 'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0082-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0082-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'object',
                    'response_ref': 'observation',
                    'target_path': '$',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-fa7472362e05238f713a',
        candidate_id='v2-candidate-0082',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='18055321e6b11351643b0220ee6bacb9c4490820f102a21b330a4ac430a7dab2',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_98f893faa1d56a63d70d(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint P21 requires observation $.newsletters (array) to have JSON type array; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0083\nCanonical relation core: ad65c0f0bef8a983bbb9383eeef84b424c34a22e98c938a6dab306153fbfc5a2\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[40].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0083
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
    assertions = [{'assertion_id': 'v2-candidate-0083-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'array',
                    'family': 'P21',
                    'target': {'path': '$.newsletters', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0083-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0083-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.newsletters',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-98f893faa1d56a63d70d',
        candidate_id='v2-candidate-0083',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='a4d06993724ebfa44f34753872d7ba84144b300851a91a8f0cdb4841f0c0bc6f',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_582afa70f02f9bd72fdd(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint P21 requires observation $.meta (object) to have JSON type object; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0084\nCanonical relation core: fe8724a71512e586ef4e1e2a21964bd6cc69b95b9f98b045e277290c70f9b34f\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[41].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0084
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
    assertions = [{'assertion_id': 'v2-candidate-0084-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'object',
                    'family': 'P21',
                    'target': {'path': '$.meta', 'role': 'observation', 'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0084-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0084-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'object',
                    'response_ref': 'observation',
                    'target_path': '$.meta',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-582afa70f02f9bd72fdd',
        candidate_id='v2-candidate-0084',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='e090b77af8fe677aa164a3b41267a86455285d7e969c1c07818ef3736f294a0a',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_d19b08d70b08c790eb9c(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint P21 requires observation $.meta.pagination (object) to have JSON type object; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0085\nCanonical relation core: 99f073a2d1a5670e826a724be711442ce5043f97749eb27b28bee19eeb6ecd9e\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[42].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0085
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
    assertions = [{'assertion_id': 'v2-candidate-0085-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'object',
                    'family': 'P21',
                    'target': {'path': '$.meta.pagination',
                               'role': 'observation',
                               'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0085-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0085-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'object',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-d19b08d70b08c790eb9c',
        candidate_id='v2-candidate-0085',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='f5eb114a04a226118317b0df7a4dc1de869bf4b85caffa3dd72c912d6c18b516',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_aed1e94dbce2dd92f8d4(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint P21 requires observation $.meta.pagination.limit (integer) to have JSON type integer; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0086\nCanonical relation core: c73ece29301cc041bb59b75415c452571ddca53930a613f148bbb7b626a95dfa\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[43].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0086
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
    assertions = [{'assertion_id': 'v2-candidate-0086-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'integer',
                    'family': 'P21',
                    'target': {'path': '$.meta.pagination.limit',
                               'role': 'observation',
                               'value_type': 'integer'}}},
     {'assertion_id': 'v2-candidate-0086-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0086-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.limit',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-aed1e94dbce2dd92f8d4',
        candidate_id='v2-candidate-0086',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='7050237fb0578c5c121e71d9846c11e003eacb5cd2ec65a3f6e58da3be28c860',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_a7d46501b58ba5d30bbb(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint P21 requires observation $.meta.pagination.next (null) to have JSON type null; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0087\nCanonical relation core: 0c3e73328d0b7d2615ac6f366b5c5fba98c8ea173a37895606642a5a4f1ebef0\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[44].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0087
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
    assertions = [{'assertion_id': 'v2-candidate-0087-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'null',
                    'family': 'P21',
                    'target': {'path': '$.meta.pagination.next',
                               'role': 'observation',
                               'value_type': 'null'}}},
     {'assertion_id': 'v2-candidate-0087-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0087-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'null',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.next',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-a7d46501b58ba5d30bbb',
        candidate_id='v2-candidate-0087',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='d3e7d7b9320bfdfdde800e495c52c1e919ba7d9f25643603543a85d4e7438ace',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_1d0b1792b7544013d052(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint P21 requires observation $.meta.pagination.page (integer) to have JSON type integer; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0088\nCanonical relation core: 0c979359892cccc2a06b0ad1bb9350cceb9d6e41dad5b8f15abedf13c8bcc7e1\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[45].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0088
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
    assertions = [{'assertion_id': 'v2-candidate-0088-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'integer',
                    'family': 'P21',
                    'target': {'path': '$.meta.pagination.page',
                               'role': 'observation',
                               'value_type': 'integer'}}},
     {'assertion_id': 'v2-candidate-0088-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0088-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.page',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-1d0b1792b7544013d052',
        candidate_id='v2-candidate-0088',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='f818a069922d63aaf64bf85ef90ee1fd999765136787a899b732471bcf419b59',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_0f2be490f96d67d0f39b(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint P21 requires observation $.meta.pagination.pages (integer) to have JSON type integer; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0089\nCanonical relation core: 7308a810f8b8052df2be845d374609beca45aa92387188747b97623bf10de84b\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[46].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0089
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
    assertions = [{'assertion_id': 'v2-candidate-0089-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'integer',
                    'family': 'P21',
                    'target': {'path': '$.meta.pagination.pages',
                               'role': 'observation',
                               'value_type': 'integer'}}},
     {'assertion_id': 'v2-candidate-0089-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0089-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.pages',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-0f2be490f96d67d0f39b',
        candidate_id='v2-candidate-0089',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='09a07531ff7806cb84d101d9d674e86a8c3e98dd7d7982e20dd1a01f05b7a336',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_46286f9fb448c5298b10(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint P21 requires observation $.meta.pagination.prev (null) to have JSON type null; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0090\nCanonical relation core: 1e9e56bf6a027a680a1df48bea7375dd1691ebbf1a6c5225e12c4ca654f65527\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[47].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0090
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
    assertions = [{'assertion_id': 'v2-candidate-0090-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'null',
                    'family': 'P21',
                    'target': {'path': '$.meta.pagination.prev',
                               'role': 'observation',
                               'value_type': 'null'}}},
     {'assertion_id': 'v2-candidate-0090-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0090-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'null',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.prev',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-46286f9fb448c5298b10',
        candidate_id='v2-candidate-0090',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='60ce5f5f06058459a68dc58a7ec7497726eaf60b3e1f54c786f8f4ee888d0aca',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_fd8b21420788b94c154e(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint P21 requires observation $.meta.pagination.total (integer) to have JSON type integer; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0091\nCanonical relation core: 7659cb044b2d4f42392b455bf634ec3b0f3383f65a389e8b284cf7c19942a258\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[48].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0091
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
    assertions = [{'assertion_id': 'v2-candidate-0091-business-01',
      'class': 'business',
      'predicate_type': 'P21',
      'predicate': {'expected_type': 'integer',
                    'family': 'P21',
                    'target': {'path': '$.meta.pagination.total',
                               'role': 'observation',
                               'value_type': 'integer'}}},
     {'assertion_id': 'v2-candidate-0091-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0091-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.total',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-fd8b21420788b94c154e',
        candidate_id='v2-candidate-0091',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='2216aaa1e286ca46381316c9f972a33805d682d751107691b6f812326db2d280',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_213388a2ada50a573815(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint P01 requires field observation $.newsletters (array) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0092\nCanonical relation core: d3d736e6ad8ffdf044253a23bc534895da722af770079ce1209922c3bdd0ea0f\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[49].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0092
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
    assertions = [{'assertion_id': 'v2-candidate-0092-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.newsletters', 'role': 'observation', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0092-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0092-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.newsletters',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-213388a2ada50a573815',
        candidate_id='v2-candidate-0092',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='a42eb2c2590a17d45f31b67beea688d00035a724f99d63eb357e678868fd1067',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_a5e3c00a7cc62da3a6ab(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint P01 requires field observation $.meta (object) to be present; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0093\nCanonical relation core: 1847a8f7ec81618fef8cff0bc89a4d823805f4e0c008ffba51cd02cc3a447e71\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[50].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0093
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
    assertions = [{'assertion_id': 'v2-candidate-0093-business-01',
      'class': 'business',
      'predicate_type': 'P01',
      'predicate': {'absent_statuses': [],
                    'family': 'P01',
                    'identity': None,
                    'member': None,
                    'operator': 'present',
                    'target': {'path': '$.meta', 'role': 'observation', 'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0093-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0093-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'object',
                    'response_ref': 'observation',
                    'target_path': '$.meta',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-a5e3c00a7cc62da3a6ab',
        candidate_id='v2-candidate-0093',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='97400e4a903eb660f75ba49a62164c570dc10a396c418bf53e18e8fafd5cd857',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_28bceba670d01ea03a45(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint For every member of observation $.newsletters (array) in actual_response: P21 requires item $.id (string) to have JSON type string; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0094\nCanonical relation core: 046e63221f310dcfe36f3b10fe6f20086d159b2f16ddc7b94e39749414791d3f\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[53].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0094
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
    assertions = [{'assertion_id': 'v2-candidate-0094-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'expected_type': 'string',
                             'family': 'P21',
                             'target': {'path': '$.id', 'role': 'item', 'value_type': 'string'}},
                    'collection': {'path': '$.newsletters',
                                   'role': 'observation',
                                   'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0094-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0094-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.newsletters',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-28bceba670d01ea03a45',
        candidate_id='v2-candidate-0094',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='91b873a07424e4d9c085c30112a9d909713967230c62ee978dda5d5e6b403f58',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_6f2216ed23a431cb3209(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint For every member of observation $.newsletters (array) in actual_response: P21 requires item $.name (string) to have JSON type string; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0095\nCanonical relation core: 55eff89f23bb1fc481e54940cbfc0e60999572221c0a56b64a3b304f19d282b7\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[54].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0095
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
    assertions = [{'assertion_id': 'v2-candidate-0095-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'expected_type': 'string',
                             'family': 'P21',
                             'target': {'path': '$.name', 'role': 'item', 'value_type': 'string'}},
                    'collection': {'path': '$.newsletters',
                                   'role': 'observation',
                                   'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0095-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0095-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.newsletters',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-6f2216ed23a431cb3209',
        candidate_id='v2-candidate-0095',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='182218eb2e44abce027326beba08a4391d1fe6ce8061311474ea2887c97791a2',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_cf18e61530442473bae2(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; basic constraint For every member of observation $.newsletters (array) in actual_response: P21 requires item $.status (string) to have JSON type string; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0096\nCanonical relation core: dc9f4c7cbf1a033dfe2ffd33a7bebc820d7acb813dbc097262e2066d2d112488\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[55].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0096
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
    assertions = [{'assertion_id': 'v2-candidate-0096-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'expected_type': 'string',
                             'family': 'P21',
                             'target': {'path': '$.status', 'role': 'item', 'value_type': 'string'}},
                    'collection': {'path': '$.newsletters',
                                   'role': 'observation',
                                   'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': None,
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0096-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0096-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.newsletters',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-cf18e61530442473bae2',
        candidate_id='v2-candidate-0096',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='cf2de98c97b1fb444623ddfd4653fb1d9f32c8847d43522a9f1dead0938592e8',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_0ab47bb0c8ff6fb3360e(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/tiers/; business relation P19 requires observation $.meta.pagination.total (integer) = count(observation $.tiers (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0097\nCanonical relation core: c52c713b22517e1d232e8cb9ad25f7eee5efd32203a7a88ceb1a159384afff57\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0097
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
    assertions = [{'assertion_id': 'v2-candidate-0097-business-01',
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
                    'units': {'evidence_refs': ['r20260920-170620-c734:request:26'],
                              'rationale': 'proposed unit: each returned tier is one item of the '
                                           'reported pagination total; not prevalidated',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0097-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0097-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.total',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-0ab47bb0c8ff6fb3360e',
        candidate_id='v2-candidate-0097',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='6fd00260b69c23d92dcb5c4013b67d667be9adfe92d56dc2a7e6d07345beee5c',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_545bdfd90fe58de91452(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; business relation P19 requires observation $.meta.pagination.total (integer) = count(observation $.newsletters (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0098\nCanonical relation core: 92a329fa52b780bf4efd355da67fa8efb017854c104da25308361b43a6eb33f7\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0098
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
    assertions = [{'assertion_id': 'v2-candidate-0098-business-01',
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
                    'units': {'evidence_refs': ['r20260920-170620-c734:request:27'],
                              'rationale': 'proposed unit: each returned newsletter is one item of the '
                                           'reported pagination total; not prevalidated',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0098-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0098-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.total',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-545bdfd90fe58de91452',
        candidate_id='v2-candidate-0098',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='ae8963d5f416d81536cf32089a36738f58a348430b9772c7b6a981ffcc16997c',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_e1d27944e1039bcaaa0e(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/labels/; business relation P19 requires observation $.meta.pagination.total (integer) = count(observation $.labels (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0099\nCanonical relation core: 3d24bef0bdd02dfa8cef73b70c242960eb1b2ca709a116c011e7f10c3e0fbef8\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0099
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0099-business-01',
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
                    'units': {'evidence_refs': ['r20260920-170620-c734:request:25'],
                              'rationale': 'proposed unit: each returned label is one item of the '
                                           'reported pagination total; not prevalidated',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0099-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0099-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.total',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-e1d27944e1039bcaaa0e',
        candidate_id='v2-candidate-0099',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='0992d4086a0cd8f406705d74c375b303f81a7992f82ca12aecf2720a8e472ff7',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_713b963d25405cb6c0fb(uisemtest_runtime):
    'Business summary: Producer actor_a POST /ghost/api/admin/members/; observer actor_a GET /ghost/api/admin/labels/; business predicate P20 requires strict equality between before $.labels (array) and after $.labels (array).\nCandidate ID: v2-candidate-0100\nCanonical relation core: dce7341d4f2333c10e9b52b06bd51dff495e0934c5d1d41ec0c27270d5f14836\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0004/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V4: v2-candidate-0100
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
    assertions = [{'assertion_id': 'v2-candidate-0100-business-01',
      'class': 'business',
      'predicate_type': 'P20',
      'predicate': {'family': 'P20',
                    'left': {'path': '$.labels', 'role': 'before', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'projection_ref': None,
                    'right': {'path': '$.labels', 'role': 'after', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0100-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0100-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0100-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-713b963d25405cb6c0fb',
        candidate_id='v2-candidate-0100',
        protocol_kind='V4',
        normal_runs=1,
        source_test_sha256='0baf5f0507cf0be06b36ff83320e11acd32ebef328bd22494369a078a9a49228',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_64cfae87097161c68db7(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/members/; basic constraint P15 requires observation $.members (array) (actual_response) to have unique members by strict-tuple identity [$.id]; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0101\nCanonical relation core: 5b4c14cf652850a850e68a15f438ef84e1551479e7026aa910386bfc9f6d8c5d\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0007/provider_response_envelope.json#content(from-json).candidates[7].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0005/provider_response_envelope.json#content(from-json).candidates[4].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0101
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
    assertions = [{'assertion_id': 'v2-candidate-0101-business-01',
      'class': 'business',
      'predicate_type': 'P15',
      'predicate': {'collection': {'path': '$.members', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P15',
                    'identity': {'paths': ['$.id'], 'semantics': 'strict-tuple'},
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0101-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0101-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.members',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-64cfae87097161c68db7',
        candidate_id='v2-candidate-0101',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='658442adf993c9eefe1dba2c741f4ccee9352acc18b735cd9aeb7dddd9230b21',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_9f87ba707951eb5ab908(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/members/; business relation P19 requires observation $.meta.pagination.total (integer) = count(observation $.members (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0103\nCanonical relation core: 3c2189f7daef4b3b67e969b9bd268c756e34b73925e2046336ce1679cb162001\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0010/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0103
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
    assertions = [{'assertion_id': 'v2-candidate-0103-business-01',
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
                              'rationale': 'the count of returned member items is expressed in items',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0103-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0103-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.total',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-9f87ba707951eb5ab908',
        candidate_id='v2-candidate-0103',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='6e304e2fcc30cd23961dc689676e3ae24a02b24921b634a7bcf7a24cfc92cf8a',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_6e967fc90e0493fba9aa(uisemtest_runtime):
    "Business summary: Queries source_query actor_a GET /ghost/api/admin/labels/; followup_query:q1 actor_a GET /ghost/api/admin/labels/; business predicate P17 requires followup_query:q1 $.labels (array) equal source_query $.labels (array); representation=multiset, basis=full_json_value, projection=[], identity=None; query scope={'closures': [], 'scope': 'actual_response'}; input transform={'keys': ['limit', 'page'], 'kind': 'equivalent_input', 'location': 'query', 'semantics': {'evidence_refs': ['r20260920-170620-c734:request:43', 'r20260920-170620-c734:request:44'], 'rationale': 'Both recorded labels reads use the same path and the same query selectors limit=100 and page=1; the follow-up input is proposed to be equivalent to the source input, so no filter/sort transformation is claimed.', 'source': 'hypothesis', 'value': 'equivalent', 'value_type': 'string'}}.\nCandidate ID: v2-candidate-0106\nCanonical relation core: 226d0bd75172329395bb90b1777e60815ba9d1142b189a7de53341aea5580206\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0013/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V3: v2-candidate-0106
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'metamorphic_query', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'source_query/producer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:43'},
     {'kind': 'http',
      'phase': 'followup_query[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:44'}]
    assertions = [{'assertion_id': 'v2-candidate-0106-business-01',
      'class': 'business',
      'predicate_type': 'P17',
      'predicate': {'comparison_basis': 'full_json_value',
                    'expected_difference': None,
                    'family': 'P17',
                    'identity': None,
                    'left': {'path': '$.labels', 'role': 'followup_query:q1', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'representation': 'multiset',
                    'right': {'path': '$.labels', 'role': 'source_query', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0106-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0106-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0106-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-6e967fc90e0493fba9aa',
        candidate_id='v2-candidate-0106',
        protocol_kind='V3',
        normal_runs=1,
        source_test_sha256='358fbfc1c4ab8b7319147d1eac255cc1f3e879be68192da7dcebdec9cd33a68d',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_0278f41471556603131e(uisemtest_runtime):
    "Business summary: Queries source_query actor_a GET /ghost/api/admin/labels/; followup_query:q1 actor_a GET /ghost/api/admin/labels/; business predicate P17 requires followup_query:q1 $.labels (array) equal source_query $.labels (array); representation=multiset, basis=full_json_value, projection=[], identity=None; query scope={'closures': [], 'scope': 'actual_response'}; input transform={'keys': ['limit', 'page'], 'kind': 'equivalent_input', 'location': 'query', 'semantics': {'evidence_refs': ['r20260920-170620-c734:request:43', 'r20260920-170620-c734:request:44'], 'rationale': 'both recorded reads of /ghost/api/admin/labels/ carry the identical selectors limit=100 and page=1, so the observed selector change is none (equivalent input)', 'source': 'hypothesis', 'value': 'equivalent', 'value_type': 'string'}}.\nCandidate ID: v2-candidate-0107\nCanonical relation core: 226d0bd75172329395bb90b1777e60815ba9d1142b189a7de53341aea5580206\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0014/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V3: v2-candidate-0107
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'metamorphic_query', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'source_query/producer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:43'},
     {'kind': 'http',
      'phase': 'followup_query[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:44'}]
    assertions = [{'assertion_id': 'v2-candidate-0107-business-01',
      'class': 'business',
      'predicate_type': 'P17',
      'predicate': {'comparison_basis': 'full_json_value',
                    'expected_difference': None,
                    'family': 'P17',
                    'identity': None,
                    'left': {'path': '$.labels', 'role': 'followup_query:q1', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'representation': 'multiset',
                    'right': {'path': '$.labels', 'role': 'source_query', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0107-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0107-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0107-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-0278f41471556603131e',
        candidate_id='v2-candidate-0107',
        protocol_kind='V3',
        normal_runs=1,
        source_test_sha256='0412217d8e9f76f34d0baa24f2816544fe9d41cf9bec64d11e11708818b2108a',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_b2629a6010d7aade866b(uisemtest_runtime):
    "Business summary: Queries source_query actor_a GET /ghost/api/admin/labels/; followup_query:q1 actor_a GET /ghost/api/admin/labels/; business predicate P17 requires followup_query:q1 $.labels (array) equal source_query $.labels (array); representation=multiset, basis=full_json_value, projection=[], identity=None; query scope={'closures': [], 'scope': 'actual_response'}; input transform={'keys': ['limit', 'page'], 'kind': 'equivalent_input', 'location': 'query', 'semantics': {'evidence_refs': ['r20260920-170620-c734:request:43', 'r20260920-170620-c734:request:44'], 'rationale': 'Both recorded label reads carry identical selectors limit=100 and page=1 and no other query parameter differs, so the frozen selector change is an equivalence. Not prevalidated.', 'source': 'hypothesis', 'value': 'equivalent', 'value_type': 'string'}}.\nCandidate ID: v2-candidate-0110\nCanonical relation core: 226d0bd75172329395bb90b1777e60815ba9d1142b189a7de53341aea5580206\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0015/provider_response_envelope.json#content(from-json).candidates[6].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V3: v2-candidate-0110
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'metamorphic_query', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'source_query/producer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:43'},
     {'kind': 'http',
      'phase': 'followup_query[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:44'}]
    assertions = [{'assertion_id': 'v2-candidate-0110-business-01',
      'class': 'business',
      'predicate_type': 'P17',
      'predicate': {'comparison_basis': 'full_json_value',
                    'expected_difference': None,
                    'family': 'P17',
                    'identity': None,
                    'left': {'path': '$.labels', 'role': 'followup_query:q1', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'representation': 'multiset',
                    'right': {'path': '$.labels', 'role': 'source_query', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0110-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0110-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0110-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-b2629a6010d7aade866b',
        candidate_id='v2-candidate-0110',
        protocol_kind='V3',
        normal_runs=1,
        source_test_sha256='0b53aa2064909083a907108ff2d393ee6cbc6669f8afc8e666b864036507b2cc',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_1e264595dd36b213f142(uisemtest_runtime):
    "Business summary: Queries source_query actor_a GET /ghost/api/admin/labels/; followup_query:q1 actor_a GET /ghost/api/admin/labels/; business predicate P17 requires followup_query:q1 $.labels (array) equal source_query $.labels (array); representation=multiset, basis=full_json_value, projection=[], identity=None; query scope={'closures': [], 'scope': 'actual_response'}; input transform={'keys': ['limit', 'page'], 'kind': 'equivalent_input', 'location': 'query', 'semantics': {'evidence_refs': ['r20260920-170620-c734:request:43', 'r20260920-170620-c734:request:44'], 'rationale': 'Both recorded label-list reads carry the same limit=100 and page=1 selector values and no other differing query key, so the follow-up repeats the source request input.', 'source': 'hypothesis', 'value': 'equivalent', 'value_type': 'string'}}.\nCandidate ID: v2-candidate-0111\nCanonical relation core: 226d0bd75172329395bb90b1777e60815ba9d1142b189a7de53341aea5580206\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0016/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V3: v2-candidate-0111
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'metamorphic_query', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'source_query/producer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:43'},
     {'kind': 'http',
      'phase': 'followup_query[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:44'}]
    assertions = [{'assertion_id': 'v2-candidate-0111-business-01',
      'class': 'business',
      'predicate_type': 'P17',
      'predicate': {'comparison_basis': 'full_json_value',
                    'expected_difference': None,
                    'family': 'P17',
                    'identity': None,
                    'left': {'path': '$.labels', 'role': 'followup_query:q1', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'representation': 'multiset',
                    'right': {'path': '$.labels', 'role': 'source_query', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0111-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0111-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0111-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-1e264595dd36b213f142',
        candidate_id='v2-candidate-0111',
        protocol_kind='V3',
        normal_runs=1,
        source_test_sha256='2f52414304b66dd3b1ff8b7fb36a03de64c2c711056e362b6a69fc3eb4821033',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_d3bb127fc69fb2b69472(uisemtest_runtime):
    "Business summary: Queries source_query actor_a GET /ghost/api/admin/labels/; followup_query:q1 actor_a GET /ghost/api/admin/labels/; business predicate P17 requires followup_query:q1 $.labels (array) equal source_query $.labels (array); representation=multiset, basis=full_json_value, projection=[], identity=None; query scope={'closures': [], 'scope': 'actual_response'}; input transform={'keys': ['limit', 'page'], 'kind': 'equivalent_input', 'location': 'query', 'semantics': {'evidence_refs': ['r20260920-170620-c734:request:43', 'r20260920-170620-c734:request:44'], 'rationale': 'Both recorded reads carry the same limit=100 and page=1 selectors on the same labels operation, so the recorded selector change between source and follow-up is an equivalence, not a filter/sort/pagination change.', 'source': 'hypothesis', 'value': 'equivalent', 'value_type': 'string'}}.\nCandidate ID: v2-candidate-0112\nCanonical relation core: 226d0bd75172329395bb90b1777e60815ba9d1142b189a7de53341aea5580206\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0017/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V3: v2-candidate-0112
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'metamorphic_query', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'source_query/producer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:43'},
     {'kind': 'http',
      'phase': 'followup_query[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:44'}]
    assertions = [{'assertion_id': 'v2-candidate-0112-business-01',
      'class': 'business',
      'predicate_type': 'P17',
      'predicate': {'comparison_basis': 'full_json_value',
                    'expected_difference': None,
                    'family': 'P17',
                    'identity': None,
                    'left': {'path': '$.labels', 'role': 'followup_query:q1', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'representation': 'multiset',
                    'right': {'path': '$.labels', 'role': 'source_query', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0112-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0112-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0112-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-d3bb127fc69fb2b69472',
        candidate_id='v2-candidate-0112',
        protocol_kind='V3',
        normal_runs=1,
        source_test_sha256='f784c50e155dbfa35b4eaf3176c5494cf868f30f3d23c7bc2c9fd2d3df92f928',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_a2139122a1a6df61b626(uisemtest_runtime):
    "Business summary: Queries source_query actor_a GET /ghost/api/admin/labels/; followup_query:q1 actor_a GET /ghost/api/admin/labels/; business predicate P17 requires followup_query:q1 $.labels (array) equal source_query $.labels (array); representation=multiset, basis=full_json_value, projection=[], identity=None; query scope={'closures': [], 'scope': 'actual_response'}; input transform={'keys': ['limit', 'page'], 'kind': 'equivalent_input', 'location': 'query', 'semantics': {'evidence_refs': ['r20260920-170620-c734:request:43', 'r20260920-170620-c734:request:44'], 'rationale': 'both recorded label reads carry identical selector values limit=100 and page=1, with no other differing parameter', 'source': 'hypothesis', 'value': 'equivalent', 'value_type': 'string'}}.\nCandidate ID: v2-candidate-0113\nCanonical relation core: 226d0bd75172329395bb90b1777e60815ba9d1142b189a7de53341aea5580206\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0018/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V3: v2-candidate-0113
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'metamorphic_query', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'source_query/producer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:43'},
     {'kind': 'http',
      'phase': 'followup_query[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:44'}]
    assertions = [{'assertion_id': 'v2-candidate-0113-business-01',
      'class': 'business',
      'predicate_type': 'P17',
      'predicate': {'comparison_basis': 'full_json_value',
                    'expected_difference': None,
                    'family': 'P17',
                    'identity': None,
                    'left': {'path': '$.labels', 'role': 'followup_query:q1', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'representation': 'multiset',
                    'right': {'path': '$.labels', 'role': 'source_query', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0113-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0113-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0113-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-a2139122a1a6df61b626',
        candidate_id='v2-candidate-0113',
        protocol_kind='V3',
        normal_runs=1,
        source_test_sha256='a5e3447b6d922436b40454cb229d4925fed181c1acf3d9e9d2783dc050ffd2c5',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_746202d435b568d4e050(uisemtest_runtime):
    "Business summary: Queries source_query actor_a GET /ghost/api/admin/labels/; followup_query:q1 actor_a GET /ghost/api/admin/labels/; business predicate P17 requires followup_query:q1 $.labels (array) equal source_query $.labels (array); representation=multiset, basis=full_json_value, projection=[], identity=None; query scope={'closures': [], 'scope': 'actual_response'}; input transform={'keys': ['limit', 'page'], 'kind': 'equivalent_input', 'location': 'query', 'semantics': {'evidence_refs': ['r20260920-170620-c734:request:43', 'r20260920-170620-c734:request:44'], 'rationale': 'Both recorded labels reads carry the identical selector limit=100&page=1 on the same canonical path, so the observed change is an equivalent-input re-read rather than a filter, sort or partition change.', 'source': 'hypothesis', 'value': 'equivalent', 'value_type': 'string'}}.\nCandidate ID: v2-candidate-0116\nCanonical relation core: 226d0bd75172329395bb90b1777e60815ba9d1142b189a7de53341aea5580206\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0019/provider_response_envelope.json#content(from-json).candidates[10].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V3: v2-candidate-0116
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'metamorphic_query', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'source_query/producer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:43'},
     {'kind': 'http',
      'phase': 'followup_query[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:44'}]
    assertions = [{'assertion_id': 'v2-candidate-0116-business-01',
      'class': 'business',
      'predicate_type': 'P17',
      'predicate': {'comparison_basis': 'full_json_value',
                    'expected_difference': None,
                    'family': 'P17',
                    'identity': None,
                    'left': {'path': '$.labels', 'role': 'followup_query:q1', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'representation': 'multiset',
                    'right': {'path': '$.labels', 'role': 'source_query', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0116-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0116-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0116-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-746202d435b568d4e050',
        candidate_id='v2-candidate-0116',
        protocol_kind='V3',
        normal_runs=1,
        source_test_sha256='951bdd1be15f999c66faf2a6a6e7b6a39cc6a8e5375e1ba2ad4cae04705de7d4',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_45347cff5263b8348380(uisemtest_runtime):
    "Business summary: Queries source_query actor_a GET /ghost/api/admin/labels/; followup_query:q1 actor_a GET /ghost/api/admin/labels/; business predicate P17 requires followup_query:q1 $.labels (array) equal source_query $.labels (array); representation=multiset, basis=full_json_value, projection=[], identity=None; query scope={'closures': [], 'scope': 'actual_response'}; input transform={'keys': ['limit', 'page'], 'kind': 'equivalent_input', 'location': 'query', 'semantics': {'evidence_refs': ['r20260920-170620-c734:request:43', 'r20260920-170620-c734:request:44'], 'rationale': 'Both recorded labels reads carry the identical selectors limit=100 and page=1 and no other selector differs; the shared logical meaning of the two reads is proposed as equivalence.', 'source': 'hypothesis', 'value': 'equivalent', 'value_type': 'string'}}.\nCandidate ID: v2-candidate-0117\nCanonical relation core: 226d0bd75172329395bb90b1777e60815ba9d1142b189a7de53341aea5580206\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0002/M10/calls/detail-0021/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V3: v2-candidate-0117
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'metamorphic_query', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'source_query/producer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:43'},
     {'kind': 'http',
      'phase': 'followup_query[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:44'}]
    assertions = [{'assertion_id': 'v2-candidate-0117-business-01',
      'class': 'business',
      'predicate_type': 'P17',
      'predicate': {'comparison_basis': 'full_json_value',
                    'expected_difference': None,
                    'family': 'P17',
                    'identity': None,
                    'left': {'path': '$.labels', 'role': 'followup_query:q1', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'representation': 'multiset',
                    'right': {'path': '$.labels', 'role': 'source_query', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0117-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0117-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0117-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-45347cff5263b8348380',
        candidate_id='v2-candidate-0117',
        protocol_kind='V3',
        normal_runs=1,
        source_test_sha256='db57557d43089309ae520b035e42d2a2157b5279f789ba768d74faf43db498d0',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_a59a7ac9f1d0b865eade(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/labels/; business relation P19 requires observation $.meta.pagination.total (integer) = count(observation $.labels (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0121\nCanonical relation core: 3d24bef0bdd02dfa8cef73b70c242960eb1b2ca709a116c011e7f10c3e0fbef8\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[1].rationale\n- ../attempts/attempt-0003/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[1].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0121
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0121-business-01',
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
                    'units': {'evidence_refs': ['r20260920-170620-c734:request:25'],
                              'rationale': 'proposed aggregation unit: the label collection and its '
                                           'reported pagination total are both counted in items',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0121-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0121-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.total',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-a59a7ac9f1d0b865eade',
        candidate_id='v2-candidate-0121',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='278baae4902f35d331f0d5b7b2edf717d52b24c81bf2ede71278649ba1f88a2a',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_bc6740f48e20a121129b(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/labels/; basic constraint P02 requires observation $.meta.pagination.page (integer) to strictly equal actual request query $.page (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0122\nCanonical relation core: 4613bf61ce3753ba61dbbf3a64cb633f23762100fa12d4b28e57e0b32abc642f\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0001/provider_response_envelope.json#content(from-json).candidates[2].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0122
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'single_state', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:25'}]
    assertions = [{'assertion_id': 'v2-candidate-0122-business-01',
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
     {'assertion_id': 'v2-candidate-0122-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0122-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.page',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-bc6740f48e20a121129b',
        candidate_id='v2-candidate-0122',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='1739b5f9172e887445843a4eee7ac348b4f5545aa5cab552295f9dd0c68d66a0',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_9f860cd28c1b46703bb8(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/tiers/; basic constraint For every member of observation $.tiers (array) in actual_response when P02 requires item $.active (boolean) to strictly equal frozen hypothesis True (boolean): P02 requires item $.type (string) to strictly equal frozen hypothesis 'paid' (string); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0123\nCanonical relation core: 258703f4933c01006e0f8c96190bfd1fc3ea47c54cff83e7a9b4d7f30649e8eb\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0002/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0123
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
    assertions = [{'assertion_id': 'v2-candidate-0123-business-01',
      'class': 'business',
      'predicate_type': 'forall',
      'predicate': {'body': {'family': 'P02',
                             'left': {'path': '$.type', 'role': 'item', 'value_type': 'string'},
                             'operator': 'eq',
                             'right': {'evidence_refs': ['r20260920-170620-c734:request:26'],
                                       'rationale': 'Proposed business rule read off the visible '
                                                    'recorded query filter type:paid+active:true; not '
                                                    'prevalidated.',
                                       'source': 'hypothesis',
                                       'value': 'paid',
                                       'value_type': 'string'}},
                    'collection': {'path': '$.tiers', 'role': 'observation', 'value_type': 'array'},
                    'family': 'forall',
                    'item_guard': {'family': 'P02',
                                   'left': {'path': '$.active',
                                            'role': 'item',
                                            'value_type': 'boolean'},
                                   'operator': 'eq',
                                   'right': {'evidence_refs': ['r20260920-170620-c734:request:26'],
                                             'rationale': 'Proposed applicability rule taken from the '
                                                          'visible recorded query filter active:true; '
                                                          'the recorded members need not already '
                                                          'satisfy it.',
                                             'source': 'hypothesis',
                                             'value': True,
                                             'value_type': 'boolean'}},
                    'scope': 'actual_response'}},
     {'assertion_id': 'v2-candidate-0123-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0123-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.tiers',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-9f860cd28c1b46703bb8',
        candidate_id='v2-candidate-0123',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='dcddfaaf99e60f6b5fb5bad5fa96b7fcb04a94e5155e5e695d8205cf2e480510',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_b57cb21a82c44b2fb658(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/newsletters/; business relation P19 requires observation $.meta.pagination.total (integer) = count(observation $.newsletters (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0124\nCanonical relation core: 92a329fa52b780bf4efd355da67fa8efb017854c104da25308361b43a6eb33f7\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0003/provider_response_envelope.json#content(from-json).candidates[6].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0124
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
    assertions = [{'assertion_id': 'v2-candidate-0124-business-01',
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
                    'units': {'evidence_refs': ['r20260920-170620-c734:request:27'],
                              'rationale': 'The newsletter collection is proposed to be counted in '
                                           'members and the same response reports an integer total '
                                           'count field.',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0124-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0124-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.total',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-b57cb21a82c44b2fb658',
        candidate_id='v2-candidate-0124',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='eba7ce53548247884cf6770241e98d101c3c50122f8d6429332cc325e603e2a6',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_c2e947ed53d8824e0e67(uisemtest_runtime):
    'Business summary: Observation actor_a GET /ghost/api/admin/members/; basic constraint P11 requires count(observation $.members (array); unit=items) le observation $.meta.pagination.total (integer); one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0125\nCanonical relation core: 9351c6dd5e92e4b4b1f7bbcf1a43a01f172b31ae41d6bedb0a87a3c6a14622a6\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0005/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation.'
    # V2: v2-candidate-0125
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
    assertions = [{'assertion_id': 'v2-candidate-0125-business-01',
      'class': 'business',
      'predicate_type': 'P11',
      'predicate': {'family': 'P11',
                    'operator': 'le',
                    'projection': 'count',
                    'right': {'ref': {'path': '$.meta.pagination.total',
                                      'role': 'observation',
                                      'value_type': 'integer'},
                              'source': 'role'},
                    'target': {'path': '$.members', 'role': 'observation', 'value_type': 'array'},
                    'unit': 'items'}},
     {'assertion_id': 'v2-candidate-0125-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0125-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'observation',
                    'target_path': '$.members',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-c2e947ed53d8824e0e67',
        candidate_id='v2-candidate-0125',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='756f7efa219700c79c5c47d177006c989334c83c8d88bf9e53369667f192a27c',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_e172abec6178c1f4b8c4(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/members/; business relation P19 requires observation $.meta.pagination.total (integer) = count(observation $.members (array)); scope=actual_response, item=None, factor=None, numeric_mode=exact, units={'output': 'items'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0126\nCanonical relation core: 3c2189f7daef4b3b67e969b9bd268c756e34b73925e2046336ce1679cb162001\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0007/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0126
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
    assertions = [{'assertion_id': 'v2-candidate-0126-business-01',
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
                              'rationale': 'The counted array and the declared pagination total are '
                                           'both member counts in the same response, so the proposed '
                                           'common unit is items; this is a frozen hypothesis, not a '
                                           'recorded specification.',
                              'source': 'hypothesis',
                              'value': {'output': 'items'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0126-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0126-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.pagination.total',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-e172abec6178c1f4b8c4',
        candidate_id='v2-candidate-0126',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='bd51ee310d7d6edb5e11cab09def0bc30d2164ac9b32f8434f52165449458a00',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_95384af0ea539ce58a9b(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/stats/member_count/; business relation P19 requires observation $.meta.totals.free (integer) = sum(observation $.stats (array)); scope=actual_response, item={'path': '$.free', 'role': 'item', 'value_type': 'integer'}, factor=None, numeric_mode=exact, units={'item': 'members', 'output': 'members'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0128\nCanonical relation core: db1f989d4b24626ef5b0dd936d64309d129304e0e26df61205c4f3dbd1f8907d\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0008/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0128
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
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/stats/member_count/',
      'request_ref': 'r20260920-170620-c734:request:32'}]
    assertions = [{'assertion_id': 'v2-candidate-0128-business-01',
      'class': 'business',
      'predicate_type': 'P19',
      'predicate': {'collection': {'path': '$.stats', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P19',
                    'item': {'path': '$.free', 'role': 'item', 'value_type': 'integer'},
                    'numeric_mode': 'exact',
                    'operator': 'sum',
                    'output': {'path': '$.meta.totals.free',
                               'role': 'observation',
                               'value_type': 'integer'},
                    'scope': 'actual_response',
                    'units': {'evidence_refs': ['r20260920-170620-c734:request:32'],
                              'rationale': 'proposed identical member-count units for each daily free '
                                           'count and for the free summary',
                              'source': 'hypothesis',
                              'value': {'item': 'members', 'output': 'members'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0128-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0128-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.totals.free',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-95384af0ea539ce58a9b',
        candidate_id='v2-candidate-0128',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='ee9b2fc3a023ee613e9492293ab475de5b7d27438fbd54b8a8eb32935d052014',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_e25542bb350da3bdd50a(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/stats/member_count/; business relation P19 requires observation $.meta.totals.paid (integer) = sum(observation $.stats (array)); scope=actual_response, item={'path': '$.paid', 'role': 'item', 'value_type': 'integer'}, factor=None, numeric_mode=exact, units={'item': 'members', 'output': 'members'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0129\nCanonical relation core: b0c83452e89eccb014c1e98f01cdc66911827e287936f597201e7d46f0784d34\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0008/provider_response_envelope.json#content(from-json).candidates[4].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0129
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
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/stats/member_count/',
      'request_ref': 'r20260920-170620-c734:request:32'}]
    assertions = [{'assertion_id': 'v2-candidate-0129-business-01',
      'class': 'business',
      'predicate_type': 'P19',
      'predicate': {'collection': {'path': '$.stats', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P19',
                    'item': {'path': '$.paid', 'role': 'item', 'value_type': 'integer'},
                    'numeric_mode': 'exact',
                    'operator': 'sum',
                    'output': {'path': '$.meta.totals.paid',
                               'role': 'observation',
                               'value_type': 'integer'},
                    'scope': 'actual_response',
                    'units': {'evidence_refs': ['r20260920-170620-c734:request:32'],
                              'rationale': 'proposed identical member-count units for each daily paid '
                                           'count and for the paid summary',
                              'source': 'hypothesis',
                              'value': {'item': 'members', 'output': 'members'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0129-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0129-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.totals.paid',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-e25542bb350da3bdd50a',
        candidate_id='v2-candidate-0129',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='dd850a4065e23746232317fd4a0d7772a5d617a006cf0cf8f48626bf46e9751e',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_780c2cf89482baa32802(uisemtest_runtime):
    "Business summary: Observation actor_a GET /ghost/api/admin/stats/member_count/; business relation P19 requires observation $.meta.totals.comped (integer) = sum(observation $.stats (array)); scope=actual_response, item={'path': '$.comped', 'role': 'item', 'value_type': 'integer'}, factor=None, numeric_mode=exact, units={'item': 'members', 'output': 'members'}, rounding=None, tolerance_kind=None, tolerance=None, conversions=None; one fresh response (same_input_fresh_replay).\nCandidate ID: v2-candidate-0130\nCanonical relation core: aa9ed76d90c98754e95ea21c91d59d95cef91b5a82fbe76ec76956e48f8eb44c\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0008/provider_response_envelope.json#content(from-json).candidates[5].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V2: v2-candidate-0130
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
      'phase': 'observation',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/stats/member_count/',
      'request_ref': 'r20260920-170620-c734:request:32'}]
    assertions = [{'assertion_id': 'v2-candidate-0130-business-01',
      'class': 'business',
      'predicate_type': 'P19',
      'predicate': {'collection': {'path': '$.stats', 'role': 'observation', 'value_type': 'array'},
                    'family': 'P19',
                    'item': {'path': '$.comped', 'role': 'item', 'value_type': 'integer'},
                    'numeric_mode': 'exact',
                    'operator': 'sum',
                    'output': {'path': '$.meta.totals.comped',
                               'role': 'observation',
                               'value_type': 'integer'},
                    'scope': 'actual_response',
                    'units': {'evidence_refs': ['r20260920-170620-c734:request:32'],
                              'rationale': 'proposed identical member-count units for each daily '
                                           'comped count and for the comped summary',
                              'source': 'hypothesis',
                              'value': {'item': 'members', 'output': 'members'},
                              'value_type': 'object'}}},
     {'assertion_id': 'v2-candidate-0130-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'observation', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0130-generic-response-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'integer',
                    'response_ref': 'observation',
                    'target_path': '$.meta.totals.comped',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-780c2cf89482baa32802',
        candidate_id='v2-candidate-0130',
        protocol_kind='V2',
        normal_runs=1,
        source_test_sha256='5fbacaaf80e39087b51e8deac2ee890a0f6d99d207795a3408eda9d3be99da6a',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_5b9841566f347a63262f(uisemtest_runtime):
    "Business summary: Queries source_query actor_a GET /ghost/api/admin/labels/; followup_query:q1 actor_a GET /ghost/api/admin/labels/; business predicate P17 requires followup_query:q1 $.labels (array) equal source_query $.labels (array); representation=multiset, basis=full_json_value, projection=[], identity=None; query scope={'closures': [], 'scope': 'actual_response'}; input transform={'keys': ['limit', 'page'], 'kind': 'equivalent_input', 'location': 'query', 'semantics': {'evidence_refs': ['r20260920-170620-c734:request:43', 'r20260920-170620-c734:request:44'], 'rationale': 'Both recorded same-actor reads are get_ghost_api_admin_labels with the identical query limit=100&page=1, so the frozen selector change is a no-op equivalence of inputs.', 'source': 'hypothesis', 'value': 'equivalent', 'value_type': 'string'}}.\nCandidate ID: v2-candidate-0134\nCanonical relation core: 226d0bd75172329395bb90b1777e60815ba9d1142b189a7de53341aea5580206\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0015/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V3: v2-candidate-0134
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'metamorphic_query', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'source_query/producer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:43'},
     {'kind': 'http',
      'phase': 'followup_query[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:44'}]
    assertions = [{'assertion_id': 'v2-candidate-0134-business-01',
      'class': 'business',
      'predicate_type': 'P17',
      'predicate': {'comparison_basis': 'full_json_value',
                    'expected_difference': None,
                    'family': 'P17',
                    'identity': None,
                    'left': {'path': '$.labels', 'role': 'followup_query:q1', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'representation': 'multiset',
                    'right': {'path': '$.labels', 'role': 'source_query', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0134-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0134-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0134-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-5b9841566f347a63262f',
        candidate_id='v2-candidate-0134',
        protocol_kind='V3',
        normal_runs=1,
        source_test_sha256='2b4d0d8baf218402830db24acbcf40cde332aac975857d8f33123e29a5e260e4',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_55fbd5226c8144a203d6(uisemtest_runtime):
    "Business summary: Queries source_query actor_a GET /ghost/api/admin/labels/; followup_query:q1 actor_a GET /ghost/api/admin/labels/; business predicate P17 requires followup_query:q1 $.labels (array) equal source_query $.labels (array); representation=multiset, basis=full_json_value, projection=[], identity=None; query scope={'closures': [], 'scope': 'actual_response'}; input transform={'keys': ['limit', 'page'], 'kind': 'equivalent_input', 'location': 'query', 'semantics': {'evidence_refs': ['r20260920-170620-c734:request:43', 'r20260920-170620-c734:request:44'], 'rationale': 'Both recorded requests use identical query selectors limit=100 and page=1, so the follow-up is an equivalent input read.', 'source': 'hypothesis', 'value': 'equivalent', 'value_type': 'string'}}.\nCandidate ID: v2-candidate-0135\nCanonical relation core: 226d0bd75172329395bb90b1777e60815ba9d1142b189a7de53341aea5580206\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0016/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V3: v2-candidate-0135
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'metamorphic_query', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'source_query/producer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:43'},
     {'kind': 'http',
      'phase': 'followup_query[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:44'}]
    assertions = [{'assertion_id': 'v2-candidate-0135-business-01',
      'class': 'business',
      'predicate_type': 'P17',
      'predicate': {'comparison_basis': 'full_json_value',
                    'expected_difference': None,
                    'family': 'P17',
                    'identity': None,
                    'left': {'path': '$.labels', 'role': 'followup_query:q1', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'representation': 'multiset',
                    'right': {'path': '$.labels', 'role': 'source_query', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0135-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0135-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0135-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-55fbd5226c8144a203d6',
        candidate_id='v2-candidate-0135',
        protocol_kind='V3',
        normal_runs=1,
        source_test_sha256='c1cbf9a58c5fbd79a875a6ad16807d82f34db32e43d2517989c518519bf6aafc',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_aa5af07bd29b279fe609(uisemtest_runtime):
    "Business summary: Queries source_query actor_a GET /ghost/api/admin/labels/; followup_query:q1 actor_a GET /ghost/api/admin/labels/; business predicate P17 requires followup_query:q1 $.labels (array) equal source_query $.labels (array); representation=multiset, basis=full_json_value, projection=[], identity=None; query scope={'closures': [], 'scope': 'actual_response'}; input transform={'keys': ['limit', 'page'], 'kind': 'equivalent_input', 'location': 'query', 'semantics': {'evidence_refs': ['r20260920-170620-c734:request:43', 'r20260920-170620-c734:request:44'], 'rationale': 'both recorded label reads carry the identical selectors limit=100 and page=1 and returned the identical response body hash', 'source': 'hypothesis', 'value': 'equivalent', 'value_type': 'string'}}.\nCandidate ID: v2-candidate-0136\nCanonical relation core: 226d0bd75172329395bb90b1777e60815ba9d1142b189a7de53341aea5580206\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0017/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V3: v2-candidate-0136
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'metamorphic_query', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'source_query/producer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:43'},
     {'kind': 'http',
      'phase': 'followup_query[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:44'}]
    assertions = [{'assertion_id': 'v2-candidate-0136-business-01',
      'class': 'business',
      'predicate_type': 'P17',
      'predicate': {'comparison_basis': 'full_json_value',
                    'expected_difference': None,
                    'family': 'P17',
                    'identity': None,
                    'left': {'path': '$.labels', 'role': 'followup_query:q1', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'representation': 'multiset',
                    'right': {'path': '$.labels', 'role': 'source_query', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0136-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0136-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0136-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-aa5af07bd29b279fe609',
        candidate_id='v2-candidate-0136',
        protocol_kind='V3',
        normal_runs=1,
        source_test_sha256='40abd25a2bda76bf94d135a50d48812ccc048738b6cdc4a9d82d9831236d5a4c',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_3a9727dacad94b9cb93e(uisemtest_runtime):
    "Business summary: Queries source_query actor_a GET /ghost/api/admin/labels/; followup_query:q1 actor_a GET /ghost/api/admin/labels/; business predicate P17 requires followup_query:q1 $.labels (array) equal source_query $.labels (array); representation=multiset, basis=full_json_value, projection=[], identity=None; query scope={'closures': [], 'scope': 'actual_response'}; input transform={'keys': ['limit', 'page'], 'kind': 'equivalent_input', 'location': 'query', 'semantics': {'evidence_refs': ['r20260920-170620-c734:request:43', 'r20260920-170620-c734:request:44'], 'rationale': 'proposed: the two recorded label reads carry the identical path and identical limit/page selectors, so their returned collections are proposed equivalent', 'source': 'hypothesis', 'value': 'equivalent', 'value_type': 'string'}}.\nCandidate ID: v2-candidate-0137\nCanonical relation core: 226d0bd75172329395bb90b1777e60815ba9d1142b189a7de53341aea5580206\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0018/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V3: v2-candidate-0137
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'metamorphic_query', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'source_query/producer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:43'},
     {'kind': 'http',
      'phase': 'followup_query[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:44'}]
    assertions = [{'assertion_id': 'v2-candidate-0137-business-01',
      'class': 'business',
      'predicate_type': 'P17',
      'predicate': {'comparison_basis': 'full_json_value',
                    'expected_difference': None,
                    'family': 'P17',
                    'identity': None,
                    'left': {'path': '$.labels', 'role': 'followup_query:q1', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'representation': 'multiset',
                    'right': {'path': '$.labels', 'role': 'source_query', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0137-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0137-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0137-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-3a9727dacad94b9cb93e',
        candidate_id='v2-candidate-0137',
        protocol_kind='V3',
        normal_runs=1,
        source_test_sha256='70cd57e141b2f0d695d90ee59fc073f23b4f53f0ece5823cef94b02dbc1ff15f',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_4e586a980f0672a56a94(uisemtest_runtime):
    "Business summary: Queries source_query actor_a GET /ghost/api/admin/labels/; followup_query:q1 actor_a GET /ghost/api/admin/labels/; business predicate P17 requires followup_query:q1 $.labels (array) equal source_query $.labels (array); representation=multiset, basis=full_json_value, projection=[], identity=None; query scope={'closures': [], 'scope': 'actual_response'}; input transform={'keys': ['limit', 'page'], 'kind': 'equivalent_input', 'location': 'query', 'semantics': {'evidence_refs': ['r20260920-170620-c734:request:43', 'r20260920-170620-c734:request:44'], 'rationale': 'Both recorded reads are the same actor/session labels list with the identical selector limit=100 and page=1, so the query inputs are proposed equivalent.', 'source': 'hypothesis', 'value': 'equivalent', 'value_type': 'string'}}.\nCandidate ID: v2-candidate-0139\nCanonical relation core: 226d0bd75172329395bb90b1777e60815ba9d1142b189a7de53341aea5580206\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0019/provider_response_envelope.json#content(from-json).candidates[3].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V3: v2-candidate-0139
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'metamorphic_query', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'source_query/producer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:43'},
     {'kind': 'http',
      'phase': 'followup_query[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:44'}]
    assertions = [{'assertion_id': 'v2-candidate-0139-business-01',
      'class': 'business',
      'predicate_type': 'P17',
      'predicate': {'comparison_basis': 'full_json_value',
                    'expected_difference': None,
                    'family': 'P17',
                    'identity': None,
                    'left': {'path': '$.labels', 'role': 'followup_query:q1', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'representation': 'multiset',
                    'right': {'path': '$.labels', 'role': 'source_query', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0139-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0139-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0139-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-4e586a980f0672a56a94',
        candidate_id='v2-candidate-0139',
        protocol_kind='V3',
        normal_runs=1,
        source_test_sha256='44a02a36822e77d885093ee2c04f3b0be8e826d4b650763e829781cd458930d6',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_5c89bac8a3a282d49995(uisemtest_runtime):
    "Business summary: Queries source_query actor_a GET /ghost/api/admin/labels/; followup_query:q1 actor_a GET /ghost/api/admin/labels/; business predicate P17 requires followup_query:q1 $.labels (array) equal source_query $.labels (array); representation=multiset, basis=full_json_value, projection=[], identity=None; query scope={'closures': [], 'scope': 'actual_response'}; input transform={'keys': ['limit', 'page'], 'kind': 'equivalent_input', 'location': 'query', 'semantics': {'evidence_refs': ['r20260920-170620-c734:request:43', 'r20260920-170620-c734:request:44'], 'rationale': 'both recorded label reads carry identical selectors limit=100 and page=1, so the frozen selector change is none', 'source': 'hypothesis', 'value': 'equivalent', 'value_type': 'string'}}.\nCandidate ID: v2-candidate-0140\nCanonical relation core: 226d0bd75172329395bb90b1777e60815ba9d1142b189a7de53341aea5580206\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0020/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V3: v2-candidate-0140
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'metamorphic_query', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'source_query/producer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:43'},
     {'kind': 'http',
      'phase': 'followup_query[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:44'}]
    assertions = [{'assertion_id': 'v2-candidate-0140-business-01',
      'class': 'business',
      'predicate_type': 'P17',
      'predicate': {'comparison_basis': 'full_json_value',
                    'expected_difference': None,
                    'family': 'P17',
                    'identity': None,
                    'left': {'path': '$.labels', 'role': 'followup_query:q1', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'representation': 'multiset',
                    'right': {'path': '$.labels', 'role': 'source_query', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0140-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0140-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0140-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-5c89bac8a3a282d49995',
        candidate_id='v2-candidate-0140',
        protocol_kind='V3',
        normal_runs=1,
        source_test_sha256='4e7c70ba5423efcc3e14ffe359411c56ef8788cd50d93e32f5d362fe2a9cd873',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])


def test_relation_test_abe1963c608500c81060(uisemtest_runtime):
    "Business summary: Queries source_query actor_a GET /ghost/api/admin/labels/; followup_query:q1 actor_a GET /ghost/api/admin/labels/; business predicate P17 requires followup_query:q1 $.labels (array) equal source_query $.labels (array); representation=multiset, basis=full_json_value, projection=[], identity=None; query scope={'closures': [], 'scope': 'actual_response'}; input transform={'keys': ['limit', 'page'], 'kind': 'equivalent_input', 'location': 'query', 'semantics': {'evidence_refs': ['r20260920-170620-c734:request:43', 'r20260920-170620-c734:request:44'], 'rationale': 'both recorded labels reads use the same limit=100 and page=1 selectors verbatim', 'source': 'hypothesis', 'value': 'equivalent', 'value_type': 'string'}}.\nCandidate ID: v2-candidate-0142\nCanonical relation core: 226d0bd75172329395bb90b1777e60815ba9d1142b189a7de53341aea5580206\nOriginal M10 rationale sources (non-normative metadata):\n- ../attempts/attempt-0003/M10/calls/detail-0021/provider_response_envelope.json#content(from-json).candidates[0].rationale\nschema_type scope: schema_type checks only the JSON type at one frozen target JSONPath; it is not full response-schema or OpenAPI validation."
    # V3: v2-candidate-0142
    steps = [{'kind': 'reset_and_authenticate', 'arm': 'metamorphic_query', 'actors': ['actor_a']},
     {'kind': 'http',
      'phase': 'source_query/producer',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:43'},
     {'kind': 'http',
      'phase': 'followup_query[1]',
      'actor': 'actor_a',
      'method': 'GET',
      'path': '/ghost/api/admin/labels/',
      'request_ref': 'r20260920-170620-c734:request:44'}]
    assertions = [{'assertion_id': 'v2-candidate-0142-business-01',
      'class': 'business',
      'predicate_type': 'P17',
      'predicate': {'comparison_basis': 'full_json_value',
                    'expected_difference': None,
                    'family': 'P17',
                    'identity': None,
                    'left': {'path': '$.labels', 'role': 'followup_query:q1', 'value_type': 'array'},
                    'operator': 'equal',
                    'projection': [],
                    'representation': 'multiset',
                    'right': {'path': '$.labels', 'role': 'source_query', 'value_type': 'array'}}},
     {'assertion_id': 'v2-candidate-0142-generic-producer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'producer', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0142-generic-observer-status',
      'class': 'generic',
      'predicate_type': 'status_success',
      'predicate': {'response_ref': 'after', 'type': 'status_success'}},
     {'assertion_id': 'v2-candidate-0142-generic-projection-schema',
      'class': 'generic',
      'predicate_type': 'schema_type',
      'predicate': {'expected_type': 'array',
                    'response_ref': 'after',
                    'target_path': '$.labels',
                    'type': 'schema_type'}}]
    result = uisemtest_runtime.run_case(
        test_id='relation-test-abe1963c608500c81060',
        candidate_id='v2-candidate-0142',
        protocol_kind='V3',
        normal_runs=1,
        source_test_sha256='cff80e60f46d67faaaa78e66c0568ddf5fc695d1883a9ef62c0d87aa8254a849',
        steps=steps,
        assertions=assertions,
    )
    assert result['final_status'] == 'normal_pass'
    assert all(row['status'] == 'pass' for row in result['assertion_calibration'])
