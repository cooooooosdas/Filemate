const DB_NAME = 'filemate-model-vault'
const STORE = 'credentials'

interface EncryptedCredential {
  scope: string
  key: CryptoKey
  iv: Uint8Array<ArrayBuffer>
  ciphertext: ArrayBuffer
}

export function browserVaultAvailable(): boolean {
  return globalThis.isSecureContext === true && Boolean(globalThis.crypto?.subtle && globalThis.indexedDB)
}

export function validateApiKey(value: string): string {
  const key = value.trim()
  if (!/^[\x21-\x7e]{10,512}$/.test(key)) throw new Error('API 密钥格式无效，请只粘贴密钥正文')
  return key
}

async function database(): Promise<IDBDatabase> {
  if (!browserVaultAvailable()) throw new Error('当前浏览器不支持安全保存，请使用 HTTPS 和正常浏览窗口')
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1)
    request.onupgradeneeded = () => request.result.createObjectStore(STORE, { keyPath: 'scope' })
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(new Error('本机密钥存储无法打开，请检查浏览器存储权限'))
    request.onblocked = () => reject(new Error('请关闭其他旧版 FileMate 标签页后重试'))
  })
}

async function read(scope: string): Promise<EncryptedCredential | undefined> {
  const db = await database()
  try {
    return await new Promise((resolve, reject) => {
      const request = db.transaction(STORE, 'readonly').objectStore(STORE).get(scope)
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(new Error('本机密钥读取失败，请重新保存'))
    })
  } finally { db.close() }
}

async function write(scope: string, record?: EncryptedCredential): Promise<void> {
  const db = await database()
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite')
      const store = tx.objectStore(STORE)
      if (record) store.put(record)
      else store.delete(scope)
      tx.oncomplete = () => resolve()
      tx.onabort = tx.onerror = () => reject(new Error('本机密钥保存失败，原配置保留，请检查浏览器存储权限'))
    })
  } finally { db.close() }
}

export async function hasBrowserApiKey(scope: string): Promise<boolean> {
  return Boolean(await read(scope))
}

export async function saveBrowserApiKey(scope: string, value: string): Promise<void> {
  const plaintext = validateApiKey(value)
  const key = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt'])
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv, additionalData: new TextEncoder().encode(scope) }, key, new TextEncoder().encode(plaintext))
  await write(scope, { scope, key, iv, ciphertext })
}

export async function getBrowserApiKey(scope: string): Promise<string> {
  const record = await read(scope)
  if (!record) return ''
  try {
    if (record.scope !== scope || record.key.extractable || record.key.algorithm.name !== 'AES-GCM') throw new Error('invalid record')
    const plaintext = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: record.iv, additionalData: new TextEncoder().encode(scope) }, record.key, record.ciphertext)
    return validateApiKey(new TextDecoder().decode(plaintext))
  } catch { throw new Error('本机密钥无法解密，请移除后重新保存') }
}

export async function removeBrowserApiKey(scope: string): Promise<void> {
  await write(scope)
}

export function isModelRequest(method: string | undefined, path: string | undefined): boolean {
  return method?.toUpperCase() === 'POST' && /^(?:\/api\/llm\/test|\/api\/resume\/generate|\/process|\/ai\/(?:summarize|knowledge-cards|questions|notes|study-plan|chat)|\/knowledge\/sources\/[^/]+\/artifacts|\/api\/knowledge-graph\/drafts|\/interviews|\/interviews\/[^/]+\/answers|\/interviews\/[^/]+\/turns\/[^/]+\/analyze|\/api\/programming\/submissions\/[^/]+\/review)$/.test(path || '')
}
