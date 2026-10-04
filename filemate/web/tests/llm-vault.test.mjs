import assert from 'node:assert/strict'
import test from 'node:test'
import { browserVaultAvailable, isModelRequest, validateApiKey } from '../src/services/llm-vault.ts'

test('keys reject whitespace and invalid header characters without echoing their value', () => {
  assert.equal(validateApiKey('  sk-synthetic-only  '), 'sk-synthetic-only')
  for (const key of ['short', 'sk synthetic-only', 'sk-中文-secret', 'x'.repeat(513)]) {
    assert.throws(() => validateApiKey(key), /密钥格式无效/)
  }
  assert.equal(browserVaultAvailable(), false)
})

test('model credential attaches only to the complete generation route set', () => {
  for (const path of ['/api/llm/test', '/process', '/ai/summarize', '/ai/knowledge-cards', '/ai/questions', '/ai/notes', '/ai/study-plan', '/ai/chat', '/knowledge/sources/source/artifacts', '/api/knowledge-graph/drafts', '/interviews', '/interviews/session/answers', '/interviews/session/turns/turn/analyze', '/api/programming/submissions/submission/review']) {
    assert.equal(isModelRequest('post', path), true, path)
    assert.equal(isModelRequest('get', path), false, path)
  }
  for (const path of ['/api/auth/login', '/api/auth/register', '/api/health', '/settings/llm', '/knowledge/import', 'https://attacker.example/ai/chat', '/ai/chat?token=any', '/api/programming/submissions/submission/run']) {
    assert.equal(isModelRequest('post', path), false, path)
  }
})
