import type { WorkspaceCanvas, WorkspaceNode } from '../types/courseWorkspace.ts'

export type PositionedWorkspaceNode = WorkspaceNode & { x: number; y: number }
export const workspaceGraphViewport = { left: 70, right: 70, top: 60, bottom: 60, preserveAspect: 'contain' as const }
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
  const groups = new Map<number, WorkspaceNode[]>()
  for (const n of nodes) { const rank = cycle ? 0 : level.get(n.id)!; groups.set(rank, [...(groups.get(rank) || []), n]) }
  const positioned: PositionedWorkspaceNode[] = []
  let base = 120
  for (const rank of [...groups.keys()].sort((a, b) => a-b)) {
    const members = groups.get(rank)!, columns = Math.ceil(Math.sqrt(members.length))
    members.forEach((n, index) => positioned.push({ ...n, x: base + index % columns*180, y: 80 + Math.floor(index/columns)*110 }))
    base += columns*180 + 60
  }
  return { nodes: positioned, edges, error: cycle ? '依赖关系存在环，已用网格保留全部节点，请核对关系。' : data.nodes.length > 100 ? '画布仅显示100个概念，请使用列表继续查看。' : '' }
}
