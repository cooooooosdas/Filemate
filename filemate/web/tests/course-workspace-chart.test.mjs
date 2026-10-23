import assert from 'node:assert/strict'
import test from 'node:test'
import { init, use } from 'echarts/core'
import { GraphChart } from 'echarts/charts'
import { SVGRenderer } from 'echarts/renderers'
import { applyWorkspaceSelection, createWorkspaceClickActions } from '../src/course-graph/workspace-chart.ts'

test('real_engine_selection_preserves_zoom_center_and_dragged_coordinates', () => {
  use([GraphChart, SVGRenderer])
  const chart = init(null, null, { renderer: 'svg', ssr: true, width: 700, height: 480 })
  try {
    chart.setOption({ animation: false, series: [{ type: 'graph', layout: 'none', roam: true, selectedMode: 'single',
      zoom: 1.8, center: [35, 42], data: [{ id: 'a', x: 31, y: 21 }, { id: 'b', x: 410, y: 70 }], links: [] }] })
    const before = chart.getOption().series[0]
    const data = chart.getModel().getSeriesByIndex(0).getData()
    data.setItemLayout(1, [512, 125]) // the layout update made by an actual graph drag
    applyWorkspaceSelection(chart, ['a', 'b'], 'b')
    const after = chart.getOption().series[0]
    assert.equal(after.zoom, before.zoom)
    assert.deepEqual(after.center, before.center)
    assert.deepEqual(after.data.map(n => [n.x, n.y]), before.data.map(n => [n.x, n.y]))
    assert.equal(after.selectedMap.b, true)
    assert.deepEqual(chart.getModel().getSeriesByIndex(0).getData().getItemLayout(1), [512, 125])
    assert.equal(after.data.length, 2)
  } finally { chart.dispose() }
})

test('double_click_cancels_pending_selection_and_dispose_cancels_timers', t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const calls = [], actions = createWorkspaceClickActions(id => calls.push(['select', id]), id => calls.push(['expand', id]))
  actions.click('a'); actions.click('a'); actions.doubleClick('a'); t.mock.timers.tick(500)
  assert.deepEqual(calls, [['expand', 'a']])
  actions.click('b'); t.mock.timers.tick(500)
  assert.deepEqual(calls.at(-1), ['select', 'b'])
  actions.click('c'); actions.dispose(); t.mock.timers.tick(500)
  assert.equal(calls.length, 2)
})
