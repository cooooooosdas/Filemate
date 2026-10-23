import type { RelationKind } from '../types/courseGraph'
import type { CourseBrowse, CoursePreference, PreferenceStorage, WorkspaceView } from '../types/courseWorkspace'

export const workspaceRelations: RelationKind[] = ['prerequisite', 'depends_on', 'part_of', 'contains', 'application', 'related_to']
const views: WorkspaceView[] = ['graph', 'outline', 'evidence']
const validId = (v: unknown): v is string => typeof v === 'string' && v.length > 0 && v.length <= 120
const validView = (v: unknown): v is WorkspaceView => views.includes(v as WorkspaceView)

export function initialCourseId(explicit: unknown, recent: string | null): string {
  return validId(explicit) ? explicit : validId(recent) ? recent : ''
}

export function resolveGraphScope(query: Record<string, unknown>, enabled: boolean): 'source' | 'course' {
  if (!enabled) return 'source'
  if ('graph_scope' in query) return query.graph_scope === 'course' ? 'course' : 'source'
  return query.source || query.node ? 'source' : 'course'
}

export function readCourseBrowse(query: Record<string, unknown>, saved: CoursePreference | null, mobile: boolean): CourseBrowse {
  const safeView = mobile ? 'outline' : 'graph'
  let notice = ''
  const invalid = () => { notice = '部分浏览条件已失效，已使用安全默认设置。' }
  const scalar = (key: string) => {
    const v = query[key]
    if (v == null) return ''
    if (!validId(v)) { invalid(); return '' }
    return v
  }
  const allowed = ['graph_scope', 'course', 'view', 'node', 'chapter', 'source_id', 'relation', 'hide_relations', 'source']
  if (Object.keys(query).some(k => !allowed.includes(k))) invalid()
  if (query.graph_scope != null && !['course', 'source'].includes(String(query.graph_scope))) invalid()
  let view = saved?.[mobile ? 'mobile' : 'desktop'] ?? safeView
  if (!validView(view)) view = safeView
  if (query.view != null) {
    if (validView(query.view)) view = query.view
    else { view = safeView; invalid() }
  }
  let relations: RelationKind[] | null = null
  if (query.relation != null) {
    const list = Array.isArray(query.relation) ? query.relation : [query.relation]
    if (list.length > 6 || list.some(r => !workspaceRelations.includes(r as RelationKind)) || new Set(list).size !== list.length) invalid()
    else relations = list as RelationKind[]
  }
  if (query.hide_relations != null) {
    if (query.hide_relations === 'true' && query.relation == null) relations = []
    else if (query.hide_relations !== 'false' || query.relation != null) { relations = null; invalid() }
  }
  const courseId = scalar('course'), nodeId = scalar('node'), chapterId = scalar('chapter'), sourceId = scalar('source_id')
  return { scope: resolveGraphScope(query, true), courseId, view, nodeId, chapterId, sourceId, relations, notice }
}

export function courseBrowseQuery(state: CourseBrowse): Record<string, string | string[]> {
  const query: Record<string, string | string[]> = { graph_scope: state.scope, view: state.view }
  for (const [key, value] of [['course', state.courseId], ['node', state.nodeId], ['chapter', state.chapterId], ['source_id', state.sourceId]]) {
    if (validId(value)) query[key!] = value!
  }
  if (state.relations?.length === 0) query.hide_relations = 'true'
  else if (state.relations) query.relation = state.relations.filter(r => workspaceRelations.includes(r))
  return query
}

export function createCoursePreferences(storage: PreferenceStorage, scope: string | null) {
  const key = scope && /^[a-f0-9]{64}$/.test(scope) ? `filemate-course-workspace-v1:${scope}` : null
  let courses: Record<string, CoursePreference> = Object.create(null), last: string | null = null
  try {
    const raw = key ? storage.getItem(key) : null
    const data = raw ? JSON.parse(raw) : null
    if (data?.courses && typeof data.courses === 'object' && !Array.isArray(data.courses)) {
      for (const [id, item] of Object.entries(data.courses).slice(-100)) {
        if (!validId(id) || !item || typeof item !== 'object') continue
        const value = item as CoursePreference
        const pref: CoursePreference = {}
        if (validView(value.desktop)) pref.desktop = value.desktop
        if (validView(value.mobile)) pref.mobile = value.mobile
        if (Object.keys(pref).length) courses[id] = pref
      }
      if (validId(data.last) && Object.hasOwn(courses, data.last)) last = data.last
    }
  } catch { /* 拒绝本机存储时仍允许页内阅读。 */ }
  const persist = () => {
    if (key) try { storage.setItem(key, JSON.stringify({ courses, last })) } catch { /* 内存偏好保留。 */ }
  }
  return {
    get(courseId: string, _mobile = false): CoursePreference | null {
      return Object.hasOwn(courses, courseId) ? { ...courses[courseId] } : null
    },
    set(courseId: string, mobile: boolean, view: WorkspaceView) {
      if (!validId(courseId) || !validView(view)) return
      const previous = courses[courseId] ?? {}
      delete courses[courseId]
      courses[courseId] = { ...previous, [mobile ? 'mobile' : 'desktop']: view }
      while (Object.keys(courses).length > 100) delete courses[Object.keys(courses)[0]!]
      last = courseId; persist()
    },
    lastCourse: () => last,
    forget(courseId: string) { delete courses[courseId]; if (last === courseId) last = null; persist() },
    clearMemory() { courses = Object.create(null); last = null },
  }
}
