import assert from 'node:assert/strict'
import test from 'node:test'
import { availableTools, primaryGroups, primaryPath, relatedTools, searchTools } from '../src/navigation/catalog.ts'

const tools = availableTools()

test('every available tool and legacy alias has a reachable primary destination', () => {
  const primaries = primaryGroups(tools).flatMap(group => group.items.map(item => item.path))
  assert.equal(new Set(tools.map(tool => tool.path)).size, tools.length)
  for (const tool of tools) {
    assert.ok(primaries.includes(primaryPath(tool.path, tools)), tool.path)
    for (const alias of tool.aliases || []) assert.equal(primaryPath(alias, tools), tool.primary)
  }
  assert.equal(primaryPath('/naming', tools), '/knowledge')
  assert.equal(primaryPath('/semester', tools), '/today')
  assert.equal(primaryPath('/digital-human', tools), '/ai-tools')
})

test('closed features disappear from search, primary and contextual navigation together', () => {
  const flags = Object.fromEntries(tools.filter(tool => tool.flag).map(tool => [tool.flag, 'false']))
  const filtered = availableTools(flags)
  const paths = filtered.map(tool => tool.path)
  for (const tool of tools.filter(tool => tool.flag)) {
    assert.ok(!paths.includes(tool.path))
    assert.ok(!searchTools(tool.title, filtered).length)
    assert.equal(primaryPath(tool.path, filtered), undefined)
  }
  for (const group of primaryGroups(filtered)) for (const tool of group.items) assert.ok(paths.includes(tool.path))
  assert.ok(relatedTools('/knowledge', undefined, filtered).every(tool => paths.includes(tool.path)))
})

test('keyword search normalizes case and full-width characters and requires every term', () => {
  assert.equal(searchTools(' C＋＋ ', tools)[0].path, '/programming')
  assert.equal(searchTools('API', tools)[0].path, '/trust')
  assert.equal(searchTools('数字人', tools)[0].path, '/digital-human')
  assert.equal(searchTools('间隔重复', tools)[0].path, '/wrongbook')
  assert.equal(searchTools('用户画像', tools)[0].path, '/growth')
  assert.equal(searchTools('面试 回答', tools)[0].path, '/interview')
  assert.deepEqual(searchTools('面试 备份', tools), [])
  assert.equal(searchTools(' ', tools).length, tools.length)
})

test('exact feature title outranks incidental matches and no unavailable feature is fabricated', () => {
  assert.equal(searchTools('题库管理', tools)[0].path, '/interview-bank')
  assert.deepEqual(searchTools('Java', tools), [])
  assert.deepEqual(searchTools('DOCX', tools), [])
})

test('study and archival imports guide toward their own next steps without duplicate upload links', () => {
  assert.deepEqual(relatedTools('/import', 'study', tools).map(tool => tool.path), relatedTools('/ai-tools', undefined, tools).map(tool => tool.path))
  const archive = relatedTools('/import', 'archive', tools).map(tool => tool.path)
  assert.ok(archive.includes('/classification') && archive.includes('/history'))
  assert.ok(!archive.includes('/import') && !archive.includes('/ai-tools'))
  assert.deepEqual(relatedTools('/naming', undefined, tools).map(tool => tool.path), archive)
  assert.ok(relatedTools('/semester', undefined, tools).some(tool => tool.path === '/goals'))
})
