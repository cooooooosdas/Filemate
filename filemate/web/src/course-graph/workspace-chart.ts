import type { EChartsType } from 'echarts/core'

export function applyWorkspaceSelection(chart: EChartsType, ids: string[], selected: string) {
  chart.dispatchAction({ type: 'downplay', seriesIndex: 0 })
  chart.dispatchAction({ type: 'unselect', seriesIndex: 0, dataIndex: ids.map((_, index) => index) })
  const dataIndex = ids.indexOf(selected)
  if (dataIndex >= 0) {
    chart.dispatchAction({ type: 'select', seriesIndex: 0, dataIndex })
    chart.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex })
  }
}

export function createWorkspaceClickActions(select: (id: string) => void, expand: (id: string) => void) {
  let timer: ReturnType<typeof setTimeout> | undefined
  const cancel = () => { clearTimeout(timer); timer = undefined }
  return {
    click(id: string) { cancel(); timer = setTimeout(() => { timer = undefined; select(id) }, 260) },
    doubleClick(id: string) { cancel(); expand(id) },
    dispose: cancel,
  }
}
