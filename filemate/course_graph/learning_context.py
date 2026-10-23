"""Bound and recheck literal citations shared by practice and the read-only assistant."""


def bounded_quotes(read, snapshot, node_ids, *, limit=12, characters=12_000):
    """Return only current literal source spans with deterministic citation identities."""
    result, seen, used, sources = [], set(), 0, {}
    for nid in node_ids:
        for ref in snapshot.refs.get(nid, []):
            if ref['evidence_id'] in seen or len(result) >= limit or used >= characters:
                continue
            seen.add(ref['evidence_id'])
            sid = ref['source_id']
            if sid not in sources:
                sources[sid] = read.get_source(sid)
            source = sources[sid]
            if source is None or snapshot.fingerprints.get(sid) != ref['source_revision']:
                continue
            text, start, end = source.get('raw_text') or '', ref['char_start'], ref['char_end']
            if not 0 <= start < end <= len(text) or text[start:end] != ref['excerpt']:
                continue
            quote = ref['excerpt'][:characters - used]
            result.append({'evidence_id': ref['evidence_id'], 'concept_id': nid, 'source_id': sid,
                           'quote': quote, 'page': ref['page'], 'char_start': start,
                           'char_end': start + len(quote), 'truncated': len(quote) < end - start})
            used += len(quote)
    return result
