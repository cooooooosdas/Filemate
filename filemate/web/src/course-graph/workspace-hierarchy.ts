import type { WorkspaceConceptPage, WorkspaceNode } from '../types/courseWorkspace.ts'

export interface OutlineChapter { id: string; title: string; incomplete: boolean; nodes: WorkspaceNode[] }

export function groupWorkspaceOutline(page: WorkspaceConceptPage | null): OutlineChapter[] {
  if (!page) return []
  const chapters = new Map((page.chapter_groups ?? []).map(g => [g.id, g]))
  const sections = new Map<string, OutlineChapter>()
  for (const node of page.items) {
    for (const id of new Set(node.chapter_ids)) {
      let section = sections.get(id)
      if (!section) {
        const titles: string[] = [], visited = new Set<string>()
        let current: string | null = id, incomplete = false
        while (current) {
          const chapter = chapters.get(current)
          if (!chapter || visited.has(current)) { incomplete = true; break }
          visited.add(current); titles.unshift(chapter.title); current = chapter.parent_id
        }
        if (incomplete) titles.unshift(titles.length ? '上级章节未加载' : '章节信息未加载')
        section = { id, title: titles.join(' / '), incomplete, nodes: [] }
        sections.set(id, section)
      }
      section.nodes.push(node)
    }
  }
  return [...sections.values()]
}
