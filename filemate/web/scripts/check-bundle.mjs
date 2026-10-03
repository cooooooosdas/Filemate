import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { gzipSync } from 'node:zlib'

// 总传输依赖比单个入口文件更能反映首页成本，避免仅拆文件来通过预算。
export const BUDGET = Object.freeze({ javascript: 450 * 1024, javascript_gzip: 140 * 1024, css: 150 * 1024 })

export function inspectBundle(dist, manifest) {
  const visited = new Set(), assets = new Set(), modules = new Set()
  function visit(key) {
    if (visited.has(key)) return
    const chunk = manifest[key]
    assert.ok(chunk, `Missing manifest module: ${key}`)
    visited.add(key)
    modules.add(key)
    assets.add(chunk.file)
    for (const css of chunk.css || []) assets.add(css)
    for (const dependency of chunk.imports || []) visit(dependency)
  }
  const entries = Object.entries(manifest).filter(([, row]) => row.isEntry)
  assert.equal(entries.length, 1, 'Expected one application entry')
  visit(entries[0][0])
  assert.ok(manifest['src/views/Home.vue'], 'Missing lazy Home route')
  visit('src/views/Home.vue')
  let javascript = 0, javascript_gzip = 0, css = 0
  const files = []
  for (const name of [...assets].sort()) {
    const absolute = path.resolve(dist, name)
    assert.ok(absolute.startsWith(path.resolve(dist) + path.sep), 'Manifest path escapes dist')
    const bytes = fs.readFileSync(absolute)
    files.push({ path: name, bytes: bytes.length, gzip_bytes: gzipSync(bytes).length })
    if (name.endsWith('.js')) { javascript += bytes.length; javascript_gzip += gzipSync(bytes).length }
    if (name.endsWith('.css')) css += bytes.length
  }
  const eagerHeavyModules = [...modules].filter(key => /monaco|editor\.api|vision\.worker|tasks-vision|echarts/i.test(key))
  const measurements = { javascript, javascript_gzip, css }
  const exceeded = Object.entries(BUDGET).filter(([key, limit]) => measurements[key] > limit).map(([key]) => key)
  return { scope: 'entry plus Home and recursive static imports; gzip estimated, not a network timing',
    measurements, budget: BUDGET, exceeded, eagerHeavyModules, files,
    passed: exceeded.length === 0 && eagerHeavyModules.length === 0 }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2)
  const option = key => args[args.indexOf(key) + 1]
  const dist = path.resolve(args.includes('--dist') ? option('--dist') : 'dist')
  const manifest = JSON.parse(fs.readFileSync(path.join(dist, '.vite/manifest.json'), 'utf8'))
  const report = inspectBundle(dist, manifest)
  const rendered = JSON.stringify(report, null, 2) + '\n'
  if (args.includes('--output')) fs.writeFileSync(option('--output'), rendered, { flag: 'wx' })
  console.log(rendered)
  if (!report.passed && !args.includes('--measure-only')) process.exitCode = 1
}
