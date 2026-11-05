export interface HomeState {
  status: 'loading' | 'error' | 'ready'
  authenticated: boolean | null
  sourceId: string | null
  due: number
}
export function resolveHomeAction(state: HomeState) {
  if (state.status === 'error') return { kind: 'retry', title: '重新读取学习状态', route: '' }
  if (state.status !== 'ready' || state.authenticated === null) return { kind: 'pending', title: '正在读取学习状态…', route: '' }
  if (state.due > 0) return { kind: 'link', title: '复习今天的错题', route: '/wrongbook' }
  if (state.sourceId) return { kind: 'link', title: '继续读上次的资料', route: `/ai-tools?source=${encodeURIComponent(state.sourceId)}` }
  if (!state.authenticated) return { kind: 'sample', title: '用示例资料试一下', route: '' }
  return { kind: 'link', title: '导入第一份资料', route: '/import?intent=study' }
}
export function createSampleImporter<T>(importer: () => Promise<T>): () => Promise<T> {
  let pending: Promise<T> | null = null
  return () => {
    if (!pending) pending = importer().finally(() => { pending = null })
    return pending
  }
}
