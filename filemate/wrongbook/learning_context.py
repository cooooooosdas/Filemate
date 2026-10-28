"""Build bounded review inputs from one actual learning snapshot."""

import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from filemate.course_graph.learning_context import bounded_quotes
from filemate.course_graph.question_links import question_digest
from filemate.course_graph.workspace_snapshot import read_workspace_snapshot
from filemate.execution.data_actions import digest
from filemate.study.knowledge_graph import _after_question_revision
from filemate.understanding.retrieval import PAGE_MARKER, rank_chunks, split_document
from filemate.wrongbook.engine import RULE_VERSION
from filemate.wrongbook.evidence import trusted_attempt
from filemate.wrongbook.repository import ReviewRepository

PROMPT_VERSION = 'wrongbook-analysis-v1'
CONTEXT_BYTES = 128 * 1024


def public_context(context: dict[str, Any]) -> dict[str, Any]:
    """Exclude lifecycle authority from a public context preview."""
    return {k: v for k, v in context.items() if not k.startswith('_')}


def provider_binding(credential_mode: str = 'server') -> dict[str, str]:
    """Describe a provider without resolving or exposing its credentials."""
    if credential_mode not in {'server', 'browser'}:
        raise ValueError('invalid_credential_mode')
    browser = credential_mode == 'browser'
    provider = 'deepseek' if browser else os.getenv('LLM_PROVIDER', 'deepseek')
    model = 'deepseek-v4-flash' if browser else os.getenv('LLM_MODEL', 'deepseek-v4-flash')
    endpoint = 'https://api.deepseek.com' if browser else os.getenv('LLM_BASE_URL', 'https://api.deepseek.com')
    return {'credential_mode': credential_mode, 'provider_identity': digest([provider, endpoint, model]),
            'provider': provider if provider in {'deepseek', 'auto', 'openai', 'openai_compatible'} else 'configured',
            'model': model[:120]}


def _attempt(row: dict[str, Any]) -> dict[str, Any]:
    keys = ('attempt_id', 'user_answer', 'is_correct', 'score', 'feedback', 'created_at',
            'judgement_status', 'judgement_method', 'rule_version', 'answer_revealed', 'purpose')
    return {**{k: row.get(k) for k in keys}, 'trusted_result': trusted_attempt(row)}


class ReviewLearningContext:
    """Read scoped evidence without model calls, inferred relations or writes."""

    def __init__(self, storage, clock=None):
        self.storage = storage
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _links(self, read, detail):
        if detail['read_only_snapshot'] or detail.get('data_error'):
            return [], {}
        try:
            hashed = question_digest(detail['question'])
        except (ValueError, TypeError):
            return [], {}
        snapshots, result, seen = {}, [], set()
        rows = read._conn().execute('''SELECT l.* FROM kg_question_links l
            JOIN kg_course_sources m ON m.course_id=l.course_id AND m.source_id=l.source_id
            WHERE l.artifact_id=? AND l.question_index=? AND l.active=1 AND m.active=1
            ORDER BY l.course_id,l.concept_id,l.link_id''', (detail['artifact_id'], detail['question_index']))
        for row in rows:
            if row['question_digest'] != hashed or row['source_id'] != detail['source_id']:
                continue
            cid = row['course_id']
            if cid not in snapshots:
                snapshots[cid] = read_workspace_snapshot(read, cid)
            snapshot = snapshots[cid]
            root = snapshot.member_to_root.get(row['concept_id'])
            if root not in snapshot.nodes or (cid, root) in seen or not snapshot.refs.get(root):
                continue
            seen.add((cid, root))
            query = urlencode({'graph_scope': 'course', 'course': cid, 'node': root, 'view': 'evidence'})
            result.append({'course_id': cid, 'course_name': snapshot.course['name'], 'concept_id': root,
                'label': snapshot.nodes[root]['label'], 'link_id': row['link_id'],
                'link_revision': row['revision'], 'question_digest': row['question_digest'],
                'evidence_ids': [e['evidence_id'] for e in snapshot.refs[root]],
                'route': '/knowledge-graph?' + query})
        return result, snapshots

    def connections(self, wrong_id: str, *, limit: int = 30, offset: int = 0) -> dict:
        """Page only currently verified question mappings to canonical concepts."""
        if type(limit) is not int or not 1 <= limit <= 30 or type(offset) is not int or not 0 <= offset <= 1_000_000:
            raise ValueError('invalid_page')
        with self.storage.read_snapshot() as read:
            detail = ReviewRepository(read).detail(wrong_id)
            links, _ = self._links(read, detail)
            return {'items': links[offset:offset+limit], 'total': len(links), 'limit': limit,
                    'offset': offset, 'has_more': offset+limit < len(links)}

    @staticmethod
    def _retrieved(read, source_id, stem, existing):
        source = read.get_source(source_id) if source_id else None
        raw = (source or {}).get('raw_text') or ''
        if not raw:
            return []
        chunks = read.list_source_chunks(source_id) or split_document(raw)
        candidates = rank_chunks(stem, chunks, limit=12)
        revision, result = read.get_source_revision(source_id), []
        used = {(q['source_id'], q['char_start'], q['char_end']) for q in existing}
        for chunk in candidates:
            quote = str(chunk.get('content', '')).strip()
            start = raw.find(quote) if quote else -1
            # 旧chunk偏移相对于页内，重复片段无法唯一定位时宁可缺证据。
            if start < 0 or raw.find(quote, start+1) >= 0:
                continue
            end, page = start + min(len(quote), 2000), None
            for marker in PAGE_MARKER.finditer(raw):
                if marker.start() <= start:
                    page = int(marker.group(1))
                elif marker.start() < end:
                    page = None
                    break
            if (source_id, start, end) in used:
                continue
            used.add((source_id, start, end))
            result.append({'evidence_id': 'review-source:' + digest([source_id, revision, start, end]),
                'source_id': source_id, 'source_revision': revision, 'quote': raw[start:end],
                'char_start': start, 'char_end': end, 'page': page, 'relation_kind': 'retrieval_candidate'})
            if len(existing) + len(result) >= 3:
                break
        return result

    def build(self, wrong_id: str, attempt_id: str, course_id: str | None = None,
              *, credential_mode: str = 'server') -> dict:
        """Bind an actual answer and at most five related answers to current inputs."""
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError('aware_clock_required')
        with self.storage.read_snapshot() as read:
            detail, conn = ReviewRepository(read).detail(wrong_id), read._conn()
            artifact = read.get_artifact(detail['artifact_id'])
            row = conn.execute('SELECT * FROM quiz_attempts WHERE attempt_id=? AND artifact_id=? AND question_index=?',
                (attempt_id, detail['artifact_id'], detail['question_index'])).fetchone()
            if row is None or not artifact:
                raise LookupError('作答不存在或不属于此题')
            row = dict(row)
            if (detail.get('data_error') or (not detail['read_only_snapshot'] and not _after_question_revision(row, artifact))
                    or row['question_digest'] not in {'', detail['question_digest']}):
                raise ValueError('question_evidence_changed')
            if len(json.dumps(detail['question'], ensure_ascii=False)) > 60000 or len(str(row['user_answer'] or '')) > 10000:
                raise ValueError('analysis_context_too_large')
            links, snapshots = self._links(read, detail)
            selected = [link for link in links if link['course_id'] == course_id][:12] if course_id else []
            if course_id and not selected:
                raise ValueError('course_scope_unavailable')
            identity = (detail['artifact_id'], detail['question_index'])
            history = [dict(r) for r in conn.execute('''SELECT * FROM quiz_attempts
                WHERE artifact_id=? AND question_index=? AND attempt_id!=? ORDER BY created_at DESC,rowid DESC LIMIT 5''',
                (*identity, attempt_id))]
            count = conn.execute('SELECT COUNT(*) FROM quiz_attempts WHERE artifact_id=? AND question_index=?', identity).fetchone()[0]
            deps, quotes, graph_binding = {}, [], None
            if detail['source_id']:
                deps[detail['source_id']] = {'source_id': detail['source_id'],
                    'source_revision': read.get_source_revision(detail['source_id']), 'membership_revision': None}
            if selected:
                snapshot = snapshots[course_id]
                graph_binding = {'course_id': course_id, 'graph_digest': snapshot.graph_digest}
                roots = [item['concept_id'] for item in selected]
                for root in roots:
                    for ref in snapshot.refs.get(root, []):
                        sid = ref['source_id']
                        deps[sid] = {'source_id': sid, 'source_revision': snapshot.fingerprints[sid],
                                     'membership_revision': snapshot.sources[sid]['revision']}
                for quote in bounded_quotes(read, snapshot, roots, limit=3, characters=6000):
                    quote['source_revision'] = snapshot.fingerprints[quote['source_id']]
                    quote['relation_kind'] = 'confirmed_graph'
                    quotes.append(quote)
            if len(quotes) < 3:
                remaining = 6000 - sum(len(q['quote']) for q in quotes)
                for quote in self._retrieved(read, detail['source_id'], str(detail['question'].get('stem', '')), quotes):
                    if remaining <= 0:
                        break
                    quote['quote'] = quote['quote'][:remaining]
                    quote['char_end'] = quote['char_start'] + len(quote['quote'])
                    quotes.append(quote)
                    remaining -= len(quote['quote'])
            confirmed = detail['error_cause_source'] == 'user'
            result = {'ref': {k: detail[k] for k in ('wrong_id', 'artifact_id', 'question_index', 'question_digest')},
                'question': detail['question'], 'attempt': _attempt(row), 'related_attempts': list(map(_attempt, history)),
                'confirmed_diagnosis': {'error_causes': detail['error_causes'] if confirmed else [],
                    'primary_cause': detail['error_cause'] if confirmed else None,
                    'note': detail['error_cause_note'] if confirmed else '', 'custom_tags': detail['custom_tags']},
                'review_state': ReviewRepository.state(detail), 'read_only_snapshot': detail['read_only_snapshot'],
                'graph_links': selected, 'source_evidence': quotes, 'next_actions': [],
                'coverage': {'total_attempts': count, 'related_attempts_omitted': max(0, count-1-len(history)),
                    'graph_links_in_scope': len(selected), 'quotes': len(quotes),
                    'source_evidence_status': 'available' if quotes else 'not_found', 'bounded_context': True,
                    'suggestions_available': False},
                **provider_binding(credential_mode), 'prompt_version': PROMPT_VERSION, 'rule_version': RULE_VERSION,
                '_source_dependencies': [deps[k] for k in sorted(deps)], '_graph_binding': graph_binding}
            result['input_digest'] = digest(result)
            result['context_revision'] = digest({'input_digest': result['input_digest'], 'revision': detail['revision']})
            if len(json.dumps(public_context(result), ensure_ascii=False).encode('utf-8')) > CONTEXT_BYTES:
                raise ValueError('analysis_context_too_large')
            result['as_of'] = now.astimezone(timezone.utc).isoformat()
            return result
