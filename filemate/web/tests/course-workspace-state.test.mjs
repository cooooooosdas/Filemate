import assert from 'node:assert/strict'
import test from 'node:test'
import { createCourseWorkspaceController } from '../src/course-graph/workspace-state.ts'

const browse = (courseId = 'c', extra = {}) => ({ scope: 'course', courseId, view: 'graph', nodeId: '', chapterId: '', sourceId: '', relations: null, notice: '', ...extra })
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r }); return { promise, resolve } }
const node = id => ({ id, label: id, aliases: [], chapter_ids: ['child'], source_count: 1, member_count: 1, source_status: 'available' })
function workspaceApi(overrides = {}) {
  const identity = cid => ({ course_id: cid, graph_digest: 'a'.repeat(64) })
  return {
    getCourseBrowserScope: async () => 's',
    getCourseWorkspace: async cid => ({ ...identity(cid), groups: [], sources: [], total_concepts: 1 }),
    getCourseCanvas: async (cid, _filters, focus) => ({ ...identity(cid), mode: 'concepts', nodes: [node(focus || 'n')], edges: [], groups: [], requested_id: focus || null, resolved_id: focus || null }),
    getCourseConceptPage: async (cid, options) => ({ ...identity(cid), items: [{ ...node('n'), matched_label: 'n' }], total: 1, offset: options.offset || 0, limit: 50 }),
    getCourseWorkspaceDetail: async (cid, nid) => ({ ...identity(cid), node: node(nid), requested_id: nid, resolved_id: nid, source_refs: [], total_refs: 0 }),
    getCourseChapterPath: async cid => ({ ...identity(cid), items: [{ id: 'parent' }, { id: 'child' }] }),
    getCourseCitation: async (cid, nid, eid) => ({ ...identity(cid), requested_id: nid, resolved_id: nid, evidence_id: eid, quote: 'literal' }),
    ...overrides,
  }
}

test('late_old_course_and_digest_mismatch_cannot_mix', async () => {
  const old = deferred(); let reads = 0
  const defaults = workspaceApi()
  const api = workspaceApi({ getCourseWorkspace: cid => cid === 'old' ? old.promise : defaults.getCourseWorkspace(cid),
    getCourseCanvas: async (...args) => { reads++; return { ...await defaults.getCourseCanvas(...args), graph_digest: 'b'.repeat(64) } } })
  const controller = createCourseWorkspaceController(api)
  const pending = controller.open(browse('old'))
  await controller.open(browse('new'))
  old.resolve(await defaults.getCourseWorkspace('old')); await pending
  assert.equal(controller.state.browse.courseId, 'new')
  assert.equal(reads, 3) // one old request and exactly two new bundles
  assert.equal(controller.state.stale, true)
  assert.equal(controller.state.canvas, null)
})

test('one_digest_reread_commits_only_a_consistent_bundle', async () => {
  const defaults = workspaceApi(); let reads = 0
  const controller = createCourseWorkspaceController(workspaceApi({ getCourseCanvas: async (...args) => {
    const result = await defaults.getCourseCanvas(...args)
    return { ...result, graph_digest: ++reads === 1 ? 'b'.repeat(64) : result.graph_digest }
  } }))
  await controller.open(browse('c', { nodeId: 'n' }))
  assert.equal(reads, 2)
  assert.equal(controller.state.canvas.graph_digest, controller.state.detail.graph_digest)
  assert.equal(controller.state.error, '')
})

test('search_locates_unloaded_node_and_clears_only_conflicting_filters', async () => {
  const defaults = workspaceApi()
  const controller = createCourseWorkspaceController(workspaceApi({ getCourseCanvas: async (cid, filter, focus, ...rest) => {
    if (focus && filter.source_id) throw Object.assign(new Error('outside'), { status: 409, code: 'focus_outside_filter' })
    return defaults.getCourseCanvas(cid, filter, focus, ...rest)
  } }))
  await controller.open(browse('c', { chapterId: 'parent', sourceId: 'source', relations: ['related_to'] }))
  await controller.search('unloaded', true)
  await controller.selectSearchResult(node('far-away'))
  assert.equal(controller.state.browse.nodeId, 'far-away')
  assert.equal(controller.state.browse.chapterId, 'parent')
  assert.equal(controller.state.browse.sourceId, '')
  assert.deepEqual(controller.state.browse.relations, ['related_to'])
  assert.ok(controller.state.notice)
})

test('search_debounce_enter_cancels_pending_timer', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const defaults = workspaceApi(); const calls = []
  const controller = createCourseWorkspaceController(workspaceApi({ getCourseConceptPage: async (cid, options, signal) => {
    if (options.q) calls.push(options.q)
    return defaults.getCourseConceptPage(cid, options, signal)
  } }))
  await controller.open(browse())
  const a = controller.search('first')
  const b = controller.search('second', true)
  await Promise.all([a, b]); t.mock.timers.tick(1000)
  assert.deepEqual(calls, ['second'])
  const c = controller.search('disposed'); controller.dispose(); t.mock.timers.tick(1000); await c
  assert.deepEqual(calls, ['second'])
})

test('network_error_keeps_only_same_identity_snapshot', async () => {
  const api = workspaceApi(), controller = createCourseWorkspaceController(api)
  await controller.open(browse())
  const previous = controller.state.canvas
  api.getCourseWorkspace = async () => { throw new Error('offline') }
  await controller.refresh()
  assert.equal(controller.state.canvas, previous)
  assert.equal(controller.state.stale, true)
  await controller.open(browse('different'))
  assert.equal(controller.state.canvas, null)
})

test('identity_reset_clears_detail_and_aborts_reads', async () => {
  const api = workspaceApi(), controller = createCourseWorkspaceController(api)
  await controller.open(browse('c', { nodeId: 'n' }))
  const late = deferred(); let signal
  api.getCourseWorkspace = (_cid, _options, s) => { signal = s; return late.promise }
  const pending = controller.refresh()
  controller.resetIdentity('new-scope')
  assert.equal(signal.aborted, true)
  assert.equal(controller.state.detail, null)
  late.resolve({ course_id: 'c', graph_digest: 'a'.repeat(64) }); await pending
  assert.equal(controller.state.navigation, null)
})

test('revoked_node_clears_selection', async () => {
  const controller = createCourseWorkspaceController(workspaceApi({ getCourseWorkspaceDetail: async () => {
    throw Object.assign(new Error('gone'), { status: 404, code: 'concept_not_found' })
  } }))
  await controller.open(browse('c', { nodeId: 'gone' }))
  assert.equal(controller.state.browse.nodeId, '')
  assert.equal(controller.state.detail, null)
  assert.ok(controller.state.notice)
  assert.ok(controller.state.navigation)
})

test('mutation_refresh_failure_never_replays_write', async () => {
  const api = workspaceApi(), controller = createCourseWorkspaceController(api)
  await controller.open(browse('c', { nodeId: 'n' }))
  api.getCourseWorkspace = async () => { throw new Error('offline') }
  await controller.invalidateAfterMutation()
  assert.equal(controller.state.detail, null)
  assert.equal(controller.state.citation, null)
  assert.match(controller.state.notice, /已保存/)
  assert.ok(controller.state.error)
})

test('late_citation_or_new_digest_is_never_attached_to_old_detail', async () => {
  const api = workspaceApi(), controller = createCourseWorkspaceController(api)
  await controller.open(browse('c', { nodeId: 'one' }))
  const late = deferred()
  api.getCourseCitation = () => late.promise
  const pending = controller.openCitation('e')
  await controller.selectNode('two')
  late.resolve({ course_id: 'c', graph_digest: 'a'.repeat(64), quote: 'old' }); await pending
  assert.equal(controller.state.citation, null)
  api.getCourseCitation = async () => ({ course_id: 'c', graph_digest: 'b'.repeat(64), quote: 'changed' })
  await controller.openCitation('e')
  assert.equal(controller.state.citation, null)
  assert.ok(controller.state.notice)
})
