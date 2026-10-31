"""Budget and order behavior, independent of model calls."""

import pytest
from pydantic import ValidationError

from .conftest import module, snapshot


def arrange(world, minutes=30, **options):
    snap = snapshot(world)
    projection = module('task_views').project_tasks(snap)
    model = module('models')
    return module('scheduler').build_schedule(snap, projection, model.ScheduleOptions(available_minutes=minutes, **options))


def test_same_snapshot_is_deterministic(world):
    assert arrange(world).model_dump() == arrange(world).model_dump()
    assert arrange(world).estimated_minutes == 15


def test_zero_minutes_defers_every_pending_task(world):
    result = arrange(world, 0)
    assert result.selected == [] and result.estimated_minutes == 0
    assert result.deferred[0]['reason'] == 'budget'


def test_pins_and_manual_order_survive_budget_reduction(world):
    store = world['store']
    goal = store.get_artifact(world['goal'])
    goal['content']['tasks'] += [{'task_id': 'baseline-quiz', 'status': 'pending', 'title': '练习'}]
    store.update_artifact(world['goal'], title='', content=goal['content'])
    order = [f"goal:{world['goal']}:baseline-quiz", f"goal:{world['goal']}:review-source"]
    result = arrange(world, 20, item_order=order, pinned_ids=[order[0]])
    assert [t.task_id for t in result.selected] == [order[0]]
    assert result.deferred[0]['task_id'] == order[1]
    reduced = arrange(world, 15, item_order=order, pinned_ids=[order[0]])
    assert reduced.selected[0].task_id == order[1]
    assert reduced.deferred[0]['task_id'] == order[0] and reduced.deferred[0]['pinned']


def test_overbudget_urgent_task_is_deferred_with_reason(world):
    result = arrange(world, 10)
    assert not result.selected and result.deferred_counts == {'budget': 1}


def test_unknown_minutes_and_inactive_refs_are_explicit(world):
    store = world['store']
    goal = store.get_artifact(world['goal'])
    goal['content']['tasks'][0]['task_id'] = 'unknown-template'
    store.update_artifact(world['goal'], title='', content=goal['content'])
    assert arrange(world).deferred_counts == {'estimate_required': 1}
    with pytest.raises(module('models').OrchestratorError):
        arrange(world, item_order=['foreign-task'])


def test_manual_minutes_are_bounded_estimates(world):
    tid = f"goal:{world['goal']}:review-source"
    result = arrange(world, 10, minute_overrides={tid: 8})
    assert result.selected[0].estimate_source == 'user_estimate' and result.estimated_minutes == 8
    model = module('models').ScheduleOptions
    for value in [True, 1.5, -1, 1441]:
        with pytest.raises(ValidationError):
            model(available_minutes=value)
    for changes in [{'minute_overrides': {tid: True}}, {'minute_overrides': {tid: 241}}, {'item_order': [tid, tid]}, {'pinned_ids': [tid]}]:
        with pytest.raises(ValidationError):
            model(available_minutes=30, **changes)


def test_completed_is_never_reopened(world):
    store = world['store']
    goal = store.get_artifact(world['goal'])
    goal['content']['tasks'][0]['status'] = 'completed'
    store.update_artifact(world['goal'], title='', content=goal['content'])
    result = arrange(world, 0)
    assert not result.selected and len(result.completed) == 1 and not result.deferred


def test_shanghai_midnight_and_same_day_deadline(world):
    from datetime import datetime, timezone
    world['now'][0] = datetime(2026, 10, 31, 16, tzinfo=timezone.utc)
    assert snapshot(world).study_date == '2026-11-01'
    result = arrange(world)
    assert result.selected[0].due_date == '2026-11-01'


def test_confirmed_prerequisite_orders_tasks_and_cycles_are_blocked(world):
    snap = snapshot(world)
    projection = module('task_views').project_tasks(snap)
    base = projection.tasks[0]
    a = base.model_copy(update={'task_id': 'z-prerequisite', 'dependency_ids': []})
    b = base.model_copy(update={'task_id': 'a-dependent', 'dependency_ids': ['z-prerequisite']})
    projection.tasks = [b, a]
    options = module('models').ScheduleOptions(available_minutes=30)
    result = module('scheduler').build_schedule(snap, projection, options)
    assert [t.task_id for t in result.selected] == ['z-prerequisite', 'a-dependent']
    a.dependency_ids = ['a-dependent']
    result = module('scheduler').build_schedule(snap, projection, options)
    assert result.selected == [] and result.deferred_counts == {'dependency_cycle': 2}


def test_missing_prerequisite_never_assumes_no_dependency(world):
    snap = snapshot(world)
    projection = module('task_views').project_tasks(snap)
    projection.tasks[0] = projection.tasks[0].model_copy(update={'dependency_ids': ['not-in-scope']})
    result = module('scheduler').build_schedule(snap, projection, module('models').ScheduleOptions(available_minutes=60))
    assert not result.selected and result.deferred_counts == {'prerequisite_unavailable': 1}
