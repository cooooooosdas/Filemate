import assert from 'node:assert/strict'
import test from 'node:test'
import { createEncouragementPicker, parseHitokotoQuote, splitQuote, CLASSIC_FALLBACKS } from '../src/home/encouragement.ts'
const sample = (overrides = {}) => ({ uuid:'b883d487-2423-4941-b812-6b4f46e91be5', hitokoto:'明年此日青云去，却笑人间举子忙。', type:'i', from:'鹧鸪天·送廓之秋试', from_who:'辛弃疾', ...overrides })
const cacheKey = 'filemate.home.poetry-cache.v1', lastKey = 'filemate.home.last-encouragement'
function storage(initial = {}) { const values = new Map(Object.entries(initial)); return { getItem:key=>values.get(key) ?? null, setItem:(key,value)=>values.set(key,value) } }
const offline = async () => { throw new Error('Offline') }

test('remote poetry preserves original wording, attribution and official detail link', () => {
  const quote = parseHitokotoQuote(sample())
  assert.equal(quote.text, sample().hitokoto)
  assert.equal(quote.author, '辛弃疾')
  assert.equal(quote.source, sample().from)
  assert.equal(quote.url, 'https://hitokoto.cn/?uuid=' + sample().uuid)
})
test('missing author and source stay absent instead of being invented', () => {
  const quote = parseHitokotoQuote(sample({from_who:null,from:null}))
  assert.equal(quote.author,null)
  assert.equal(quote.source,null)
})
test('non-poetry, malformed, oversized and executable-looking responses are rejected', () => {
  for (const value of [null,[],sample({type:'e'}),sample({uuid:'javascript:alert(1)'}),sample({hitokoto:'短句'}),sample({hitokoto:'天'.repeat(23)}),sample({hitokoto:'<script>alert(1)</script>'})]) assert.equal(parseHitokotoQuote(value),null)
})
test('line breaks never rewrite or drop original punctuation', () => {
  for(const text of [sample().hitokoto,...CLASSIC_FALLBACKS.map(q=>q.text),'天地玄黄宇宙洪荒日月盈昃辰宿列张']) assert.equal(splitQuote(text).join(''),text)
})
test('concurrent mounts and route returns share one in-flight request', async () => {
  let calls = 0, finish
  const pick = createEncouragementPicker({load:()=>{calls++;return new Promise(resolve=>{finish=resolve})}})
  const first = pick(), second = pick()
  assert.equal(first,second)
  finish(sample())
  const quote = await first
  assert.equal(await pick(),quote)
  assert.equal(calls,1)
})
test('the online corpus is not limited to the bundled fallback sentences', async () => {
  const quote = await createEncouragementPicker({load:async()=>sample()})()
  assert.equal(quote.provider,'hitokoto')
  assert.ok(CLASSIC_FALLBACKS.every(item=>item.text!==quote.text))
})
test('network failure reuses validated cached poetry with its attribution', async () => {
  const cached = parseHitokotoQuote(sample())
  const quote = await createEncouragementPicker({load:offline, random:()=>0, storage:()=>storage({[cacheKey]:JSON.stringify([cached])})})()
  assert.deepEqual(quote,cached)
})
test('a repeated remote sentence selects a different cached or classic sentence', async () => {
  const cached = parseHitokotoQuote(sample()), store = storage({[cacheKey]:JSON.stringify([cached]),[lastKey]:cached.id})
  const quote = await createEncouragementPicker({load:async()=>sample(),random:()=>0,storage:()=>store})()
  assert.notEqual(quote.id,cached.id)
  assert.equal(store.getItem(lastKey),quote.id)
})
test('duplicate wording under a different UUID still avoids the previous sentence', async () => {
  const cached = parseHitokotoQuote(sample()), store=storage({[cacheKey]:JSON.stringify([cached]),[lastKey]:cached.id})
  const quote = await createEncouragementPicker({load:async()=>sample({uuid:'bb83d487-2423-4941-b812-6b4f46e91be5'}),random:()=>0,storage:()=>store})()
  assert.notEqual(quote.text,cached.text)
})
test('corrupt cache, wrong category and tampered links cannot replace trusted fallback', async () => {
  for (const value of ['bad-json',JSON.stringify([{id:'javascript:alert(1)',text:'<script>恶意内容</script>',url:'javascript:alert(1)'}])]) {
    const quote=await createEncouragementPicker({load:async()=>sample({type:'a'}),random:()=>0,storage:()=>storage({[cacheKey]:value})})()
    assert.equal(quote,CLASSIC_FALLBACKS[0])
  }
})
test('denied and read-only browser storage do not break either online or offline visits', async () => {
  const denied=()=>{throw new Error('Storage denied')}
  for (const store of [denied,()=>({getItem:denied,setItem:denied}),()=>({getItem:()=>null,setItem:denied})]) {
    for(const load of [async()=>sample(),offline]) {
      const pick=createEncouragementPicker({load,storage:store})
      assert.equal(await pick(),await pick())
      assert.ok((await pick()).text)
    }
  }
})
test('remote cache is capped and restored URLs are rebuilt from validated UUIDs', async () => {
  const existing=Array.from({length:30},(_,i)=>({...parseHitokotoQuote(sample()),id:'00000000-0000-0000-0000-'+String(i).padStart(12,'0'),text:'会当凌绝顶，一览众山小。',url:'javascript:alert(1)'}))
  const store=storage({[cacheKey]:JSON.stringify(existing)})
  await createEncouragementPicker({load:async()=>sample(),storage:()=>store})()
  const saved=JSON.parse(store.getItem(cacheKey))
  assert.equal(saved.length,24)
  assert.ok(saved.every(quote=>quote.url.startsWith('https://hitokoto.cn/?uuid=')))
})
