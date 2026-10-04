<template>
  <aside class="hero-encouragement" aria-label="今日一言" :data-encouragement="quote?.id" :data-provider="quote?.provider" :data-category="quote?.category" :aria-busy="!quote">
    <span class="encouragement-label">一言<span v-if="quote"> · {{ QUOTE_CATEGORIES[quote.category] }}</span></span>
    <template v-if="quote">
      <p class="encouragement-words"><span v-for="(line, index) in lines" :key="index" class="verse-line">{{ line }}</span></p>
      <a class="encouragement-source" :href="quote.url" target="_blank" rel="noopener noreferrer" :title="attribution" :aria-label="`${attribution}，在新标签页查看出处`"><cite>{{ attribution }}</cite><span aria-hidden="true">↗</span></a>
    </template>
    <div v-else class="encouragement-loading" role="status" aria-label="正在读取一言"><span /><span /></div>
  </aside>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, shallowRef } from 'vue'
import { getVisitEncouragement } from '../home/visitEncouragement'
import { splitQuote, QUOTE_CATEGORIES } from '../home/encouragement'
import type { Encouragement } from '../types/encouragement'
const quote = shallowRef<Encouragement | null>(null)
const lines = computed(() => quote.value ? splitQuote(quote.value.text) : [])
const attribution = computed(() => {
  const current = quote.value
  if (!current) return ''
  const source = current.source ? (current.source.startsWith('《') ? current.source : `《${current.source}》`) : ''
  return [current.author, source].filter(Boolean).join(' · ') || '一言语句'
})
let mounted = true
onMounted(async () => { const selected = await getVisitEncouragement(); if (mounted) quote.value = selected })
onUnmounted(() => { mounted = false })
</script>

<style scoped>
.hero-encouragement { position:relative; z-index:1; align-self:start; min-width:0; margin-top:26px; padding:0 0 140px 26px; }
.hero-encouragement::before { content:''; position:absolute; left:0; top:0; bottom:140px; width:2px; background:#d5e8f480; }
.encouragement-label { display:block; margin-bottom:22px; color:#dcebf6; font-size:18px; font-weight:500; letter-spacing:.08em; }
.encouragement-words { margin:0; color:#f5f8fc; font-size:clamp(26px,2.4vw,34px); line-height:1.6; letter-spacing:-.025em; text-wrap:balance; }
.verse-line { display:block; }
.verse-line:last-child { color:#e0edf8; font-weight:600; }
.encouragement-source { display:flex; align-items:center; gap:10px; min-height:44px; margin-top:12px; color:#dcebf6; font-size:16px; line-height:1.5; text-decoration:none; }
.encouragement-source cite { font-style:normal; display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:2; overflow:hidden; }
.encouragement-source:hover { color:#ffffff; text-decoration:underline; text-underline-offset:4px; }
.encouragement-source > span { flex-shrink:0; font-size:20px; }
.encouragement-loading { height:150px; padding-top:14px; }
.encouragement-loading span { display:block; height:28px; margin-bottom:22px; width:85%; background:#dcebf61a; border-radius:4px; }
.encouragement-loading span:last-child { width:65%; }
@media(max-width:1150px) { .hero-encouragement { padding-left:20px; }.encouragement-label { margin-bottom:18px; }.encouragement-words { font-size:28px; } }
@media(max-width:900px) { .hero-encouragement { margin-top:0; padding:24px 0 0; border-top:1px solid #d5e8f466; }.hero-encouragement::before { display:none; }.encouragement-label { font-size:16px; margin-bottom:12px; }.encouragement-words { font-size:26px; line-height:1.55; } }
@media(max-width:700px) { .encouragement-words { font-size:24px; } }
</style>
