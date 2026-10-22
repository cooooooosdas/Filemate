import assert from 'node:assert/strict'
import test from 'node:test'
import { resolveGraphScope, readCourseBrowse, courseBrowseQuery, createCoursePreferences } from '../src/course-graph/browse-state.ts'

const storage = () => {
  const data = new Map()
  return { data, getItem: k => data.get(k) ?? null, setItem: (k, v) => data.set(k, v), removeItem: k => data.delete(k) }
}
const scope = 'a'.repeat(64)

test('url_wins_and_mobile_does_not_reuse_desktop_graph', () => {
  assert.equal(readCourseBrowse({}, { desktop: 'graph' }, true).view, 'outline')
  assert.equal(readCourseBrowse({ view: 'evidence' }, { desktop: 'graph' }, false).view, 'evidence')
  assert.equal(resolveGraphScope({ node: 'old-id' }, true), 'source')
  assert.equal(resolveGraphScope({ source: 'old-source' }, true), 'source')
  assert.equal(resolveGraphScope({ graph_scope: 'course', node: 'new-id' }, true), 'course')
  assert.equal(resolveGraphScope({}, false), 'source')
})

test('storage_denied_and_corrupt_fall_back_to_memory', () => {
  const denied = { getItem() { throw Error('denied') }, setItem() { throw Error('denied') }, removeItem() { throw Error('denied') } }
  const a = createCoursePreferences(denied, scope)
  a.set('course1', false, 'evidence')
  assert.equal(a.get('course1', false).desktop, 'evidence')
  const s = storage(); s.setItem(`filemate-course-workspace-v1:${scope}`, '{broken')
  const b = createCoursePreferences(s, scope)
  assert.equal(b.lastCourse(), null)
  b.set('course2', true, 'outline')
  assert.equal(b.get('course2', true).mobile, 'outline')
  const anonymous = createCoursePreferences(s, null)
  const count = s.data.size
  anonymous.set('private', false, 'graph')
  assert.equal(s.data.size, count)
  anonymous.clearMemory(); assert.equal(anonymous.lastCourse(), null)
})

test('two_scopes_do_not_share_courses', () => {
  const s = storage()
  const a = createCoursePreferences(s, scope), b = createCoursePreferences(s, 'b'.repeat(64))
  a.set('course1', false, 'graph')
  assert.equal(b.get('course1', false), null)
  assert.equal(createCoursePreferences(s, scope).lastCourse(), 'course1')
  a.set('course1', true, 'outline')
  assert.deepEqual(a.get('course1', false), { desktop: 'graph', mobile: 'outline' })
})

test('query_round_trip_excludes_private_text', () => {
  const state = readCourseBrowse({ graph_scope: 'course', course: 'c', node: 'n', chapter: '@unassigned',
    source_id: 's', view: 'evidence', relation: ['application', 'related_to'], q: 'private quote' }, null, false)
  assert.ok(state.notice)
  const query = courseBrowseQuery({ ...state, secret: 'sk-private', quote: '<private>' })
  assert.equal(JSON.stringify(query).includes('private'), false)
  assert.deepEqual(readCourseBrowse(query, null, false), { ...state, notice: '' })
  const hidden = readCourseBrowse({ graph_scope: 'course', hide_relations: 'true' }, null, false)
  assert.deepEqual(hidden.relations, [])
  assert.equal(courseBrowseQuery(hidden).hide_relations, 'true')
})

test('invalid_scalar_and_relation_inputs_fall_back_with_notice', () => {
  for (const query of [{ view: ['graph', 'evidence'] }, { view: 'invented' }, { relation: 'invented' },
    { hide_relations: 'true', relation: 'application' }, { course: 'x'.repeat(121) }]) {
    const result = readCourseBrowse(query, null, false)
    assert.ok(result.notice)
    assert.equal(result.view, 'graph')
  }
})

test('missing_course_clears_preference_without_selecting_another', () => {
  const p = createCoursePreferences(storage(), scope)
  p.set('valid', false, 'graph'); p.set('gone', false, 'outline'); p.forget('gone')
  assert.equal(p.get('gone', false), null)
  assert.equal(p.lastCourse(), null)
  assert.equal(p.get('valid', false).desktop, 'graph')
})

test('preferences_are_bounded_and_reject_untrusted_persisted_fields', () => {
  const s = storage(), p = createCoursePreferences(s, scope)
  for (let i = 0; i < 105; i++) p.set(`course-${i}`, false, 'graph')
  const data = JSON.parse([...s.data.values()][0])
  assert.equal(Object.keys(data.courses).length, 100)
  assert.equal(p.get('course-0', false), null)
  assert.equal(p.lastCourse(), 'course-104')
  const contaminated = { ...data, quote: 'secret', courses: { good: { desktop: 'outline', api_key: 'secret' }, bad: { desktop: 'invented' } } }
  s.setItem(`filemate-course-workspace-v1:${scope}`, JSON.stringify(contaminated))
  const restored = createCoursePreferences(s, scope)
  assert.deepEqual(restored.get('good', false), { desktop: 'outline' })
  assert.equal(restored.get('bad', false), null)
})
