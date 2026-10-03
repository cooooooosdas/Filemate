import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { BUDGET, inspectBundle } from '../scripts/check-bundle.mjs'

function fixture(run) {
  const temporary = path.resolve(process.env.FILEMATE_TEST_TEMP || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../_working'))
  fs.mkdirSync(temporary, { recursive: true })
  const root = fs.mkdtempSync(path.join(temporary, 'filemate-bundle-'))
  try { run(root) } finally {
    assert.ok(root.startsWith(temporary + path.sep))
    fs.rmSync(root, { recursive: true, force: true })
  }
}
test('initial budget counts every static dependency and excludes lazy editor bytes', () => fixture(root => {
  fs.writeFileSync(path.join(root, 'entry.js'), 'entry')
  fs.writeFileSync(path.join(root, 'home.js'), 'home')
  fs.writeFileSync(path.join(root, 'shared.js'), 'shared')
  fs.writeFileSync(path.join(root, 'style.css'), 'css')
  const report = inspectBundle(root, {
    'index.html': { isEntry: true, file: 'entry.js', imports: ['shared'], dynamicImports: ['editor'] },
    'src/views/Home.vue': { file: 'home.js', imports: ['shared'], css: ['style.css'] },
    shared: { file: 'shared.js' }, editor: { file: 'editor.api.js' },
  })
  assert.equal(report.measurements.javascript, 15)
  assert.equal(report.measurements.css, 3)
  assert.equal(report.files.length, 4)
  assert.equal(report.passed, true)
}))
test('splitting an oversized eager dependency cannot bypass the total budget', () => fixture(root => {
  fs.writeFileSync(path.join(root, 'entry.js'), 'e')
  fs.writeFileSync(path.join(root, 'home.js'), 'h')
  fs.writeFileSync(path.join(root, 'shared.js'), 'x'.repeat(BUDGET.javascript))
  const report = inspectBundle(root, {
    'index.html': { isEntry: true, file: 'entry.js', imports: ['shared'] },
    'src/views/Home.vue': { file: 'home.js' }, shared: { file: 'shared.js' },
  })
  assert.deepEqual(report.exceeded, ['javascript'])
  assert.equal(report.passed, false)
}))
test('missing manifest dependency and eager editor loading fail explicitly', () => fixture(root => {
  fs.writeFileSync(path.join(root, 'entry.js'), 'e')
  fs.writeFileSync(path.join(root, 'home.js'), 'h')
  fs.writeFileSync(path.join(root, 'editor.js'), 'editor')
  const manifest = {
    'index.html': { isEntry: true, file: 'entry.js', imports: ['editor.api'] },
    'src/views/Home.vue': { file: 'home.js' },
  }
  assert.throws(() => inspectBundle(root, manifest), /Missing manifest/)
  manifest['editor.api'] = { file: 'editor.js' }
  assert.equal(inspectBundle(root, manifest).passed, false)
}))
