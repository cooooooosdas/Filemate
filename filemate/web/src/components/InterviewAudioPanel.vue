<template>
  <section class="interview-audio-panel" aria-label="独立录音与转写">
    <header><div><p>本机声音记录</p><h3>{{ summary ? '本场录音回听' : '说一遍，再听一遍' }}</h3></div><IconMicrophone :size="28" aria-hidden="true" /></header>
    <p>录音只在当前页面内存，刷新或离开即清除。请及时导出；单段最多10分钟／20MiB，本页最多30段／60MiB。</p>
    <div v-if="!summary" class="audio-actions">
      <button type="button" :disabled="locked || busy || blocked" @click="$emit('record')"><IconMicrophone :size="20" aria-hidden="true" />开始独立录音</button>
      <button v-if="busy" type="button" @click="$emit('stop')"><IconPlayerStop :size="20" aria-hidden="true" />停止采集</button>
      <span role="status">{{ captureLabels[phase] || phase }}</span>
    </div>
    <p v-if="captureError" role="alert">{{ errors[captureError] || captureError }}。文字回答仍可使用。</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <details v-if="!summary" class="audio-asr"><summary>可选：把语音转为文字</summary>
      <p>转写由浏览器提供，可能将音频发送给浏览器厂商；联网失败或不支持时可直接打字。独立录音不需要这项授权。</p>
      <label><input type="checkbox" :checked="allowed" :disabled="blocked || locked" @change="$emit('consent', ($event.target as HTMLInputElement).checked)" />本场允许使用浏览器语音转写</label>
      <button type="button" :disabled="!allowed || busy || blocked || locked" @click="$emit('transcribe')">开始转写，追加到已有文字</button>
      <p role="status">{{ asrLabels[transcription.status] }}<span v-if="transcription.preview"> · 临时识别：{{ transcription.preview }}</span></p>
      <p v-if="transcription.segments.length">已保留{{ transcription.segments.length }}段最终转写；供应商置信估计{{ transcription.confidence == null ? '未提供' : transcription.confidence.toFixed(2) }}（非准确率）。提交前可在回答框修改。</p>
    </details>
    <ul v-if="takes.length" class="audio-takes"><li v-for="take in takes" :key="take.id">
      <div class="audio-take-heading"><strong>第{{ take.binding.questionIndex + 1 }}题 · {{ take.attemptId ? '已关联回答' : '未关联的本机录音' }}</strong><span>{{ take.captureSeconds.toFixed(1) }}秒</span></div>
      <audio :src="take.url" controls preload="metadata" @play="onPlay" />
      <p v-if="take.partial">录音不完整：{{ errors[take.issue || ''] || '设备中断' }}，可回听并导出已采集部分。</p>
      <p v-if="take.summary">低能量{{ take.summary.low_energy_seconds.toFixed(1) }}秒 · RMS {{ take.summary.rms.toFixed(3) }} · 削波{{ (take.summary.clipping_ratio * 100).toFixed(1) }}%。设备摘要，未经服务端核验；非能力评分，低能量不等于停顿。</p>
      <p v-else>音频摘要无法测量；保留原录音，不推算指标。</p>
      <div class="audio-actions"><button type="button" :disabled="blocked" @click="$emit('download',take.id)"><IconDownload :size="19" aria-hidden="true" />导出录音</button><button type="button" :disabled="busy || blocked" @click="$emit('remove',take.id)"><IconTrash :size="19" aria-hidden="true" />删除本机这段</button></div>
    </li></ul>
    <p v-else>本页没有这部分录音。刷新后仅保留已提交的文字、摘要和转写来源，原录音需提前导出。</p>
  </section>
</template>
<script setup lang="ts">
import { IconMicrophone, IconPlayerStop, IconDownload, IconTrash } from '@tabler/icons-vue'
import type { StoredAudio } from '../interview/audio-collection'
import type { TranscriptionEvidence } from '../types/interviewAudio'
const props=defineProps<{takes:StoredAudio[];phase:string;captureError:string|null;transcription:TranscriptionEvidence&{preview:string};allowed:boolean;busy:boolean;blocked:boolean;locked:boolean;summary?:boolean;error:string}>()
const emit=defineEmits<{record:[];stop:[];transcribe:[];consent:[value:boolean];download:[id:string];remove:[id:string];play:[]}>()
const captureLabels:Record<string,string>={idle:'就绪',requesting:'等待麦克风授权…',recording:'录音中',stopping:'正在收尾并计算本机摘要…'}
const asrLabels:Record<string,string>={idle:'尚未转写',permission_required:'请先授权',unsupported:'当前浏览器不支持语音转写',starting:'正在连接转写服务…',listening:'正在识别，最终文字会追加到回答框',completed:'转写已结束',interrupted:'转写中断，最终文字已保留',denied:'转写权限被拒绝',no_speech:'未获得最终识别结果'}
const errors:Record<string,string>={permission_denied:'麦克风授权被拒绝',permission_timeout:'等待麦克风授权超时',capture_unavailable:'录音设备或浏览器录音不可用',recording_error:'录音过程发生错误',size_limit:'达到单段容量上限',duration_limit:'达到10分钟录音上限',stop_timeout:'录音停止超时',device_disconnected:'麦克风已断开',no_samples:'没有采集到音频'}
function onPlay(event:Event){if(props.busy){(event.target as HTMLAudioElement).pause();return};document.querySelectorAll<HTMLAudioElement>('.interview-audio-panel audio').forEach(a=>{if(a!==event.target)a.pause()});emit('play')}
</script>
<style scoped>
.interview-audio-panel{margin-block:1.2rem;padding:clamp(16px,3vw,26px);border:1px solid var(--border-default);border-radius:18px;background:var(--bg-elevated);color:var(--text-primary,#173052);font-size:1rem;line-height:1.65;overflow-wrap:anywhere}.interview-audio-panel header,.audio-take-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.interview-audio-panel h3{font-size:1.4rem;margin:0}.interview-audio-panel header p{margin:0}.audio-actions{display:flex;flex-wrap:wrap;align-items:center;gap:10px}.audio-actions button,.audio-asr button{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--border-strong);border-radius:10px;padding:10px 16px;background:var(--bg-surface);color:inherit;font:inherit;cursor:pointer}.interview-audio-panel button:disabled{opacity:.55;cursor:not-allowed}.audio-asr{margin-top:18px}.audio-asr summary{font-weight:650;cursor:pointer}.audio-asr label{display:block;margin-block:12px}.audio-takes{padding:0;list-style:none}.audio-takes li{border-top:1px solid var(--border-subtle);padding-block:18px}.audio-takes audio{display:block;width:100%;margin-top:14px}.audio-take-heading{flex-wrap:wrap}
</style>
