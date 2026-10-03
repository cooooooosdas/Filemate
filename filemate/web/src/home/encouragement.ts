import type { Encouragement } from '../types/encouragement'

export const CLASSIC_FALLBACKS: readonly Encouragement[] = [
  { id: 'classic-wang-yue', text: '会当凌绝顶，一览众山小。', source: '望岳', author: '杜甫',
    url: 'https://www.gushiwen.cn/mingju_960.aspx', provider: 'classic' },
  { id: 'classic-du-shu', text: '纸上得来终觉浅，绝知此事要躬行。', source: '冬夜读书示子聿', author: '陆游',
    url: 'https://m.ccdi.gov.cn/content/7d/c6/23245.html', provider: 'classic' },
]
type QuoteStorage = Pick<Storage, 'getItem' | 'setItem'>
const CACHE_KEY = 'filemate.home.poetry-cache.v1'
const LAST_QUOTE_KEY = 'filemate.home.last-encouragement'
const UUID = /^[\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12}$/i

export function parseHitokotoQuote(value: unknown): Encouragement | null {
  if (!value || typeof value !== 'object') return null
  const data = value as Record<string, unknown>
  if (data.type !== 'i' || typeof data.uuid !== 'string' || !UUID.test(data.uuid) || typeof data.hitokoto !== 'string') return null
  const text = data.hitokoto.trim()
  if ([...text].length < 8 || [...text].length > 22 || /[<>\r\n\u0000-\u001f]/u.test(text)) return null
  const field = (name: string, limit: number): string | null => {
    const value = data[name]
    return typeof value === 'string' && value.trim().length <= limit && value.trim() ? value.trim() : null
  }
  return { id: data.uuid, text, source: field('from', 80), author: field('from_who', 40),
    url: 'https://hitokoto.cn/?uuid=' + data.uuid, provider: 'hitokoto' }
}

function readCache(storage?: QuoteStorage): Encouragement[] {
  try {
    const data: unknown = JSON.parse(storage?.getItem(CACHE_KEY) ?? '[]')
    if (!Array.isArray(data)) return []
    return data.slice(-24).flatMap(item => {
      if (!item || typeof item !== 'object') return []
      const quote = parseHitokotoQuote({ type: 'i', uuid: item.id, hitokoto: item.text, from: item.source, from_who: item.author })
      return quote ? [quote] : []
    })
  } catch { return [] }
}

export function splitQuote(text: string): string[] {
  const cuts = [...text.matchAll(/[，。！？；,.!?;]/gu)].map(match => match.index + match[0].length).filter(index => index < text.length)
  const cut = cuts.sort((a, b) => Math.abs(a - text.length / 2) - Math.abs(b - text.length / 2))[0]
  return cut ? [text.slice(0, cut), text.slice(cut)] : [text]
}

export function createEncouragementPicker(options: {
  load: () => Promise<unknown>
  random?: () => number
  storage?: () => QuoteStorage | undefined
}): () => Promise<Encouragement> {
  let chosen: Promise<Encouragement> | undefined
  return () => chosen ??= (async () => {
    let storage: QuoteStorage | undefined
    let previous: string | null = null
    try { storage = options.storage?.(); previous = storage?.getItem(LAST_QUOTE_KEY) ?? null } catch { /* 禁用存储不影响诗词阅读。 */ }
    const cache = readCache(storage)
    const previousText = [...cache, ...CLASSIC_FALLBACKS].find(quote => quote.id === previous)?.text
    let remote: Encouragement | null = null
    try { remote = parseHitokotoQuote(await options.load()) } catch { /* 网络失败时使用已有诗词，不阻塞学习入口。 */ }
    if (remote) {
      const deduped = cache.filter(quote => quote.id !== remote!.id && quote.text !== remote!.text)
      cache.splice(0, cache.length, ...deduped.slice(-23), remote)
      try { storage?.setItem(CACHE_KEY, JSON.stringify(cache)) } catch { /* 只读存储时本次仍可显示接口原文。 */ }
    }
    const alternatives = [...cache, ...CLASSIC_FALLBACKS].filter(quote => quote.id !== previous && quote.text !== previousText)
    const quote = remote && remote.id !== previous && remote.text !== previousText ? remote : alternatives[Math.floor((options.random ?? Math.random)() * alternatives.length)]!
    try { storage?.setItem(LAST_QUOTE_KEY, quote.id) } catch { /* 上一句记录失败不影响阅读。 */ }
    return quote
  })()
}
