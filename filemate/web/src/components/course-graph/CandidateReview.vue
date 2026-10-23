<template>
  <section class="candidate-source" :aria-label="`核对${name}`">
    <h3>{{ name }}</h3>
    <p>状态：{{ statusLabel(source.status) }}<span v-if="!source.source_current"> · 原资料已变化或不在课程中，请重新提取</span></p>
    <p v-if="source.error_code" role="status">本份未完成：{{ source.error_code }}。已保存的其他结果保留，可重试失败来源。</p>
    <p v-if="source.payload.coverage?.source_truncated">本次仅核对前 20,000 字符；后续原文尚未覆盖。</p>
    <p v-if="!all.length">这份资料尚无可核对候选。请先提取或重试。</p>
    <article v-for="item in pageItems" :key="item.item_id" class="candidate" :data-candidate="item.item_id">
      <div class="candidate-heading"><span>{{ item.kind === 'node' ? '概念' : '关系' }}</span><h4>{{ title(item) }}</h4></div>
      <blockquote>{{ item.original.excerpt || '没有可验证的原文' }}</blockquote>
      <p v-if="item.parsed?.page">第 {{ item.parsed.page }} 页</p>
      <p v-if="item.parsed?.legacy_mapping_ambiguous">旧版术语键有歧义；本概念保持独立，不自动关联旧题目。</p>
      <p v-if="item.validation === 'needs_semantic_review'">引文位置有效；关系含义需你核对。</p>
      <p v-if="item.review_status === 'confirmed'" class="published">已确认入图 · 可在历史中撤销</p>
      <p v-else-if="item.review_status === 'revoked'">已撤销 · 请从历史恢复</p>
      <template v-else>
        <div class="choice-actions" :aria-label="`审核${title(item)}`">
          <button :aria-pressed="choice(item)?.verdict === 'accept'" :disabled="disabled || !source.source_current" @click="decide(item, { verdict: 'accept' })">接受</button>
          <button :aria-pressed="choice(item)?.verdict === 'revise'" :disabled="disabled || !source.source_current" @click="decide(item, { verdict: 'revise' })">修订</button>
          <button :aria-pressed="choice(item)?.verdict === 'reject'" :disabled="disabled" @click="decide(item, { verdict: 'reject' })">拒绝</button>
          <span v-if="!choice(item)">待选择</span>
        </div>
        <div v-if="choice(item)?.verdict === 'revise'" class="revision-fields">
          <label v-if="item.kind === 'node'">显示名称<input :value="choice(item)?.label ?? item.original.label" maxlength="120" :disabled="disabled" @input="decide(item, { label: input($event) })" /></label>
          <template v-else>
            <label>起点术语<input :value="choice(item)?.from_label ?? item.original.from" maxlength="120" :disabled="disabled" @input="decide(item, { from_label: input($event) })" /></label>
            <label>关系<select :value="choice(item)?.relation ?? item.original.relation" :disabled="disabled" @change="relation(item, $event)"><option v-for="(label, value) in relations" :key="value" :value="value">{{ label }}</option></select></label>
            <label>终点术语<input :value="choice(item)?.to_label ?? item.original.to" maxlength="120" :disabled="disabled" @input="decide(item, { to_label: input($event) })" /></label>
          </template>
          <label v-if="item.kind === 'node'">人工别名（逗号分隔）<input :value="choice(item)?.aliases?.join('，') || ''" maxlength="2400" :disabled="disabled" @input="decide(item, { aliases: input($event).split(/[,，]/).map(a => a.trim()).filter(Boolean).slice(0, 20) })" /></label>
          <p>原引文保持原样；修订名称不会修复无效引用。</p>
        </div>
        <label v-if="item.validation === 'needs_semantic_review'" class="check"><input type="checkbox" :checked="choice(item)?.semantic_checked || false" :disabled="disabled" @change="decide(item, { semantic_checked: ($event.target as HTMLInputElement).checked })" />我已核对这段原文确实支持该关系</label>
      </template>
    </article>
    <nav v-if="valid.length > size" aria-label="候选分页"><button :disabled="page === 0" @click="page--">前一页候选</button><span>{{ page + 1 }} / {{ Math.ceil(valid.length / size) }}</span><button :disabled="(page + 1) * size >= valid.length" @click="page++">后一页候选</button></nav>
    <details v-if="invalid.length" class="invalid-items"><summary>不可确认的候选 · {{ invalid.length }} 项</summary><article v-for="item in invalid" :key="item.item_id"><h4>{{ title(item) }}</h4><blockquote>{{ item.original.excerpt || '缺少原文' }}</blockquote><p>{{ item.error_codes?.map(code => errors[code] || code).join('；') }}</p><button :disabled="disabled || item.review_status === 'confirmed'" @click="decide(item, { verdict: 'reject' })">{{ choice(item)?.verdict === 'reject' ? '已标记拒绝' : '拒绝此项' }}</button></article></details>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { CourseCandidate, CourseDecision, CourseExtraction, RelationKind } from '../../types/courseGraph'
const props = defineProps<{ source: CourseExtraction; name: string; choices: Record<string, CourseDecision>; disabled: boolean }>()
const emit = defineEmits<{ decide: [choice: CourseDecision] }>()
const size = 12, page = ref(0)
const all = computed(() => [...(props.source.payload.nodes || []), ...(props.source.payload.edges || [])])
const valid = computed(() => all.value.filter(i => i.validation !== 'invalid'))
const invalid = computed(() => all.value.filter(i => i.validation === 'invalid'))
const pageItems = computed(() => valid.value.slice(page.value * size, (page.value + 1) * size))
watch(() => props.source.source_id, () => { page.value = 0 })
const relations: Record<RelationKind, string> = { prerequisite: '前置知识', depends_on: '依赖于', part_of: '属于', contains: '包含', application: '应用于', related_to: '相关' }
const errors: Record<string, string> = { quote_not_found: '引文未在原文连续出现', missing_endpoint: '关系端点缺少有效概念', invalid_schema: '格式不符合要求', unsupported_relation: '原文不支持此关系', term_not_in_quote: '术语未出现在引文中' }
function title(item: CourseCandidate) { return item.original.label || `${item.original.from || '未知起点'} → ${item.original.to || '未知终点'}` }
function choice(item: CourseCandidate) { return props.choices[item.item_id] }
function decide(item: CourseCandidate, update: Partial<CourseDecision>) { const current = choice(item) || { item_id: item.item_id, verdict: 'revise' as const }; emit('decide', { ...current, ...update }) }
function input(event: Event) { return (event.target as HTMLInputElement).value }
function relation(item: CourseCandidate, event: Event) { decide(item, { relation: input(event) as RelationKind }) }
function statusLabel(status: string) { return ({ pending: '等待提取', running: '正在提取', ready: '已提取', partial: '部分引文需处理', failed: '失败可重试', interrupted: '已中断可重试', cancelled: '已取消', unavailable: '来源已删除' } as Record<string, string>)[status] || status }
</script>
