<template>
  <div class="finder">
    <label class="finder-input">
      <Search :size="22" aria-hidden="true" />
      <input ref="input" v-model="query" role="combobox" aria-label="输入功能名称"
        aria-autocomplete="list" aria-expanded="true" aria-controls="feature-results"
        :aria-activedescendant="results.length ? `feature-option-${activeIndex}` : undefined"
        placeholder="搜索资料、面试、API、备份…" @keydown="handleKey" />
    </label>
    <p class="result-count" role="status">{{ query.trim() ? `找到 ${results.length} 项功能` : '选择要继续的任务' }}</p>
    <ul id="feature-results" ref="list" class="finder-results" role="listbox" aria-label="功能查找结果">
      <li v-for="(item, index) in results" :key="item.path" role="none" @pointermove="activeIndex = index">
        <button :id="`feature-option-${index}`" type="button" role="option" :aria-selected="index === activeIndex" tabindex="-1" @click="open(item)">
          <component :is="icons[item.icon]" :size="22" aria-hidden="true" />
          <span>{{ item.title }}</span><small>{{ item.group }}</small>
          <ArrowRight :size="18" class="result-arrow" aria-hidden="true" />
        </button>
      </li>
    </ul>
    <p v-if="!results.length" class="finder-empty">没有找到这个功能，换个关键词试试。</p>
    <p class="finder-hint">↑ ↓ 选择 · Enter 打开 · Esc 关闭</p>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch, type Component } from 'vue'
import { ArrowRight, Search } from '../icons'
import { searchTools, type Tool } from '../navigation/catalog'

const props = defineProps<{ tools: Tool[]; icons: Record<string, Component> }>()
const emit = defineEmits<{ select: [item: Tool] }>()
const input = ref<HTMLInputElement>()
const list = ref<HTMLElement>()
const query = ref('')
const activeIndex = ref(0)
const results = computed(() => searchTools(query.value, props.tools))
watch(results, () => { activeIndex.value = 0 })
watch(activeIndex, async () => {
  await nextTick()
  list.value?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' })
})
function handleKey(event: KeyboardEvent): void {
  if (event.isComposing || !results.value.length) return
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    const direction = event.key === 'ArrowDown' ? 1 : -1
    activeIndex.value = (activeIndex.value + direction + results.value.length) % results.value.length
  } else if (event.key === 'Enter') {
    event.preventDefault()
    const selected = results.value[activeIndex.value]
    if (selected) open(selected)
  }
}
function open(item: Tool): void { emit('select', item) }
function focus(): void { input.value?.focus() }
function reset(): void { query.value = ''; activeIndex.value = 0 }
defineExpose({ focus, reset })
</script>

<style scoped>
.finder-input { display:flex; align-items:center; gap:12px; padding:0 14px; border:1px solid var(--border-strong); border-radius:10px; color:var(--text-muted); background:var(--bg-base); }
.finder-input:focus-within { outline:2px solid var(--accent); outline-offset:2px; }
.finder-input input { width:100%; min-width:0; min-height:56px; border:0; outline:none; background:transparent; color:var(--text-primary); font:inherit; font-size:18px; }
.result-count { margin:20px 0 10px; color:var(--text-secondary); font-size:15px; }
.finder-results { list-style:none; padding:0; margin:0; max-height:min(380px, 48dvh); overflow:auto; scroll-padding:8px; }
.finder-results li { margin-bottom:3px; border-radius:10px; }
.finder-results button { display:flex; align-items:center; gap:12px; width:100%; min-height:52px; padding:10px 12px; border:0; border-radius:inherit; background:transparent; color:var(--text-primary); text-align:left; font:inherit; font-size:17px; cursor:pointer; }
.finder-results button[aria-selected="true"] { background:var(--accent-soft); outline:1px solid var(--accent-border); outline-offset:-1px; }
.finder-results span { min-width:0; overflow-wrap:anywhere; }
.finder-results svg { flex-shrink:0; color:var(--accent); }
.finder-results small { margin-left:auto; color:var(--text-secondary); font-size:14px; white-space:nowrap; }
.result-arrow { opacity:0; }
[aria-selected="true"] .result-arrow { opacity:1; }
.finder-hint,.finder-empty { margin:16px 0 0; color:var(--text-muted); font-size:14px; line-height:1.6; }
.finder-hint { border-top:1px solid var(--border-subtle); padding-top:16px; }
@media(max-width:560px) { .finder-results button { font-size:16px; gap:10px; padding-inline:8px; } .finder-results small { font-size:13px; } .result-arrow { display:none; } }
</style>
