import assert from 'node:assert/strict'
import test from 'node:test'
import { newPasswordError } from '../src/auth/password.ts'

test('nine-character passwords accept lowercase or uppercase with digits and optional symbols', () => {
  for (const value of ['Abcd12345', 'abcd12345', 'ABCD12345', 'Abcd1234!', '中文ab12345']) {
    assert.equal(newPasswordError(value), '')
  }
})

test('short, digits-only and letters-only new passwords explain how to correct the field', () => {
  assert.match(newPasswordError('Abcd1234'), /9–128/)
  for (const value of ['123456789', 'abcdefghi', 'abcdefg!@', '中文密码测试123']) {
    assert.match(newPasswordError(value), /字母和数字/)
  }
})

test('length limit counts Unicode code points and preserves the 128-character maximum', () => {
  assert.equal(newPasswordError('a1' + 'x'.repeat(126)), '')
  assert.match(newPasswordError('a1' + 'x'.repeat(127)), /9–128/)
  assert.match(newPasswordError('ab12😀😀😀😀'), /9–128/)
  assert.equal(newPasswordError('ab12😀😀😀😀😀'), '')
})
