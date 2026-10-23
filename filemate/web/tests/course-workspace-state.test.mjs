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


test('search_pagination_reaches_the_51st_identical_label_and_drops_late_pages', async () => {
  const defaults = workspaceApi(), requests = [], late = deferred()
  const controller = createCourseWorkspaceController(workspaceApi({ getCourseConceptPage: async (cid, options) => {
    if (!options.q) return defaults.getCourseConceptPage(cid, options)
    requests.push([options.q, options.offset || 0])
    if (options.q === 'late' && options.offset === 50) return late.promise
    const offset = options.offset || 0
    return { course_id: cid, graph_digest: 'a'.repeat(64), total: 51, limit: 50, offset,
      items: Array.from({ length: Math.min(50, 51-offset) }, (_, i) => ({ ...node(`n${offset+i}`), label: '相同概念' })) }
  } }))
  await controller.open(browse()); await controller.search('相同', true); await controller.pageSearch(50)
  assert.equal(controller.state.searchPage.items[0].id, 'n50')
  await controller.selectSearchResult(controller.state.searchPage.items[0])
  assert.equal(controller.state.detail.resolved_id, 'n50')
  await controller.search('late', true)
  const pending = controller.pageSearch(50)
  await controller.search('new', true)
  late.resolve({ course_id: 'c', graph_digest: 'a'.repeat(64), items: [node('stale')], offset: 50, total: 51, limit: 50 }); await pending
  assert.equal(controller.state.searchPage.offset, 0)
  assert.notEqual(controller.state.searchPage.items[0]?.id, 'stale')
  assert.ok(requests.some(([q, offset]) => q === '相同' && offset === 50))
})

test('refresh_invalidates_search_from_a_different_digest', async () => {
  const api = workspaceApi(), controller = createCourseWorkspaceController(api)
  await controller.open(browse()); await controller.search('n', true)
  for (const method of ['getCourseWorkspace', 'getCourseCanvas', 'getCourseConceptPage']) {
    const previous = api[method]
    api[method] = async (...args) => ({ ...await previous(...args), graph_digest: 'b'.repeat(64) })
  }
  await controller.refresh()
  assert.equal(controller.state.stale, false)
  assert.equal(controller.state.navigation.graph_digest, 'b'.repeat(64))
  assert.ok(controller.state.searchPage === null || controller.state.searchPage.graph_digest === 'b'.repeat(64))
})

test('url_filter_changes_reset_offsets_and_refresh_clamps_a_shrunken_page', async () => {
  const defaults = workspaceApi(); let total = 75
  const controller = createCourseWorkspaceController(workspaceApi({ getCourseConceptPage: async (cid, options) => {
    const result = await defaults.getCourseConceptPage(cid, options)
    const count = options.chapter_id ? 2 : total, offset = options.offset || 0
    return { ...result, total: count, items: offset >= count ? [] : [node(`n${offset}`)] }
  } }))
  await controller.open(browse()); await controller.page(50)
  assert.equal(controller.state.listPage.offset, 50)
  await controller.open(browse('c', { chapterId: 'small' }))
  assert.equal(controller.state.listPage.offset, 0)
  assert.ok(controller.state.listPage.items.length)
  await controller.open(browse()); await controller.page(50); total = 2
  await controller.refresh()
  assert.equal(controller.state.listPage.offset, 0)
  assert.ok(controller.state.listPage.items.length)
})

test('chapter_directory_reads_children_and_a_consistent_ancestor_path', async () => {
  const defaults = workspaceApi(), parents = []
  const controller = createCourseWorkspaceController(workspaceApi({ getCourseWorkspace: async (cid, options) => {
    parents.push(options.parent_id); return defaults.getCourseWorkspace(cid, options)
  } }))
  await controller.open(browse()); await controller.open(browse('c', { chapterId: 'child' }))
  assert.deepEqual(parents, ['@root', 'child'])
  assert.deepEqual(controller.state.chapterPath.items.map(g => g.id), ['parent', 'child'])
})

test('selection_keeps_canvas_identity_and_expansion_alone_loads_neighbors', async () => {
  const defaults = workspaceApi(), calls = []
  const controller = createCourseWorkspaceController(workspaceApi({ getCourseCanvas: async (...args) => {
    calls.push(args[2]); const result = await defaults.getCourseCanvas(...args)
    return { ...result, nodes: args[2] ? [node(args[2]), node('external-neighbor')] : [node('n'), node('unrelated')] }
  } }))
  await controller.open(browse())
  const original = controller.state.canvas
  await controller.selectNode('n')
  assert.equal(controller.state.canvas, original)
  assert.deepEqual(calls, [undefined])
  assert.equal(controller.state.detail.resolved_id, 'n')
  await controller.expandNode('n')
  assert.deepEqual(controller.state.canvas.nodes.map(n => n.id), ['n', 'external-neighbor'])
  await controller.selectNode('external-neighbor'); await controller.refresh()
  assert.equal(calls.at(-1), 'n') // refresh keeps the explicit canvas focus
})

test('late_selection_and_new_digest_never_attach_detail_to_old_canvas', async () => {
  const api = workspaceApi(), controller = createCourseWorkspaceController(api), late = deferred()
  await controller.open(browse())
  api.getCourseWorkspaceDetail = () => late.promise
  const pending = controller.selectNode('old')
  await controller.open(browse('new'))
  late.resolve({ course_id: 'c', graph_digest: 'a'.repeat(64), node: node('old'), resolved_id: 'old' }); await pending
  assert.equal(controller.state.detail, null)
  api.getCourseWorkspaceDetail = async () => ({ course_id: 'new', graph_digest: 'b'.repeat(64), node: node('changed'), resolved_id: 'changed' })
  await controller.selectNode('changed')
  assert.equal(controller.state.detail, null)
  assert.equal(controller.state.stale, true)
})
