<template>
  <section class="merge-section" aria-labelledby="merge-heading">
    <h3 id="merge-heading">把同一概念的出处放在一起</h3><p>选择 2–20 个同课概念，指定保留的代表。原 ID、原文和学习记录继续保留。</p>
    <label>融合后显示为<select :value="target" :disabled="disabled" @change="emit('target', ($event.target as HTMLSelectElement).value)"><option value="">选择代表概念</option><option v-for="node in selected" :key="node.id" :value="node.id">{{ node.label }}</option></select></label>
    <button :disabled="disabled || selected.length < 2 || !target" @click="emit('preview')">预览融合影响（{{ selected.length }}）</button>
    <div v-if="preview" class="confirmation" role="region" aria-label="融合确认">
      <h4>核对后再融合</h4><ul><li v-for="node in preview.concepts" :key="node.concept_id"><strong>{{ node.label }}{{ node.concept_id === target ? ' · 代表概念' : '' }}</strong><p>{{ node.member_ids.length }} 条原记录 · {{ node.source_count }} 个当前有效来源</p><p v-if="!node.source_refs.length">无有效来源，请确认仍需融合。</p><div v-for="ref in node.source_refs" :key="ref.evidence_id"><strong>{{ ref.original_name }}</strong><blockquote>{{ ref.excerpt }}</blockquote><router-link :to="{ path: '/ai-tools', query: { source: ref.source_id } }">核对原资料</router-link></div></li></ul>
      <p>涉及 {{ preview.ids.concepts.length }} 条概念记录；{{ preview.self_edge_count }} 条自身关系将不在视图显示。若产生前置依赖环，系统会拒绝。</p>
      <button class="primary" :disabled="disabled" @click="emit('confirm')">确认融合所选概念</button>
    </div>
  </section>
</template>
<script setup lang="ts">
import type { CourseConcept, CourseMergePreview } from '../../types/courseGraph'
defineProps<{ selected: CourseConcept[]; target: string; preview: CourseMergePreview | null; disabled: boolean }>()
const emit = defineEmits<{ target: [id: string]; preview: []; confirm: [] }>()
</script>
