import type { WorkspaceCanvas, WorkspaceNode } from '../types/courseWorkspace.ts'

export type PositionedWorkspaceNode = WorkspaceNode & { x: number; y: number }
export const relationLabels: Record<string, string> = {
  prerequisite: '前置知识', depends_on: '依赖', part_of: '属于', contains: '包含', application: '应用于', related_to: '相关',
}

export function layoutWorkspaceCanvas(data: WorkspaceCanvas) {
  const nodes = [...new Map(data.nodes.map(n => [n.id, n])).values()].sort((a, b) => a.id.localeCompare(b.id)).slice(0, 100)
  const ids = new Set(nodes.map(n => n.id)), edges = data.edges.filter(e => ids.has(e.from) && ids.has(e.to))
  const adjacency = new Map(nodes.map(n => [n.id, new Set<string>()])), incoming = new Map(nodes.map(n => [n.id, 0]))
  for (const e of edges) {
    if (!['prerequisite', 'depends_on'].includes(e.relation)) continue
    const [a, b] = e.relation === 'depends_on' ? [e.to, e.from] : [e.from, e.to]
    if (!adjacency.get(a)!.has(b)) { adjacency.get(a)!.add(b); incoming.set(b, incoming.get(b)! + 1) }
  }
  const level = new Map(nodes.map(n => [n.id, 0])), ready = nodes.filter(n => incoming.get(n.id) === 0).map(n => n.id)
  let visited = 0
  while (ready.length) {
    const a = ready.shift()!; visited++
    for (const b of [...adjacency.get(a)!].sort()) {
      level.set(b, Math.max(level.get(b)!, level.get(a)! + 1))
      incoming.set(b, incoming.get(b)! - 1)
      if (incoming.get(b) === 0) { ready.push(b); ready.sort() }
    }
  }
  const cycle = visited !== nodes.length
  const rows = new Map<number, number>()
  const positioned: PositionedWorkspaceNode[] = nodes.map((n, index) => {
    const column = cycle ? index % 5 : level.get(n.id)!
    const row = cycle ? Math.floor(index / 5) : rows.get(column) ?? 0
    rows.set(column, row + 1)
    return { ...n, x: 120 + column * 240, y: 80 + row * 110 }
  })
  return { nodes: positioned, edges, error: cycle ? '依赖关系存在环，已用网格保留全部节点，请核对关系。' : data.nodes.length > 100 ? '画布仅显示100个概念，请使用列表继续查看。' : '' }
}
