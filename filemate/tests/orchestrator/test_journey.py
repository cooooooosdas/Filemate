"""Owned backend and Vite, real domain HTTP and independent backup restores."""

import importlib
import importlib.util

import pytest


@pytest.fixture(scope='module')
def journey(tmp_path_factory):
    assert importlib.util.find_spec('scripts.acceptance.orchestrator_journey'), 'journey driver missing'
    driver = importlib.import_module('scripts.acceptance.orchestrator_journey')
    return driver.run_journey(tmp_path_factory.mktemp('synthetic-orchestrator') / 'candidate')


def test_goal_to_schedule_to_completion_and_restart(journey):
    assert journey['status'] == 'PASS'
    assert journey['checks']['real_domain_completion'] and journey['checks']['restart_preserves_completion']
    assert journey['checks']['schedule_commands_preserve_domain_fingerprints']
    assert journey['checks']['undo_preserves_completion']


def test_restore_keeps_references_but_invalidates_tokens(journey):
    assert journey['checks']['managed_restore_fingerprints_match']
    assert journey['checks']['managed_restore_rejects_overwrite']
    assert journey['checks']['personal_restore_keeps_refs']
    assert journey['checks']['personal_restore_invalidates_old_tokens']


def test_delete_one_source_only_stales_affected_schedule(journey):
    assert journey['checks']['unrelated_source_delete_preserves_view']
    assert journey['checks']['affected_source_delete_stales_view']


def test_api_via_dev_proxy_returns_json_for_both_accept_headers(journey):
    assert journey['checks']['proxy_json_accept'] and journey['checks']['proxy_html_accept']
    assert journey['checks']['network_outage_preserves_data']
