import crypto from 'node:crypto'
import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'

const host = '127.0.0.1'
const port = Number.parseInt(process.env.FILEMATE_GATEWAY_PORT || '8080', 10)
const backendUrl = new URL(process.env.FILEMATE_GATEWAY_BACKEND || 'http://127.0.0.1:8010')
const staticRoot = path.resolve(process.env.FILEMATE_WEB_DIST || 'filemate/web/dist')
const username = process.env.FILEMATE_BASIC_USER || ''
const password = process.env.FILEMATE_BASIC_PASSWORD || ''
const maxBodyBytes = 64 * 1024 * 1024

if (!username || !password) {
  throw new Error('FILEMATE_BASIC_USER and FILEMATE_BASIC_PASSWORD are required')
}
if (!fs.existsSync(path.join(staticRoot, 'index.html'))) {
  throw new Error(`Vue production build was not found: ${staticRoot}`)
}

const apiPrefixes = [
  '/process', '/sessions', '/ai', '/knowledge', '/quiz', '/wrongbook',
  '/interview', '/interviews', '/analytics', '/review', '/study-plans',
  '/evaluation', '/goals', '/trust', '/agents',
]

const contentTypes = new Map([
  ['.css', 'text/css; charset=utf-8'],
  ['.html', 'text/html; charset=utf-8'],
  ['.ico', 'image/x-icon'],
  ['.js', 'text/javascript; charset=utf-8'],
  ['.json', 'application/json; charset=utf-8'],
  ['.png', 'image/png'],
  ['.svg', 'image/svg+xml'],
  ['.webp', 'image/webp'],
  ['.woff2', 'font/woff2'],
  ['.wasm', 'application/wasm'],
])

const securityHeaders = {
  'content-security-policy': "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' https://v1.hitokoto.cn; media-src 'self' blob:; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
  'x-content-type-options': 'nosniff',
  'x-frame-options': 'DENY',
  'referrer-policy': 'strict-origin-when-cross-origin',
  'permissions-policy': 'camera=(self), microphone=(self), geolocation=(), payment=(), usb=()',
}

function safeEqual(left, right) {
  const leftBuffer = Buffer.from(left)
  const rightBuffer = Buffer.from(right)
  return leftBuffer.length === rightBuffer.length && crypto.timingSafeEqual(leftBuffer, rightBuffer)
}

function isAuthorized(request) {
  const header = request.headers.authorization || ''
  if (!header.startsWith('Basic ')) return false
  try {
    const decoded = Buffer.from(header.slice(6), 'base64').toString('utf8')
    const separator = decoded.indexOf(':')
    if (separator < 0) return false
    return safeEqual(decoded.slice(0, separator), username)
      && safeEqual(decoded.slice(separator + 1), password)
  } catch {
    return false
  }
}

function requiresBackend(request, pathname) {
  if (pathname === '/openapi.json' || pathname === '/docs' || pathname.startsWith('/docs/')) {
    return true
  }
  if (pathname === '/api' || pathname.startsWith('/api/')) return true
  const matchesPrefix = apiPrefixes.some((prefix) => (
    pathname === prefix || pathname.startsWith(`${prefix}/`)
  ))
  if (!matchesPrefix) return false
  if (request.method !== 'GET' && request.method !== 'HEAD') return true
  return !(request.headers.accept || '').includes('text/html')
}

function sendJson(response, status, payload, headers = {}) {
  const body = Buffer.from(JSON.stringify(payload))
  response.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': body.length,
    ...headers,
  })
  response.end(body)
}

function proxyRequest(request, response) {
  const contentLength = Number.parseInt(request.headers['content-length'] || '0', 10)
  if (Number.isFinite(contentLength) && contentLength > maxBodyBytes) {
    sendJson(response, 413, { success: false, error: '上传内容超过 64 MB 临时演示上限' })
    return
  }

  const headers = { ...request.headers }
  headers.host = backendUrl.host
  headers['x-forwarded-host'] = request.headers.host || ''
  headers['x-forwarded-proto'] = 'https'

  const upstream = http.request({
    protocol: backendUrl.protocol,
    hostname: backendUrl.hostname,
    port: backendUrl.port,
    method: request.method,
    path: request.url,
    headers,
    timeout: 120_000,
  }, (upstreamResponse) => {
    response.writeHead(upstreamResponse.statusCode || 502, upstreamResponse.headers)
    upstreamResponse.pipe(response)
  })

  upstream.on('timeout', () => upstream.destroy(new Error('upstream timeout')))
  upstream.on('error', () => {
    if (!response.headersSent) {
      sendJson(response, 502, { success: false, error: 'FileMate 后端暂不可用' })
    } else {
      response.destroy()
    }
  })
  request.pipe(upstream)
}

function serveFrontend(pathname, response) {
  let relativePath
  try {
    relativePath = decodeURIComponent(pathname).replace(/^\/+/, '')
  } catch {
    sendJson(response, 400, { success: false, error: '请求路径无效' })
    return
  }

  const candidate = path.resolve(staticRoot, relativePath || 'index.html')
  const insideStaticRoot = candidate === staticRoot || candidate.startsWith(`${staticRoot}${path.sep}`)
  let selected = path.join(staticRoot, 'index.html')
  let descriptor
  let stat
  try {
    if (insideStaticRoot && fs.statSync(candidate, { throwIfNoEntry: false })?.isFile()) {
      selected = candidate
    } else if (relativePath.startsWith('assets/') || relativePath.startsWith('interview-vision/') || contentTypes.has(path.extname(relativePath))) {
      sendJson(response, 404, { success: false, error: 'Static resource not found' })
      return
    }
    // Keep the opened file stable if a release directory changes during this response.
    descriptor = fs.openSync(selected, 'r')
    stat = fs.fstatSync(descriptor)
  } catch {
    if (descriptor !== undefined) fs.closeSync(descriptor)
    sendJson(response, 503, { success: false, error: 'Frontend temporarily unavailable' }, { 'retry-after': '5' })
    return
  }
  const extension = path.extname(selected).toLowerCase()
  const headers = {
    'content-type': contentTypes.get(extension) || 'application/octet-stream',
    'x-content-type-options': 'nosniff',
    'x-frame-options': 'DENY',
    'referrer-policy': 'strict-origin-when-cross-origin',
    'cache-control': selected.endsWith('index.html')
      ? 'no-cache'
      : 'public, max-age=31536000, immutable',
  }
  response.writeHead(200, { ...headers, 'content-length': stat.size })
  if (response.req.method === 'HEAD') {
    fs.closeSync(descriptor)
    response.end()
  } else {
    fs.createReadStream(selected, { fd: descriptor, autoClose: true })
      .on('error', () => response.destroy())
      .pipe(response)
  }
}

const server = http.createServer((request, response) => {
  for (const [name, value] of Object.entries(securityHeaders)) response.setHeader(name, value)
  if (!isAuthorized(request)) {
    sendJson(
      response,
      401,
      { success: false, error: '需要 FileMate 演示访问凭据' },
      { 'www-authenticate': 'Basic realm="FileMate Demo", charset="UTF-8"' },
    )
    return
  }

  const requestUrl = new URL(request.url || '/', `http://${request.headers.host || 'localhost'}`)
  if (requiresBackend(request, requestUrl.pathname)) {
    proxyRequest(request, response)
  } else if (request.method === 'GET' || request.method === 'HEAD') {
    serveFrontend(requestUrl.pathname, response)
  } else {
    sendJson(response, 404, { success: false, error: 'Not found' })
  }
})

server.listen(port, host, () => {
  process.stdout.write(`FileMate demo gateway: http://${host}:${server.address().port}\n`)
})
