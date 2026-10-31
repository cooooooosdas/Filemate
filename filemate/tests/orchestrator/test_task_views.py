"""Task identity regressions with hand-checked domain facts."""

from copy import deepcopy

from .conftest import module, snapshot, wrong


def project(world):
    return module('task_views').project_tasks(snapshot(world))


def test_same_wrong_cycle_one_action_with_all_origins(world):
    wid = wrong(world)
    snap = snapshot(world)
    due = snap.facts['reviews'][0]['next_review_at']
    snap.facts['goal']['tasks'].append({'task_id': 'explicit-review', 'title': '独立复练', 'status': 'pending', 'action': 'independent_review', 'focus_wrong_id': wid, 'next_review_at': due})
    result = module('task_views').project_tasks(snap)
    reviews = [t for t in result.tasks if t.kind == 'review']
    assert len(reviews) == 1 and len(reviews[0].origin_refs) == 2


def test_diagnosis_does_not_create_cycle(world):
    wid = wrong(world)
    first = project(world)
    conn = world['store']._conn()
    conn.execute('UPDATE wrong_questions SET revision=revision+1,error_cause=? WHERE wrong_id=?', ('careless', wid))
    conn.commit()
    assert [t.task_id for t in project(world).tasks] == [t.task_id for t in first.tasks]


def test_new_due_cycle_keeps_old_history(world):
    wid = wrong(world)
    first = project(world)
    conn = world['store']._conn()
    conn.execute('UPDATE wrong_questions SET next_review_at=? WHERE wrong_id=?', ('2026-11-02T08:00:00+00:00', wid))
    conn.commit()
    second = project(world)
    assert next(t for t in first.tasks if t.kind == 'review').task_id != next(t for t in second.tasks if t.kind == 'review').task_id
    assert next(t for t in second.tasks if t.kind == 'review').eligibility == 'not_due'


def test_composite_plan_is_not_swallowed_by_one_review(world):
    wrong(world)
    snap = snapshot(world)
    snap.facts['plans'] = [{'plan_id': 'synthetic-plan', 'source_id': world['sources'][0], 'status': 'active', 'exam_date': '2026-11-05', 'days': [{'day_index': 0, 'day': 1, 'date': '2026-10-31', 'duration_minutes': 20, 'completed': False, 'composite': True}]}]
    result = module('task_views').project_tasks(snap)
    assert len([t for t in result.tasks if t.kind in ('plan', 'review')]) == 2
    assert any(t.task_id == 'plan:synthetic-plan:0' for t in result.tasks)


def test_completion_and_semester_revision_do_not_mint_new_task(world):
    snap = snapshot(world)
    snap.facts['semester'] = [{'artifact_id': 'personal-semester-v1', 'task_id': 'math-week-1', 'title': '训练', 'minutes': 30, 'due_date': '2026-10-31', 'completed': False}]
    first = module('task_views').project_tasks(snap)
    copied = deepcopy(snap)
    copied.facts['semester'][0].update(completed=True, completed_at='2026-10-31T09:00:00Z')
    second = module('task_views').project_tasks(copied)
    task = next(t for t in second.completed if t.kind == 'semester')
    assert task.task_id == next(t for t in first.tasks if t.kind == 'semester').task_id
    assert task.completion_ref and task.status == 'completed'


def test_task_routes_resolve_original_resource(world):
    result = project(world)
    task = result.tasks[0]
    assert task.route.startswith('/goals?') and world['goal'] in task.route
    assert task.estimated_minutes == 15 and task.estimate_source == 'rule_default'


def test_confirmed_graph_plan_dependencies_are_projected(world):
    snap = snapshot(world)
    snap.facts['plans'] = [{'plan_id': 'graph-plan', 'source_id': world['sources'][0], 'status': 'active', 'exam_date': '2026-11-05', 'days': [
        {'day_index': i, 'day': i + 1, 'date': '2026-10-31', 'duration_minutes': 10, 'completed': False} for i in range(2)]}]
    snap.facts['plan_links'] = [{'plan_id': 'graph-plan', 'day_index': i, 'concept_id': f'c{i}'} for i in range(2)]
    snap.facts['graph'] = [{'relation': {'from_id': 'c0', 'to_id': 'c1', 'type': 'prerequisite'}}]
    projected = module('task_views').project_tasks(snap)
    target = next(t for t in projected.tasks if t.task_id == 'plan:graph-plan:1')
    assert target.dependency_ids == ['plan:graph-plan:0']


def test_real_saved_plan_uses_daily_plan_and_zero_based_completion(world):
    store = world['store']
    plan = {'title': '原创合成学习计划', 'exam_date': '2026-11-05', 'daily_minutes': 15, 'goal': '复习',
            'daily_plan': [{'date': '2026-10-31', 'focus': '栈', 'duration_minutes': 15, 'tasks': ['阅读并练习']}]}
    aid = store.save_artifact(source_id=world['sources'][0], artifact_type='study_plan', content=plan)
    saved = store.create_study_plan(artifact_id=aid, source_id=world['sources'][0], plan=plan)
    tid = f"plan:{saved['plan_id']}:0"
    assert any(t.task_id == tid for t in project(world).tasks)
    store.set_study_plan_day(saved['plan_id'], 0, completed=True)
    assert any(t.task_id == tid for t in project(world).completed)
