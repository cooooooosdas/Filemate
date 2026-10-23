<template>
  <div class="cw-manager-content"><CourseGraphPanel ref="panel" :sources="sources" :initial-course-id="courseId" managed @changed="$emit('changed', $event)" /></div>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import type { KnowledgeSource } from '../../services/api'
import CourseGraphPanel from './CourseGraphPanel.vue'
defineProps<{ courseId: string; sources: KnowledgeSource[] }>()
defineEmits<{ changed: [id: string]; closed: [] }>()
const panel = ref<{ canLeave(): Promise<boolean> } | null>(null)
defineExpose({ canLeave: () => panel.value?.canLeave() ?? Promise.resolve(true) })
</script>
