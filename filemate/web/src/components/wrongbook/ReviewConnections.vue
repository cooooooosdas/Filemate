<template>
  <section class="learning-section" aria-label="关联知识图谱">
    <h3>回到知识点</h3><p v-if="!items.length">暂无有效的课程映射；不会按名称猜测关联。</p>
    <label v-if="courses.length">本次只使用一门课程的证据<select :value="course" :disabled="disabled" @change="$emit('course',($event.target as HTMLSelectElement).value)"><option value="">仅使用本题资料</option><option v-for="item in courses" :key="item.course_id" :value="item.course_id">{{ item.course_name || item.course_id }}</option></select></label>
    <ul class="learning-links"><li v-for="item in visible" :key="`${item.course_id}-${item.concept_id}`"><RouterLink :to="item.route">{{ item.label || item.concept_id }}<span> · 打开原文证据</span></RouterLink></li></ul>
  </section>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import type { ReviewConnection } from '../../types/reviewLearning'
const props=defineProps<{items:ReviewConnection[];course:string;disabled?:boolean}>()
defineEmits<{course:[value:string]}>()
const courses=computed(()=>[...new Map(props.items.map(item=>[item.course_id,item])).values()])
const visible=computed(()=>props.items.filter(item=>!props.course||item.course_id===props.course))
</script>
