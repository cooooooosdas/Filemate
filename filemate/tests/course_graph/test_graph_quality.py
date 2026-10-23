"""Original synthetic calculator cases, never platform quality measurements."""

import importlib
import json
import subprocess
import sys

import pytest


def inputs():
    gold = {'schema_version': 1, 'synthetic': True, 'authorized': True, 'authorization_id': 'original-fixture',
            'human_gold': True, 'annotator_ids': ['synthetic-a', 'synthetic-b'], 'gold_version': 'fixture-v1',
            'dataset_id': 'calculator-only', 'nodes': ['a', 'b', 'c'],
            'relations': [{'from_id': 'a', 'to_id': 'b', 'relation': 'prerequisite'}],
            'citation_support': [{'item_id': 'c1', 'value': True}, {'item_id': 'c2', 'value': False}],
            'merge_correctness': [{'item_id': 'm1', 'value': True}],
            'relation_invalidity': [{'item_id': 'r1', 'value': True}, {'item_id': 'r2', 'value': True}]}
    prediction = {'schema_version': 1, 'synthetic': True, 'dataset_id': 'calculator-only',
                  'model_version': 'synthetic-fixture', 'prompt_version': 'fixture-v1', 'nodes': ['a', 'd'],
                  'relations': [{'from_id': 'b', 'to_id': 'a', 'relation': 'prerequisite'}],
                  'citation_ids': ['c1', 'c2', 'c3'], 'merge_ids': ['m1', 'm2'],
                  'relation_candidate_ids': ['r1', 'r2', 'r3'], 'rejected_relation_ids': ['r1']}
    return gold, prediction


def evaluate(gold, prediction):
    return importlib.import_module('evaluation.course_graph_quality').evaluate_quality(gold, prediction)


def test_known_sets_and_directed_relation_errors():
    report = evaluate(*inputs())
    metrics = report['metrics']
    assert metrics['nodes']['precision'] == .5 and metrics['nodes']['recall'] == 1 / 3
    assert metrics['nodes']['f1'] == .4
    assert metrics['relations']['tp'] == 0 and metrics['relations']['fp'] == metrics['relations']['fn'] == 1
    assert metrics['citation_support']['rate'] == .5 and metrics['citation_support']['coverage'] == 2 / 3
    assert metrics['merge_correctness']['rate'] == 1 and metrics['merge_correctness']['coverage'] == .5
    assert metrics['invalid_relation_rejection']['rate'] == .5
    assert report['synthetic'] is True and report['result_kind'] == 'calculator_regression_only'
    assert report['real_study_status'] == 'pending_approval'


def test_zero_denominator_and_missing_judgments_remain_null():
    gold, prediction = inputs()
    for data in [gold, prediction]:
        data['nodes'] = []; data['relations'] = []
    gold['citation_support'] = []; gold['merge_correctness'] = []; gold['relation_invalidity'] = []
    result = evaluate(gold, prediction)['metrics']
    assert result['nodes']['precision'] is result['nodes']['recall'] is result['nodes']['f1'] is None
    for name in ['citation_support', 'merge_correctness', 'invalid_relation_rejection']:
        assert result[name]['rate'] is None and result[name]['unjudged'] > 0


@pytest.mark.parametrize('change', [{'authorized': False}, {'authorized': 1}, {'human_gold': False}, {'annotator_ids': []}, {'authorization_id': ''}])
def test_no_authorization_or_human_gold_cannot_produce_scores(change):
    gold, prediction = inputs()
    with pytest.raises(ValueError):
        evaluate(gold | change, prediction)


@pytest.mark.parametrize('change', [{'nodes': ['a', 'a']}, {'rejected_relation_ids': ['not-a-candidate']}, {'synthetic': False}, {'dataset_id': 'other'}])
def test_duplicate_or_mismatched_inputs_refused(change):
    gold, prediction = inputs()
    with pytest.raises(ValueError):
        evaluate(gold, prediction | change)


def test_unknown_judgment_is_not_counted_as_false():
    gold, prediction = inputs()
    gold['citation_support'][0]['value'] = None
    report = evaluate(gold, prediction)
    assert report['metrics']['citation_support']['judged'] == 1
    assert report['metrics']['citation_support']['unjudged'] == 2
    assert report['metrics']['citation_support']['rate'] == 0


def test_cli_refuses_overwrite_and_writes_synthetic_provenance(tmp_path):
    gold, prediction = inputs()
    g, p, out = [tmp_path / n for n in ['gold.json', 'prediction.json', 'report.json']]
    g.write_text(json.dumps(gold), encoding='utf-8'); p.write_text(json.dumps(prediction), encoding='utf-8')
    args = [sys.executable, '-m', 'evaluation.course_graph_quality', '--gold', str(g), '--prediction', str(p), '--output', str(out)]
    completed = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', check=False)
    assert completed.returncode == 0, completed.stderr
    original = out.read_bytes()
    assert json.loads(original)['synthetic'] is True
    assert subprocess.run(args, capture_output=True, check=False).returncode != 0
    assert out.read_bytes() == original
