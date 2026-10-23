import type { CourseBrowse, WorkspaceApi, WorkspaceCanvas, WorkspaceChapterPath, WorkspaceCitation, WorkspaceConceptPage, WorkspaceDetail, WorkspaceFilter, WorkspaceNavigation, WorkspaceNode, WorkspaceView } from '../types/courseWorkspace.ts'

export interface WorkspaceState {
  browse: CourseBrowse; navigation: WorkspaceNavigation | null; canvas: WorkspaceCanvas | null
  detail: WorkspaceDetail | null; citation: WorkspaceCitation | null; listPage: WorkspaceConceptPage | null
  chapterPath: WorkspaceChapterPath | null
  searchPage: WorkspaceConceptPage | null; loading: boolean; searching: boolean; citationLoading: boolean
  error: string; errorCode: string; stale: boolean; notice: string; generation: number; identity: string | null
}
const emptyBrowse = (): CourseBrowse => ({ scope: 'course', courseId: '', view: 'graph', nodeId: '', chapterId: '', sourceId: '', relations: null, notice: '' })
const filterOf = (b: CourseBrowse): WorkspaceFilter => ({ chapter_id: b.chapterId || undefined, source_id: b.sourceId || undefined, relations: b.relations })
const codeOf = (error: unknown) => (error as { code?: string })?.code ?? ''

export function createCourseWorkspaceController(api: WorkspaceApi, observe: (state: WorkspaceState) => WorkspaceState = s => s) {
  const state = observe({ browse: emptyBrowse(), navigation: null, canvas: null, detail: null, citation: null,
    listPage: null, chapterPath: null, searchPage: null, loading: false, searching: false, citationLoading: false,
    error: '', errorCode: '', stale: false, notice: '', generation: 0, identity: null })
  let disposed = false, mainAbort: AbortController | null = null, searchAbort: AbortController | null = null
  let citationAbort: AbortController | null = null, searchId = 0, citationId = 0
  let timer: ReturnType<typeof setTimeout> | null = null, resolveTimer: (() => void) | null = null
  let listOffset = 0, groupOffset = 0, refOffset = 0, navOffset = 0, sourceOffset = 0
  let searchQuery = '', searchOffset = 0, canvasFocus = ''
  const current = (generation: number) => !disposed && state.generation === generation
  function clearTimer() { if (timer !== null) clearTimeout(timer); timer = null; resolveTimer?.(); resolveTimer = null }
  function closeCitation() { citationAbort?.abort(); ++citationId; state.citation = null; state.citationLoading = false }
  function stopReads() {
    mainAbort?.abort(); searchAbort?.abort(); ++searchId; clearTimer(); closeCitation(); state.searching = false
  }
  function clearSnapshot() { state.navigation = null; state.canvas = null; state.detail = null; state.listPage = null; state.searchPage = null; state.chapterPath = null }
  const filterKey = (b: CourseBrowse) => JSON.stringify([b.chapterId, b.sourceId, b.relations === null ? null : [...b.relations].sort()])
  const pageOffset = (offset: number, total: number, limit: number) => Number.isFinite(total) && limit > 0 && offset > 0 && offset >= total ? Math.max(0, Math.floor((total-1)/limit)*limit) : offset

  async function open(browse: CourseBrowse, options?: { focusId: string }) {
    if (disposed) return
    const sameCourse = state.browse.courseId === browse.courseId
    const sameNode = state.browse.nodeId === browse.nodeId
    const sameFilters = filterKey(state.browse) === filterKey(browse)
    stopReads()
    const generation = ++state.generation
    mainAbort = new AbortController()
    const signal = mainAbort.signal
    state.browse = { ...browse, relations: browse.relations ? [...browse.relations] : browse.relations }
    state.error = ''; state.errorCode = ''; state.notice = browse.notice; state.loading = !!browse.courseId
    if (!sameCourse) { clearSnapshot(); listOffset = 0; groupOffset = 0; refOffset = 0; navOffset = 0; sourceOffset = 0 }
    else if (!sameNode) { state.detail = null; refOffset = 0 }
    if (!sameFilters) { listOffset = 0; groupOffset = 0; navOffset = 0; state.searchPage = null; state.chapterPath = null }
    canvasFocus = options?.focusId ?? browse.nodeId
    if (!browse.courseId) { clearSnapshot(); state.loading = false; state.stale = false; return }
    let digestRetries = 0, pageRetries = 0, nodeRetries = 0
    for (let attempt = 0; attempt < 4; attempt++) {
      try {
        const b = state.browse, cid = b.courseId
        const realChapter = b.chapterId && !b.chapterId.startsWith('@') ? b.chapterId : ''
        const [navigation, canvas, listPage, detail, chapterPath] = await Promise.all([
          api.getCourseWorkspace(cid, { parent_id: realChapter || '@root', group_offset: navOffset, source_offset: sourceOffset }, signal),
          api.getCourseCanvas(cid, filterOf(b), canvasFocus || undefined, groupOffset, signal),
          api.getCourseConceptPage(cid, { ...filterOf(b), offset: listOffset }, signal),
          b.nodeId ? api.getCourseWorkspaceDetail(cid, b.nodeId, refOffset, signal) : Promise.resolve(null),
          realChapter ? api.getCourseChapterPath(cid, realChapter, signal) : Promise.resolve(null),
        ])
        if (!current(generation)) return
        const bundle = [navigation, canvas, listPage, ...(detail ? [detail] : []), ...(chapterPath ? [chapterPath] : [])]
        if (bundle.some(part => part.course_id !== cid || part.graph_digest !== navigation.graph_digest)) {
          if (digestRetries++ === 0) continue
          state.stale = true; state.error = '课程内容正在变化，请稍后刷新。'; state.errorCode = 'snapshot_changed'; break
        }
        const offsets = [pageOffset(listOffset, listPage.total, listPage.limit), pageOffset(groupOffset, canvas.group_total, canvas.group_limit),
          pageOffset(navOffset, navigation.group_total, navigation.group_limit), pageOffset(sourceOffset, navigation.source_total, navigation.source_limit),
          detail ? pageOffset(refOffset, detail.total_refs, detail.limit) : 0]
        if (offsets.some((offset, index) => offset !== [listOffset, groupOffset, navOffset, sourceOffset, refOffset][index])) {
          if (pageRetries++ === 0) { [listOffset, groupOffset, navOffset, sourceOffset, refOffset] = offsets as [number, number, number, number, number]; continue }
          state.stale = true; state.error = '分页内容正在变化，请刷新后重试。'; state.errorCode = 'snapshot_changed'; break
        }
        if (state.searchPage && state.searchPage.graph_digest !== navigation.graph_digest) {
          state.searchPage = null; searchOffset = 0; state.notice = '课程内容已更新，请重新搜索。'
        }
        state.navigation = navigation; state.canvas = canvas; state.listPage = listPage; state.detail = detail
        state.chapterPath = chapterPath
        state.stale = false; state.loading = false; return
      } catch (cause) {
        if (!current(generation)) return
        const code = codeOf(cause)
        if (code === 'concept_not_found' && (state.browse.nodeId || canvasFocus) && nodeRetries++ === 0) {
          state.browse = { ...state.browse, nodeId: '' }; state.detail = null
          canvasFocus = ''; refOffset = 0
          state.notice = '该概念当前不可用，已返回课程概览。'; continue
        }
        state.error = cause instanceof Error ? cause.message : '课程读取失败，请重试。'
        state.errorCode = code
        state.stale = true
        if (code === 'course_not_found') clearSnapshot()
        break
      }
    }
    if (current(generation)) state.loading = false
  }

  async function selectNode(id: string) {
    if (disposed || !state.navigation) return
    stopReads(); const generation = ++state.generation
    mainAbort = new AbortController(); refOffset = 0
    state.browse = { ...state.browse, nodeId: id, notice: '' }; state.detail = null
    state.loading = true; state.error = ''; state.errorCode = ''; state.notice = ''
    try {
      const detail = await api.getCourseWorkspaceDetail(state.browse.courseId, id, 0, mainAbort.signal)
      if (!current(generation)) return
      if (detail.course_id !== state.browse.courseId || detail.graph_digest !== state.navigation?.graph_digest) {
        state.stale = true; state.notice = '课程内容已变化，请刷新后查看详情。'
      } else state.detail = detail
    } catch (cause) {
      if (!current(generation)) return
      if (codeOf(cause) === 'concept_not_found') {
        state.browse = { ...state.browse, nodeId: '' }; state.notice = '该概念当前不可用，请刷新课程。'
      } else state.error = cause instanceof Error ? cause.message : '详情读取失败，请重试。'
      state.stale = true
    } finally { if (current(generation)) state.loading = false }
  }
  async function expandNode(id: string) { await open({ ...state.browse, nodeId: id, notice: '' }, { focusId: id }) }
  async function refresh() { await open({ ...state.browse, notice: '' }, { focusId: canvasFocus }) }
  async function setFilters(filters: WorkspaceFilter) {
    listOffset = 0; groupOffset = 0
    await open({ ...state.browse, chapterId: filters.chapter_id || '', sourceId: filters.source_id || '',
      relations: filters.relations ?? null, nodeId: '', notice: '' })
  }
  function setView(view: WorkspaceView) { state.browse = { ...state.browse, view } }

  async function runSearch(q: string, id: number) {
    if (disposed || id !== searchId || !state.browse.courseId) return
    searchAbort?.abort(); searchAbort = new AbortController()
    const generation = state.generation, cid = state.browse.courseId
    state.searching = true
    try {
      let page = await api.getCourseConceptPage(cid, { q, offset: searchOffset, relations: state.browse.relations }, searchAbort.signal)
      if (!current(generation) || id !== searchId) return
      const offset = pageOffset(searchOffset, page.total, page.limit)
      if (offset !== searchOffset) {
        searchOffset = offset
        page = await api.getCourseConceptPage(cid, { q, offset, relations: state.browse.relations }, searchAbort.signal)
      }
      if (!current(generation) || id !== searchId) return
      if (page.course_id !== cid || page.graph_digest !== state.navigation?.graph_digest) {
        state.searchPage = null; state.notice = '课程内容已变化，请刷新后搜索。'; state.stale = true
      } else state.searchPage = page
    } catch (cause) {
      if (current(generation) && id === searchId) { state.searchPage = null; state.error = '搜索暂不可用，请重试。' }
    } finally { if (current(generation) && id === searchId) state.searching = false }
  }
  function search(q: string, immediate = false): Promise<void> {
    clearTimer(); searchAbort?.abort()
    const id = ++searchId
    searchQuery = q; searchOffset = 0; state.searchPage = null
    if (!q.trim()) { state.searchPage = null; state.searching = false; return Promise.resolve() }
    if (q.length > 160) { state.error = '搜索内容最多160字符。'; return Promise.resolve() }
    if (immediate) return runSearch(q, id)
    return new Promise(resolve => {
      resolveTimer = resolve
      timer = setTimeout(() => { timer = null; resolveTimer = null; void runSearch(q, id).finally(resolve) }, 300)
    })
  }

  async function selectSearchResult(item: WorkspaceNode) {
    const generation = state.generation, original = state.browse
    let chapterId = original.chapterId, sourceId = original.sourceId
    try {
      for (const [name, value] of [['chapter_id', chapterId], ['source_id', sourceId]] as const) {
        if (!value) continue
        try { await api.getCourseCanvas(original.courseId, { [name]: value, relations: original.relations }, item.id, 0, mainAbort?.signal) }
        catch (cause) {
          if (codeOf(cause) !== 'focus_outside_filter') throw cause
          if (name === 'chapter_id') chapterId = ''; else sourceId = ''
        }
      }
      if (!current(generation)) return
      await open({ ...original, chapterId, sourceId, nodeId: item.id,
        notice: chapterId !== original.chapterId || sourceId !== original.sourceId ? '已清除不匹配的范围条件，定位到搜索结果。' : '' })
    } catch { if (current(generation)) state.error = '结果已变化，请刷新后重新定位。' }
  }

  async function openCitation(eid: string) {
    if (disposed || !state.detail) return
    closeCitation()
    const generation = state.generation, id = citationId, detail = state.detail, cid = state.browse.courseId
    citationAbort = new AbortController(); state.citationLoading = true
    try {
      const result = await api.getCourseCitation(cid, detail.requested_id, eid, citationAbort.signal)
      if (!current(generation) || id !== citationId) return
      if (result.course_id !== cid || result.graph_digest !== detail.graph_digest) {
        state.stale = true; state.notice = '原文或课程内容已变化，请刷新后重新查看。'
      } else state.citation = result
    } catch {
      if (current(generation) && id === citationId) state.error = '原文当前不可用，可能已更新或移出课程。请刷新核对。'
    } finally { if (current(generation) && id === citationId) state.citationLoading = false }
  }

  async function invalidateAfterMutation() {
    stopReads(); clearSnapshot()
    await open({ ...state.browse, notice: '' })
    state.notice = state.error ? '已保存，刷新失败，请重试读取。' : '已保存，工作台已更新。'
  }
  function resetIdentity(scope: string | null) {
    stopReads(); ++state.generation; clearSnapshot(); state.identity = scope
    state.browse = emptyBrowse(); state.error = ''; state.errorCode = ''; state.notice = ''; state.stale = false; state.loading = false
    searchQuery = ''; searchOffset = 0; canvasFocus = ''
  }
  function dispose() { stopReads(); ++state.generation; disposed = true; state.loading = false }
  return { state, open, selectNode, expandNode, refresh, setFilters, setView, search, selectSearchResult, openCitation, closeCitation,
    invalidateAfterMutation, resetIdentity, dispose,
    async pageSearch(offset: number) { if (disposed || !searchQuery.trim()) return; clearTimer(); searchAbort?.abort(); searchOffset = offset; await runSearch(searchQuery, ++searchId) },
    async page(offset: number) { listOffset = offset; await refresh() },
    async pageGroups(offset: number) { groupOffset = offset; await refresh() },
    async pageReferences(offset: number) { refOffset = offset; await refresh() },
    async pageNavigation(groups: number, sources: number) { navOffset = groups; sourceOffset = sources; await refresh() },
  }
}
