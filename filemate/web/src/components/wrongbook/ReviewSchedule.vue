<template>
  <section aria-label="排期管理"><p>所有日期按上海时区记录。更改前先核对预览，作答证据不会被删除。</p>
    <div class="review-actions"><button :disabled="!c.writable()" @click="c.previewSchedule({action: d.schedule_status === 'paused' ? 'resume' : 'pause'})">{{ d.schedule_status === 'paused' ? '预览恢复' : '预览暂停' }}</button><button v-if="d.scheduler_version === 'legacy-v1'" :disabled="!c.writable()" @click="c.previewSchedule({action:'activate'})">预览启用新规则</button></div>
    <form class="review-actions" @submit.prevent="reschedule"><label>下次复习（上海）<input v-model="date" type="datetime-local" required /></label><button :disabled="!c.writable()">预览改期</button></form>
    <ElDialog :model-value="!!c.state.preview" title="核对排期变更" width="min(560px, 94vw)" :close-on-click-modal="false" :before-close="close" @closed="date = ''">
      <div v-if="c.state.preview" class="review-dialog"><p>时区：Asia/Shanghai</p><p>当前：{{ c.state.preview.before.schedule_status }} · {{ reviewTime(c.state.preview.before.next_review_at) }}</p><p>变更后：{{ c.state.preview.after.schedule_status || c.state.preview.before.schedule_status }} · {{ reviewTime(c.state.preview.after.next_review_at || c.state.preview.before.next_review_at) }}</p><p v-if="c.state.writeError" role="alert">{{ c.state.writeError }}</p><div class="review-actions"><button :disabled="c.state.writing" @click="close()">返回</button><button class="primary" :disabled="c.state.writing" @click="c.confirmSchedule()">{{ c.state.writing ? '正在确认…' : '确认变更' }}</button></div></div>
    </ElDialog>
  </section>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { ElDialog } from 'element-plus'
import { reviewTime } from '../../wrongbook/presentation'
import type { ReviewDetail } from '../../types/wrongbook'
import type { createReviewWorkspaceController } from '../../wrongbook/workspace-state'
const props = defineProps<{ c: ReturnType<typeof createReviewWorkspaceController>; d: ReviewDetail }>()
const date = ref('')
function reschedule() { if (date.value) props.c.previewSchedule({ action: 'reschedule', next_review_at: `${date.value}:00+08:00` }) }
function close(done?: () => void) { props.c.cancelPreview(); if (!props.c.state.preview) done?.() }
</script>
