"""Calculate declared human-gold graph quality without inventing missing judgments."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Identity = Annotated[str, Field(min_length=1, max_length=120)]
Identities = Annotated[list[Identity], Field(max_length=30_000)]


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Relation(Strict):
    from_id: Identity
    to_id: Identity
    relation: Literal['prerequisite', 'depends_on', 'part_of', 'contains', 'application', 'related_to']


class Judgment(Strict):
    item_id: Identity
    value: bool | None


class Graph(Strict):
    schema_version: Literal[1]
    synthetic: bool
    dataset_id: Identity
    nodes: Identities
    relations: list[Relation] = Field(max_length=30_000)


class Gold(Graph):
    authorized: Literal[True]
    authorization_id: Identity
    human_gold: Literal[True]
    annotator_ids: list[Identity] = Field(min_length=2, max_length=20)
    gold_version: Identity
    citation_support: list[Judgment] = Field(default_factory=list, max_length=30_000)
    merge_correctness: list[Judgment] = Field(default_factory=list, max_length=30_000)
    relation_invalidity: list[Judgment] = Field(default_factory=list, max_length=30_000)


class Prediction(Graph):
    model_version: Identity
    prompt_version: Identity
    citation_ids: Identities = Field(default_factory=list)
    merge_ids: Identities = Field(default_factory=list)
    relation_candidate_ids: Identities = Field(default_factory=list)
    rejected_relation_ids: Identities = Field(default_factory=list)


def _unique(values):
    if len(set(values)) != len(values):
        raise ValueError('duplicate_identity_or_relation')
    return set(values)


def _relations(values):
    return _unique([(r.from_id, r.relation, r.to_id) for r in values])


def _set_metrics(gold, prediction):
    tp, fp, fn = len(gold & prediction), len(prediction - gold), len(gold - prediction)
    return {'tp': tp, 'fp': fp, 'fn': fn,
            'precision': tp / (tp + fp) if tp + fp else None,
            'recall': tp / (tp + fn) if tp + fn else None,
            'f1': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
            'null_reason': 'zero_denominator' if not prediction or not gold else None}


def _judgments(values):
    _unique([v.item_id for v in values])
    return {v.item_id: v.value for v in values}


def _rate(ids, judgments):
    values = [judgments[i] for i in ids if judgments.get(i) is not None]
    return {'rate': sum(values) / len(values) if values else None, 'positive': sum(values),
            'judged': len(values), 'total_candidates': len(ids), 'unjudged': len(ids) - len(values),
            'coverage': len(values) / len(ids) if ids else None,
            'null_reason': None if values else 'no_human_judgments_or_zero_candidates'}


def _fingerprint(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, allow_nan=False).encode('utf-8')).hexdigest()


def evaluate_quality(gold: dict, prediction: dict) -> dict:
    """Compute exact directed-set and covered human-judgment metrics, never AI self-scores."""
    if (not isinstance(gold, dict) or gold.get('authorized') is not True or gold.get('human_gold') is not True
            or type(gold.get('schema_version')) is not int or not isinstance(prediction, dict)
            or type(prediction.get('schema_version')) is not int):
        raise ValueError('explicit_authorized_human_gold_required')
    g, p = Gold.model_validate(gold), Prediction.model_validate(prediction)
    if g.synthetic != p.synthetic or g.dataset_id != p.dataset_id:
        raise ValueError('dataset_or_sample_kind_mismatch')
    _unique(g.annotator_ids)
    citations, merges, candidates, rejected = [_unique(v) for v in
        (p.citation_ids, p.merge_ids, p.relation_candidate_ids, p.rejected_relation_ids)]
    if not rejected <= candidates:
        raise ValueError('rejection_not_in_candidates')
    invalidity = _judgments(g.relation_invalidity)
    invalid = {i for i in candidates if invalidity.get(i) is True}
    judged = {i for i in candidates if invalidity.get(i) is not None}
    return {'schema_version': 1, 'synthetic': g.synthetic, 'dataset_id': g.dataset_id,
            'result_kind': 'calculator_regression_only' if g.synthetic else 'declared_human_gold_quality',
            'real_study_status': 'pending_approval', 'gold_version': g.gold_version,
            'model_version': p.model_version, 'prompt_version': p.prompt_version,
            'input_hashes': {'gold_sha256': _fingerprint(gold), 'prediction_sha256': _fingerprint(prediction)},
            'metrics': {'nodes': _set_metrics(_unique(g.nodes), _unique(p.nodes)),
                'relations': _set_metrics(_relations(g.relations), _relations(p.relations)),
                'citation_support': _rate(citations, _judgments(g.citation_support)),
                'merge_correctness': _rate(merges, _judgments(g.merge_correctness)),
                'invalid_relation_rejection': {'rate': len(invalid & rejected) / len(invalid) if invalid else None,
                    'rejected_invalid': len(invalid & rejected), 'known_invalid': len(invalid),
                    'judged': len(judged), 'unjudged': len(candidates - judged), 'total_candidates': len(candidates),
                    'coverage': len(judged) / len(candidates) if candidates else None,
                    'rejected_known_valid': len({i for i in rejected if invalidity.get(i) is False}),
                    'null_reason': None if invalid else 'no_human_confirmed_invalid_relations'}},
            'limitations': ['Authorization and annotator declarations require separate record verification.',
                            'Missing judgments stay unjudged; covered rates do not estimate full-population quality.',
                            'Synthetic regression numbers are not platform extraction quality or learning outcomes.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gold', type=Path, required=True)
    parser.add_argument('--prediction', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = evaluate_quality(json.loads(args.gold.read_text(encoding='utf-8')),
                                  json.loads(args.prediction.read_text(encoding='utf-8')))
        with args.output.open('x', encoding='utf-8') as output:
            json.dump(report, output, ensure_ascii=False, indent=2, allow_nan=False)
    except (OSError, ValueError) as exc:
        parser.exit(2, f'Quality calculation refused ({type(exc).__name__}); validate inputs and use a new output path.\n')
    print(json.dumps({'saved': str(args.output), 'synthetic': report['synthetic'], 'result_kind': report['result_kind']}))


if __name__ == '__main__':
    main()
