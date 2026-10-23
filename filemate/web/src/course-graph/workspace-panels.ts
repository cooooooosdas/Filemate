export type WorkspacePanel = 'none' | 'manager' | 'directory' | 'detail' | 'source' | 'learning'
interface PanelState { active: WorkspacePanel; managerMounted: boolean; managerEpoch: number }
export function createWorkspacePanels(canLeave: () => Promise<boolean>, focus: (id: string) => void = () => {}, observe: (s: PanelState) => PanelState = s => s) {
  const state = observe({ active: 'none', managerMounted: false, managerEpoch: 0 })
  let trigger = '', generation = 0
  async function open(panel: WorkspacePanel, opener = '') {
    const current = ++generation
    if ((state.active === 'manager' || state.active === 'learning') && panel !== state.active && !await canLeave()) return false
    if (current !== generation) return false
    trigger = opener; state.active = panel
    if (panel === 'manager') state.managerMounted = true
    return true
  }
  async function close(panel: WorkspacePanel) {
    if (state.active !== panel) return false
    const current = ++generation
    if ((panel === 'manager' || panel === 'learning') && !await canLeave()) return false
    if (current !== generation) return false
    state.active = 'none'; focus(trigger); return true
  }
  function invalidate() { ++generation; state.active = 'none'; state.managerMounted = false; state.managerEpoch++ }
  return { state, open, close, invalidate }
}
export function createCommitNotifier(changed: (courseId: string) => unknown) {
  const receipts = new Set<string>()
  return async (courseId: string, receipt: string) => {
    const key = `${courseId}:${receipt}`
    if (receipts.has(key)) return
    receipts.add(key)
    if (receipts.size > 200) receipts.delete(receipts.values().next().value!)
    await changed(courseId)
  }
}

export function nextPanelFocus(index: number, length: number, backwards: boolean): number {
  if (!length) return -1
  return index < 0 ? (backwards ? length-1 : 0) : (index + (backwards ? -1 : 1) + length) % length
}
