<template>
  <section class="interview-video-library" aria-label="本页录像回看">
    <h3>{{ title || '录像回看' }} <span>{{ takes.length }} 段</span></h3>
    <p v-if="!takes.length">暂无本页录像。刷新或离开后录像会清除，已保存文字仍可回看。</p>
    <article v-for="take in takes" :key="take.id">
      <h4>第 {{ take.binding.questionIndex + 1 }} 题 · {{ take.attemptId ? '已关联回答' : '未关联片段' }}</h4>
      <p>{{ take.duration.toFixed(1) }} 秒 · {{ take.hasAudio ? '含声音' : '静音画面' }}<strong v-if="take.partial"> · 录制中断，仅保留已采集部分</strong></p>
      <p v-if="take.issue">{{ videoIssue(take.issue) }}</p>
      <video :src="take.url" controls playsinline preload="metadata" :aria-label="`第${take.binding.questionIndex + 1}题录像`" @play="play($event)" />
      <div><button type="button" @click="$emit('download', take.id)"><ArrowDown :size="20" />导出录像</button><button type="button" @click="$emit('remove', take.id)"><Trash :size="20" />删除片段</button></div>
    </article>
  </section>
</template>
<script setup lang="ts">
import type { VideoItem } from '../types/interviewVideo'
import { ArrowDown, Trash } from '../icons'
import { videoIssue } from '../interview/video-messages'
const props = defineProps<{takes: VideoItem[]; title?: string; busy?: boolean}>()
const emit = defineEmits<{download: [id: string]; remove: [id: string]; play: []}>()
function play(event: Event) {
  const video = event.target as HTMLVideoElement
  if (props.busy) { video.pause(); return }
  document.querySelectorAll<HTMLMediaElement>('.interview-video-library video, .interview-audio-panel audio').forEach(other => { if (other !== video) other.pause() })
  emit('play')
}
</script>
<style scoped>
.interview-video-library { min-width: 0; padding: 18px 0; text-align: left; }
h3,h4,p { margin: 0 0 12px; } h3 { font-size: 22px; } h4 { font-size: 18px; } h3 span,p { font-size: 16px; color: var(--text-secondary); line-height: 1.6; }
article { padding: 18px 0; border-top: 1px solid var(--border-color); } video { width: 100%; max-height: 360px; background: #111827; border-radius: 12px; }
article div { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 12px; } button { min-height: 44px; display: inline-flex; align-items: center; gap: 8px; font-size: 17px; padding: 8px 14px; color: var(--text-primary); background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 10px; }
</style>
