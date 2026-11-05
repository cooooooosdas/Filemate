import assert from 'node:assert/strict'
import { readFileSync, statSync } from 'node:fs'
import { gzipSync } from 'node:zlib'
import test from 'node:test'

const asset = name => new URL(`../src/assets/optimized/${name}`, import.meta.url)
const source = path => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')

function webpSize(name) {
  const bytes = readFileSync(asset(name))
  assert.equal(bytes.toString('ascii', 0, 4), 'RIFF')
  assert.equal(bytes.toString('ascii', 8, 12), 'WEBP')
  if (bytes.toString('ascii', 12, 16) === 'VP8X') {
    return [bytes.readUIntLE(24, 3) + 1, bytes.readUIntLE(27, 3) + 1]
  }
  assert.equal(bytes.toString('ascii', 12, 16), 'VP8 ')
  return [bytes.readUInt16LE(26) & 0x3fff, bytes.readUInt16LE(28) & 0x3fff]
}

test('brand lockup uses actual vector paths with the original aspect ratio', () => {
  const svg = readFileSync(asset('filemate-brand-lockup.svg'), 'utf8')
  assert.match(svg, /viewBox="0 0 1867 526"/)
  assert.match(svg, /<path /)
  assert.doesNotMatch(svg, /<image\b|data:image|<script\b|<foreignObject\b/)
  assert.ok(gzipSync(svg).length <= 25 * 1024)
  const logo = source('components/Logo.vue')
  assert.match(logo, /optimized\/filemate-brand-lockup\.svg/)
  assert.match(logo, /alt="FileMate，你的文件知识管理伙伴"/)
  assert.match(logo, /width="432"/)
  assert.match(logo, /height="122"/)
})

test('home mascot has a correctly sized transparent WebP and PNG fallback', () => {
  assert.deepEqual(webpSize('filemate-mascot-home.webp'), [220, 294])
  assert.ok(statSync(asset('filemate-mascot-home.webp')).size <= 25 * 1024)
  const fallback = readFileSync(asset('filemate-mascot-home.png'))
  assert.deepEqual([fallback.readUInt32BE(16), fallback.readUInt32BE(20)], [220, 294])
  const home = source('views/Home.vue')
  assert.match(home, /<picture[\s>]/)
  assert.match(home, /type="image\/webp"/)
  assert.match(home, /width="220" height="294"/)
})

test('localized avatar resources are bounded and keep sprite coordinates', () => {
  assert.deepEqual(webpSize('filemate-mascot-tutor.webp'), [560, 746])
  assert.deepEqual(webpSize('filemate-mascot-expressions.webp'), [1040, 780])
  assert.deepEqual(webpSize('filemate-mascot-expressions-tutor.webp'), [1448, 1086])
  assert.ok(statSync(asset('filemate-mascot-expressions.webp')).size < 120 * 1024)
  for (const file of ['digital-human/avatars.ts', 'components/CompanionCard.vue', 'views/Interview.vue']) {
    assert.doesNotMatch(source(file), /assets\/filemate-mascot(?:-expressions)?\.png/)
    assert.match(source(file), /assets\/optimized\//)
  }
  const companion = source('components/CompanionCard.vue')
  assert.match(companion, /width="1040"/)
  assert.match(companion, /height="780"/)
  assert.match(companion, /loading="lazy"/)
  assert.match(companion, /height: auto/)
  const tutor = source('views/DigitalHuman.vue')
  assert.match(tutor, /width="560" height="746"/)
  assert.match(source('digital-human/avatars.ts'), /expressions-tutor\.webp/)
})
