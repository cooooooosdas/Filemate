import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

const css = fs.readFileSync(new URL('../src/style.css', import.meta.url), 'utf8')
const tokens = Object.fromEntries([...css.matchAll(/--([\w-]+):\s*(#[\da-f]{6}|var\(--[\w-]+\))/gi)].map(m => [m[1], m[2]]))
function color(name) {
  const value = tokens[name]
  assert.ok(value, `Missing color token: ${name}`)
  return value.startsWith('var(') ? color(value.slice(6, -1)) : value
}
function luminance(hex) {
  const channels = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map(c => c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722
}
function contrast(a, b) {
  const x = luminance(a), y = luminance(b)
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05)
}
test('shared small-text colors reach AA on all supported light surfaces', () => {
  for (const foreground of ['text-primary', 'text-secondary', 'text-muted', 'accent', 'success', 'warning', 'danger']) {
    for (const background of ['bg-base', 'bg-surface', 'bg-elevated', 'accent-soft']) {
      const ratio = contrast(color(foreground), color(background))
      assert.ok(ratio >= 4.5, `${foreground} on ${background}: ${ratio.toFixed(2)} < 4.5`)
    }
  }
})
test('component placeholder and status colors inherit accessible tokens', () => {
  for (const [component, semantic] of [['el-text-color-placeholder', 'text-muted'], ['el-color-primary', 'accent'], ['el-color-success', 'success'], ['el-color-warning', 'warning'], ['el-color-danger', 'danger'], ['el-color-info', 'text-muted']]) {
    assert.equal(color(component), color(semantic), component)
  }
})
test('solid component buttons keep readable white labels when hovered', () => {
  for (const token of ['accent', 'accent-hover', 'el-color-primary-light-3', 'el-color-success-light-3', 'el-color-warning-light-3', 'el-color-danger-light-3', 'el-color-info-light-3']) {
    assert.ok(contrast('#ffffff', color(token)) >= 4.5, token)
  }
})
