import assert from 'node:assert/strict'
import test from 'node:test'
import viteConfig from '../vite.config.ts'

function resolve(command, value) {
  const key = 'VITE_ENABLE_WRONGBOOK_V2', previous = process.env[key]
  if (value === undefined) delete process.env[key]
  else process.env[key] = value
  try {
    return typeof viteConfig === 'function'
      ? viteConfig({ command, mode: 'production', isSsrBuild: false, isPreview: false })
      : viteConfig
  } finally {
    if (previous === undefined) delete process.env[key]
    else process.env[key] = previous
  }
}

test('ordinary production builds retain the released wrongbook 2.0 entry', () => {
  assert.equal(resolve('build').define?.['import.meta.env.VITE_ENABLE_WRONGBOOK_V2'], '"true"')
})
test('explicit legacy build remains available for a controlled rollback', () => {
  assert.equal(resolve('build', 'false').define?.['import.meta.env.VITE_ENABLE_WRONGBOOK_V2'], '"false"')
})
test('explicit v2 and the unchanged development opt-in remain supported', () => {
  assert.equal(resolve('build', 'true').define?.['import.meta.env.VITE_ENABLE_WRONGBOOK_V2'], '"true"')
  assert.equal(resolve('serve').define?.['import.meta.env.VITE_ENABLE_WRONGBOOK_V2'], '"false"')
})
test('invalid release flag fails rather than silently building the legacy page', () => {
  assert.throws(() => resolve('build', 'TRUE'), /VITE_ENABLE_WRONGBOOK_V2/)
})
