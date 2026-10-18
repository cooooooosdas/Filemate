import assert from 'node:assert/strict'
import test from 'node:test'

const theme = await import('../src/preferences/themes.ts').catch(() => ({}))
const files = await import('../src/preferences/file-save.ts').catch(() => ({}))

test('automatic appearance reacts to the system, while a manual choice survives system changes and reload', () => {
  assert.equal(typeof theme.createThemeController, 'function', 'appearance control must exist')
  let stored = 'system', dark = false, listener, rendered
  const storage = { getItem: () => stored, setItem: (_, value) => { stored = value } }
  const media = { get matches() { return dark }, addEventListener: (_, fn) => { listener = fn }, removeEventListener: () => { listener = undefined } }
  const control = theme.createThemeController(storage, media, value => { rendered = value })
  assert.equal(rendered.id, 'blue-gray')
  dark = true; listener()
  assert.equal(rendered.id, 'midnight')
  assert.equal(control.select('mist'), true)
  assert.equal(rendered.id, 'mist')
  dark = false; listener(); dark = true; listener()
  assert.equal(rendered.id, 'mist')
  assert.equal(stored, 'mist')
  control.dispose()
  assert.equal(listener, undefined)
  theme.createThemeController(storage, media, value => { rendered = value }).dispose()
  assert.equal(rendered.id, 'mist')
})

test('invalid preferences and unavailable browser storage cannot break the page', () => {
  assert.equal(typeof theme.createThemeController, 'function')
  let rendered
  const control = theme.createThemeController({ getItem() { throw Error('blocked') }, setItem() { throw Error('blocked') } }, { matches: false, addEventListener() {}, removeEventListener() {} }, value => { rendered = value })
  assert.equal(rendered.id, 'blue-gray')
  assert.equal(control.select('midnight'), false)
  assert.equal(rendered.id, 'midnight')
  control.select('unknown')
  assert.equal(rendered.id, 'blue-gray')
  control.dispose()
})

const luminance = hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4).reduce((v, x, i) => v + x * [.2126, .7152, .0722][i], 0)
const ratio = (a, b) => (Math.max(luminance(a), luminance(b)) + .05) / (Math.min(luminance(a), luminance(b)) + .05)
test('every theme keeps body, secondary text and links readable on its workspace and reading surfaces', () => {
  assert.ok(theme.themes?.length >= 4)
  for (const choice of theme.themes) {
    for (const ink of ['text-primary', 'text-secondary', 'text-muted', 'accent', 'success', 'warning', 'danger']) {
      for (const surface of ['bg-base', 'bg-surface', 'bg-elevated', 'accent-soft']) {
        assert.ok(ratio(choice.colors[ink], choice.colors[surface]) >= 4.5, `${choice.id}: ${ink} on ${surface}`)
      }
    }
    assert.ok(ratio('#ffffff', choice.colors['action-fill']) >= 4.5, choice.id)
  }
})

test('saving waits for the native picker and cancellation never opens a writable file', async () => {
  assert.equal(typeof files.writePickedFile, 'function')
  let opened = false
  assert.equal(await files.writePickedFile(new Blob(['evidence']), 'report.json', async () => { throw new DOMException('cancelled', 'AbortError') }), false)
  const handle = { async createWritable() { opened = true; return { async write() {}, async close() {} } } }
  const pending = files.writePickedFile(new Blob(['evidence']), 'report.json', async () => { assert.equal(opened, false); return handle })
  assert.equal(await pending, true)
  assert.equal(opened, true)
})

test('failed file writes abort the temporary stream and report failure instead of success', async () => {
  assert.equal(typeof files.writePickedFile, 'function')
  const events = []
  const blob = new Blob(['original report'])
  await assert.rejects(files.writePickedFile(blob, 'report.json', async name => {
    assert.equal(name, 'report.json')
    return { async createWritable() { return { async write(data) { assert.equal(await data.text(), 'original report'); events.push('write'); throw Error('disk full') }, async close() { events.push('close') }, async abort() { events.push('abort') } } } }
  }), /disk full/)
  assert.deepEqual(events, ['write', 'abort'])
})

test('export names cannot traverse directories and filenames retain their useful extension', () => {
  assert.equal(typeof files.safeDownloadName, 'function')
  assert.equal(files.safeDownloadName('../课程/题目?.json'), '.._课程_题目_.json')
  assert.equal(files.safeDownloadName(''), 'FileMate-export.txt')
  assert.ok(files.safeDownloadName('题'.repeat(300) + '.json').endsWith('.json'))
  assert.ok(files.safeDownloadName('题'.repeat(300) + '.json').length <= 180)
})
