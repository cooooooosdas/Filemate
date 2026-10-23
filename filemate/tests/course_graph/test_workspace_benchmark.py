"""Safety contracts for synthetic workspace benchmarks."""
from pathlib import Path

import pytest


def benchmark():
    from scripts.acceptance import course_workspace_benchmark
    return course_workspace_benchmark


def test_existing_or_relative_output_refused(tmp_path):
    with pytest.raises(ValueError):
        benchmark().prepare(Path('relative'), [100])
    with pytest.raises(ValueError):
        benchmark().prepare(tmp_path, [100])
    assert not list(tmp_path.iterdir())


def test_requested_sizes_are_exact_and_identity_isolated(tmp_path):
    result = benchmark().prepare(tmp_path / 'new', [3, 7])
    assert [row['total_nodes'] for row in result['cases']] == [3, 7]
    assert len({row['course_id'] for row in result['cases']}) == 2
    assert len({row['database'] for row in result['cases']}) == 2
    assert result['synthetic'] is True
    with pytest.raises(ValueError):
        benchmark().prepare(tmp_path / 'bad', [0, 10001])


def test_benchmark_results_distinguish_unmeasured_browser_fields(tmp_path):
    result = benchmark().prepare(tmp_path / 'new', [2])
    browser = result['cases'][0]['browser']
    assert browser['first_interactive_ms'] is None
    assert browser['max_long_task_ms'] is None
    assert browser['heap_bytes'] is None
    assert browser['measurement_status'] == 'not_measured'
