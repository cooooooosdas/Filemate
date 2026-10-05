<template>
  <div class="digital-human">
    <header class="page-intro">
      <div><span class="eyebrow">FILEMATE · VOICE STUDIO</span><h1>让学习，有声可循。</h1><p>把已保存的 AI 回答交给校园导师，也可以写下你想听的讲解。播报时不向 FileMate 后端发送讲解正文；浏览器声线是否联网由设备环境决定。</p></div>
      <router-link to="/ai-tools">返回学习工作区 <el-icon><ArrowRight /></el-icon></router-link>
    </header>

    <div class="studio-grid">
      <section class="script-panel" aria-label="讲解稿与播放控制">
        <div class="section-head"><div><span class="section-index">01 / 讲解稿</span><h2>今天想听什么？</h2></div><span class="length-count">{{ Array.from(text).length }} / 5000 字</span></div>
        <p v-if="sourceLabel" class="source-tag"><el-icon><Document /></el-icon>{{ sourceLabel }}</p>
        <label class="script-label" for="lecture-text">讲解内容</label>
        <textarea id="lecture-text" v-model="text" maxlength="5000" placeholder="在学习工作区点击“让 AI 导师讲解”，或在这里输入一段文字。" :disabled="loading" @input="markManual" />
        <div class="script-hint"><span>支持中文长文本；500 字会自动分段朗读。</span><button type="button" :disabled="loading || !text" @click="clearText">清空</button></div>

        <div class="control-divider" />
        <div class="section-head compact"><div><span class="section-index">02 / 播放</span><h2>把内容说出来</h2></div><span class="state-badge" :data-state="state">{{ stateLabel }}</span></div>
        <div v-if="error" class="error-box" role="alert">{{ error }} <button type="button" :disabled="loading || state === 'starting'" @click="retry">重试</button></div>
        <p v-if="notice" class="notice" role="status">{{ notice }} <button v-if="lastDeleted" type="button" @click="undoDelete">撤销删除</button></p>
        <p v-if="Object.keys(pendingFinishes).length" class="notice" role="status">播放状态未能同步到播报记录。<button type="button" :disabled="syncing" @click="retrySync">重试同步</button></p>
        <div class="transport">
          <button class="play-button" :disabled="loading || state === 'starting' || !text.trim()" @click="state === 'paused' ? resume() : play()"><el-icon><VideoPlay /></el-icon>{{ state === 'paused' ? '继续' : state === 'playing' ? '重新播放' : '开始讲解' }}</button>
          <button :disabled="state !== 'playing'" @click="pause"><el-icon><VideoPause /></el-icon>暂停</button>
          <button :disabled="!text.trim() || loading" @click="replay"><el-icon><RefreshRight /></el-icon>重播</button>
          <button :disabled="!active" @click="stop"><el-icon><Close /></el-icon>停止</button>
        </div>
        <p class="notice">{{ voiceBoundary }}</p>
        <div class="progress-track" role="progressbar" :aria-valuenow="progress" aria-valuemin="0" aria-valuemax="100" aria-label="讲解进度"><span :style="{ width: `${progress}%` }" /></div>
        <div class="settings-grid">
          <label>语速 <strong>{{ rate.toFixed(1) }}×</strong><input v-model.number="rate" type="range" min="0.7" max="1.5" step="0.1" @change="restartIfActive" /></label>
          <label>音量 <strong>{{ Math.round(volume * 100) }}%</strong><input v-model.number="volume" type="range" min="0" max="1" step="0.1" @change="restartIfActive" /></label>
          <label class="select-setting">声音<select v-model="voiceId" aria-label="声音" @change="restartIfActive"><option value="default">设备默认中文声线</option><option v-for="voice in voices" :key="voice.voiceURI" :value="voice.voiceURI">{{ voice.name }} · {{ voice.lang }}</option></select></label>
          <label class="select-setting">形象<select v-model="avatarId" aria-label="形象"><option v-for="avatar in AVATARS" :key="avatar.avatarId" :value="avatar.avatarId">{{ avatar.avatarName }}</option></select></label>
        </div>
        <div class="privacy-note"><el-icon><Lock /></el-icon><span>FileMate 仅记录播报时间、字数、状态和形象/声线，不保存正文或音频；可删除单条记录。浏览器声线可能联网，请勿朗读敏感资料。</span></div>
      </section>

      <section ref="stage" class="mentor-stage" aria-label="数字人舞台">
        <div class="stage-top"><div><span class="section-index">03 / 数字人</span><h2>你的学习搭子</h2></div><span class="provider-chip"><span />{{ provider.available() ? '设备语音就绪' : '设备不支持语音' }}</span></div>
        <div class="stage-copy"><p>每次讲解，都按你的节奏来。</p><small>拖动右下角卡片，或把它收起，学习内容始终可见。</small></div>
        <div class="stage-watermark" aria-hidden="true">FM</div>
        <button v-if="collapsed" class="collapsed-mentor" @click="collapsed = false"><el-icon><Microphone /></el-icon>展开导师</button>
        <div v-else ref="mentorPanel" class="mentor-panel" :style="{ width: `${panelWidth}px`, transform: `translate(${offset.x}px, ${offset.y}px)` }">
          <div class="mentor-handle" @pointerdown="startDrag"><span class="drag-mark" aria-hidden="true">···</span><strong>{{ currentAvatar.avatarName }}</strong><span class="mentor-actions"><button type="button" title="缩小" aria-label="缩小数字人" @pointerdown.stop @click="panelWidth = Math.max(250, panelWidth - 40)"><el-icon><Minus /></el-icon></button><button type="button" title="放大" aria-label="放大数字人" @pointerdown.stop @click="panelWidth = Math.min(390, panelWidth + 40)"><el-icon><Plus /></el-icon></button><button type="button" title="收起" aria-label="收起数字人" @pointerdown.stop @click="collapsed = true"><el-icon><ArrowDown /></el-icon></button></span></div>
          <div class="mentor-art" :class="[currentAvatar.style, { talking: state === 'playing', muted: state !== 'playing' }]">
            <div v-if="currentAvatar.style === 'portrait'" class="portrait-image" :class="{ speaking: mouthOpen }" :style="{ backgroundImage: `url(${currentAvatar.image})` }" role="img" aria-label="FileMate 近景导师" />
            <div v-else class="campus-image"><img :src="currentAvatar.image" alt="FileMate 校园导师" /><span class="mouth-cover" :class="{ open: mouthOpen }" aria-hidden="true" /></div>
            <div v-if="state === 'playing'" class="voice-bars" aria-hidden="true"><i /><i /><i /><i /><i /></div>
          </div>
          <div class="mentor-caption"><span>{{ stateLabel }}</span><p v-if="subtitles && text">{{ visibleSubtitle }}</p><p v-else-if="!subtitles">字幕已关闭</p><p v-else>输入讲解内容，导师就会为你读出来。</p></div>
          <div class="mentor-footer"><label><input v-model="subtitles" type="checkbox" />显示字幕</label><button type="button" @click="toggleFullscreen"><el-icon><FullScreen /></el-icon>{{ fullscreen ? '退出全屏' : '全屏' }}</button></div>
        </div>
      </section>
    </div>

    <section class="history-panel" aria-label="最近的播报记录"><div class="section-head"><div><span class="section-index">04 / 记录</span><h2>最近讲过的内容</h2></div><button type="button" @click="loadHistory">刷新记录</button></div><p v-if="historyError" role="alert" class="error-text">{{ historyError }}</p><p v-else-if="!history.length" class="empty-history">还没有播报记录。开始一次讲解后，元数据会出现在这里。</p><ul v-else><li v-for="item in history" :key="item.playback_id"><span><strong>{{ item.text_length }} 字 · {{ item.avatar_id === 'filemate-campus' ? '校园导师' : '近景导师' }}</strong><small>{{ formatTime(item.created_at) }} · {{ playbackStatus(item.status) }}</small></span><button type="button" :aria-label="`删除 ${formatTime(item.created_at)} 的播报记录`" @click="removeHistory(item.playback_id)">删除记录</button></li></ul></section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowDown, ArrowRight, Close, Document, FullScreen, Lock, Microphone, Minus, Plus, RefreshRight, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import { AVATARS } from '../digital-human/avatars'
import { BrowserSpeechProvider } from '../digital-human/provider'
import { createDigitalHumanPlayback, deleteDigitalHumanPlayback, finishDigitalHumanPlayback, getAIContext, listDigitalHumanPlaybacks, restoreDigitalHumanPlayback, type DigitalHumanPlayback } from '../services/api'

type PlaybackState = 'idle' | 'starting' | 'playing' | 'paused' | 'completed' | 'stopped' | 'failed'
const route = useRoute()
const provider = new BrowserSpeechProvider()
const text = ref('')
const loading = ref(false)
const state = ref<PlaybackState>('idle')
const error = ref('')
const notice = ref('')
const historyError = ref('')
const history = ref<DigitalHumanPlayback[]>([])
const lastDeleted = ref<string | null>(null)
const avatarId = ref(AVATARS[1].avatarId)
const currentAvatar = computed(() => AVATARS.find(item => item.avatarId === avatarId.value) || AVATARS[0])
const voiceId = ref(AVATARS[1].voiceId)
const voices = ref<SpeechSynthesisVoice[]>([])
const voiceBoundary = computed(() => {
  const selected = voices.value.find(voice => voice.voiceURI === voiceId.value)
  return selected?.localService === true ? '当前声线标记为设备本地服务；FileMate不上传讲解正文。' : selected?.localService === false ? '当前声线使用在线服务，开始讲解可能把正文发送给语音供应商。' : '默认声线的服务位置未确认，可能联网；请勿朗读敏感资料。'
})
const rate = ref(1)
const volume = ref(1)
const subtitles = ref(true)
const progress = ref(0)
const characterIndex = ref(0)
const spokenText = ref('')
const mouthOpen = ref(false)
const collapsed = ref(false)
const panelWidth = ref(290)
const offset = ref({ x: 0, y: 0 })
const stage = ref<HTMLElement | null>(null)
const mentorPanel = ref<HTMLElement | null>(null)
const fullscreen = ref(false)
const sourceLabel = ref('')
const sourceReference = ref<{ contextId: string; messageIndex: number; content: string } | null>(null)
const active = computed(() => ['starting', 'playing', 'paused'].includes(state.value))
const stateLabel = computed(() => ({ idle: '准备就绪', starting: '正在准备语音', playing: '正在讲解', paused: '已暂停', completed: '讲解完成', stopped: '已停止', failed: '讲解失败' }[state.value]))
const visibleSubtitle = computed(() => {
  const start = Math.max(0, characterIndex.value - 10)
  return (spokenText.value || text.value).slice(start, start + 48)
})
type FinishStatus = 'completed' | 'stopped' | 'failed'
const pendingFinishes = ref<Record<string, { status: FinishStatus; code: string }>>({})
const syncing = ref(false)
const errorSource = ref(false)
let playbackId: string | null = null
let operation = 0
let sourceOperation = 0
let historyOperation = 0
let disposed = false
let mouthTimer: number | undefined
let endDrag: (() => void) | undefined
let stageObserver: ResizeObserver | undefined

function refreshVoices(): void {
  voices.value = provider.voices().filter(item => item.lang.toLowerCase().startsWith('zh'))
  if (voiceId.value !== 'default' && !voices.value.some(item => item.voiceURI === voiceId.value)) voiceId.value = 'default'
}
function markManual(): void {
  if (active.value) stop()
  if (sourceReference.value && text.value !== sourceReference.value.content) { sourceReference.value = null; sourceLabel.value = '手动编辑的讲解稿' }
}
function clearText(): void { stop(); text.value = ''; spokenText.value = ''; sourceReference.value = null; sourceLabel.value = ''; progress.value = 0; error.value = '' }
function message(cause: unknown): string { return cause instanceof Error ? cause.message : '操作失败，请重试。' }
async function loadHistory(): Promise<void> {
  const current = ++historyOperation
  try {
    const items = await listDigitalHumanPlaybacks()
    if (disposed || current !== historyOperation) return
    history.value = items; historyError.value = ''
  } catch (cause) { if (!disposed && current === historyOperation) historyError.value = message(cause) }
}
async function finishRecord(id: string, status: FinishStatus, code = ''): Promise<void> {
  try {
    await finishDigitalHumanPlayback(id, status, code)
    if (disposed) return
    delete pendingFinishes.value[id]
    await loadHistory()
  } catch { if (!disposed) pendingFinishes.value[id] = { status, code } }
}
async function retrySync(): Promise<void> {
  if (syncing.value) return
  syncing.value = true
  try {
    for (const [id, result] of Object.entries(pendingFinishes.value)) await finishRecord(id, result.status, result.code)
  } finally { syncing.value = false }
}
async function finish(status: FinishStatus, code = ''): Promise<void> {
  const id = playbackId
  playbackId = null
  if (!id) return
  await finishRecord(id, status, code)
}
function stopMouth(): void { if (mouthTimer !== undefined) window.clearInterval(mouthTimer); mouthTimer = undefined; mouthOpen.value = false }
function startMouth(): void { stopMouth(); mouthTimer = window.setInterval(() => { mouthOpen.value = !mouthOpen.value }, 230) }
function stop(): Promise<void> {
  operation++
  provider.stop()
  stopMouth()
  spokenText.value = ''
  if (active.value) { state.value = 'stopped'; return finish('stopped') }
  return Promise.resolve()
}
async function play(): Promise<void> {
  if (loading.value || disposed) return
  const script = text.value.trim()
  if (!script) { error.value = '请先输入讲解文字。'; return }
  if (Array.from(script).length > 5000) { error.value = '讲解稿不能超过 5000 字，请先精简内容。'; return }
  if (!provider.available()) { error.value = '当前浏览器不支持语音合成，请使用最新版 Chrome 或 Edge。'; state.value = 'failed'; return }
  stop()
  const current = ++operation
  error.value = ''; errorSource.value = false; notice.value = ''; lastDeleted.value = null; state.value = 'starting'; progress.value = 0; characterIndex.value = 0; spokenText.value = script
  try {
    const reference = sourceReference.value
    const saved = await createDigitalHumanPlayback({
      text_length: Array.from(script).length, avatar_id: avatarId.value, voice_id: voiceId.value,
      provider: 'web_speech',
      ...(reference ? { context_id: reference.contextId, message_index: reference.messageIndex } : {}),
    })
    if (disposed || current !== operation) { void finishRecord(saved.playback_id, 'stopped'); return }
    playbackId = saved.playback_id
    void loadHistory()
  } catch (cause) {
    if (current !== operation) return
    state.value = 'failed'; error.value = `讲解记录未创建：${message(cause)}。请检查服务连接并重试。`; return
  }
  provider.speak(script, { voiceId: voiceId.value, rate: rate.value, volume: volume.value }, {
    onStart: () => { if (current !== operation || state.value === 'paused') return; state.value = 'playing'; startMouth() },
    onBoundary: index => { if (current !== operation) return; characterIndex.value = index; progress.value = Math.round(index / script.length * 100); mouthOpen.value = true },
    onEnd: () => { if (current !== operation) return; stopMouth(); state.value = 'completed'; progress.value = 100; void finish('completed') },
    onError: reason => { if (current !== operation) return; stopMouth(); state.value = 'failed'; error.value = reason; void finish('failed', 'speech_error') },
  })
}
function pause(): void { if (state.value !== 'playing') return; provider.pause(); if (state.value === 'playing') { stopMouth(); state.value = 'paused' } }
function resume(): void { if (state.value !== 'paused') return; provider.resume(); if (state.value === 'paused') { state.value = 'playing'; startMouth() } }
function replay(): void { if (text.value.trim()) void play() }
function restartIfActive(): void { if (active.value) void play() }
async function removeHistory(id: string): Promise<void> {
  if (id === playbackId) await stop()
  try { if (await deleteDigitalHumanPlayback(id)) { delete pendingFinishes.value[id]; lastDeleted.value = id; notice.value = '记录已移除。'; await loadHistory() } }
  catch (cause) { historyError.value = message(cause) }
}
async function undoDelete(): Promise<void> {
  const id = lastDeleted.value
  if (!id) return
  try { await restoreDigitalHumanPlayback(id); lastDeleted.value = null; notice.value = '记录已恢复。'; await loadHistory() }
  catch (cause) { historyError.value = message(cause) }
}
function playbackStatus(value: string): string { return ({ started: '播放中或未正常结束', completed: '已完成', stopped: '已停止', failed: '失败' } as Record<string, string>)[value] || value }
function formatTime(value: string): string { return new Date(value).toLocaleString('zh-CN') }
async function toggleFullscreen(): Promise<void> {
  try { if (document.fullscreenElement) await document.exitFullscreen(); else await stage.value?.requestFullscreen() }
  catch { notice.value = '浏览器未允许全屏，请使用普通视图。' }
}
function syncFullscreen(): void { fullscreen.value = document.fullscreenElement === stage.value }
function startDrag(event: PointerEvent): void {
  if (event.button !== 0 || !stage.value || !mentorPanel.value) return
  const panel = mentorPanel.value.getBoundingClientRect()
  const bounds = stage.value.getBoundingClientRect()
  const initial = { x: event.clientX, y: event.clientY, left: panel.left, top: panel.top, ox: offset.value.x, oy: offset.value.y }
  endDrag?.()
  const move = (next: PointerEvent): void => {
    const dx = Math.min(bounds.right - panel.width - initial.left, Math.max(bounds.left - initial.left, next.clientX - initial.x))
    const dy = Math.min(bounds.bottom - panel.height - initial.top, Math.max(bounds.top - initial.top, next.clientY - initial.y))
    offset.value = { x: initial.ox + dx, y: initial.oy + dy }
  }
  const end = (): void => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', end); window.removeEventListener('pointercancel', end); endDrag = undefined }
  endDrag = end
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', end, { once: true })
  window.addEventListener('pointercancel', end, { once: true })
}
async function retry(): Promise<void> {
  if (errorSource.value) await loadSelectedAnswer()
  else await play()
}
async function loadSelectedAnswer(): Promise<void> {
  stop()
  const current = ++sourceOperation
  text.value = ''; sourceReference.value = null; sourceLabel.value = ''; error.value = ''; progress.value = 0; state.value = 'idle'; loading.value = false
  const ctx = typeof route.query.ctx === 'string' ? route.query.ctx : ''
  if (!ctx) return
  const rawIndex = route.query.message
  const index = typeof rawIndex === 'string' && /^(0|[1-9]\d*)$/.test(rawIndex) ? Number(rawIndex) : NaN
  if (!Number.isSafeInteger(index)) { errorSource.value = true; error.value = '讲解链接的消息序号无效，请从学习工作区重新打开。'; return }
  loading.value = true
  try {
    const context = await getAIContext(ctx)
    if (disposed || current !== sourceOperation) return
    const item = context.chat_history[index]
    if (!item || item.role !== 'assistant') throw new Error('这条 AI 回答不存在或已删除。')
    text.value = item.content.trim()
    sourceReference.value = { contextId: ctx, messageIndex: index, content: text.value }
    sourceLabel.value = '来自已保存的学习对话 · 第 ' + (index + 1) + ' 条消息'
    errorSource.value = false
  } catch (cause) { if (!disposed && current === sourceOperation) { errorSource.value = true; error.value = message(cause) } }
  finally { if (!disposed && current === sourceOperation) loading.value = false }
}
onMounted(() => {
  refreshVoices()
  if (provider.available()) window.speechSynthesis.addEventListener('voiceschanged', refreshVoices)
  document.addEventListener('fullscreenchange', syncFullscreen)
  void loadHistory()
  stageObserver = new ResizeObserver(() => { endDrag?.(); offset.value = { x: 0, y: 0 } })
  if (stage.value) stageObserver.observe(stage.value)
})
onUnmounted(() => {
  disposed = true
  sourceOperation++
  stop()
  endDrag?.()
  stageObserver?.disconnect()
  if (provider.available()) window.speechSynthesis.removeEventListener('voiceschanged', refreshVoices)
  document.removeEventListener('fullscreenchange', syncFullscreen)
})
watch([avatarId, panelWidth], () => { endDrag?.(); offset.value = { x: 0, y: 0 } })
watch(() => [route.query.ctx, route.query.message], () => { void loadSelectedAnswer() }, { immediate: true })
</script>

<style scoped>
.digital-human .mentor-actions button{min-width:44px;min-height:44px}.digital-human .mentor-footer button,.digital-human .error-box button{min-height:44px}
.digital-human{max-width:1440px;margin:auto;padding:12px 14px 40px;color:var(--text-primary)}.page-intro{display:flex;justify-content:space-between;align-items:end;gap:24px;padding:12px 0 26px}.eyebrow,.section-index{font:600 11px ui-monospace,Consolas,monospace;letter-spacing:.1em;color:var(--accent)}.page-intro h1{font-size:clamp(28px,3vw,42px);line-height:1.2;letter-spacing:-.03em;margin:13px 0}.page-intro p{max-width:640px;color:var(--text-secondary);line-height:1.8;margin:0}.page-intro a{color:var(--accent);text-decoration:none;white-space:nowrap;display:inline-flex;align-items:center;gap:8px;min-height:44px}.studio-grid{display:grid;grid-template-columns:minmax(0,7fr) minmax(340px,5fr);gap:18px;align-items:stretch}.script-panel,.mentor-stage,.history-panel{border:1px solid var(--border-subtle);background:#fff;border-radius:14px}.script-panel{padding:26px;min-width:0}.section-head{display:flex;align-items:end;justify-content:space-between;gap:12px}.section-head h2,.stage-top h2{font-size:21px;margin:8px 0 0;letter-spacing:-.02em}.length-count{font-size:14px;color:var(--text-muted)}.source-tag{display:inline-flex;gap:6px;align-items:center;color:var(--accent);background:var(--accent-soft);border-radius:8px;padding:7px 9px;font-size:14px}.script-label{display:block;margin:24px 0 8px;font-size:13px;font-weight:600}.script-panel textarea{width:100%;height:258px;box-sizing:border-box;resize:vertical;border:1px solid var(--border-subtle);background:var(--bg-elevated);border-radius:10px;padding:16px;color:var(--text-primary);font:inherit;line-height:1.8}.script-panel textarea::placeholder{color:var(--text-muted)}.script-hint{display:flex;justify-content:space-between;align-items:center;gap:12px;color:var(--text-muted);font-size:14px;margin-top:8px}.control-divider{border-top:1px solid var(--border-subtle);margin:23px 0}.compact h2{font-size:18px}.state-badge{background:var(--accent-soft);color:var(--accent);border-radius:8px;padding:7px 9px;font-size:14px}.state-badge[data-state=failed]{color:#b44b4b;background:#fff3f2}.transport{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}.digital-human button{font:inherit;cursor:pointer;min-height:44px;border:1px solid var(--border-subtle);background:#fff;border-radius:10px;padding:8px 12px;color:var(--text-primary)}.digital-human button:disabled{opacity:.48;cursor:not-allowed}.digital-human button:focus-visible,.digital-human a:focus-visible,.digital-human input:focus-visible,.digital-human select:focus-visible,.digital-human textarea:focus-visible{outline:2px solid var(--accent);outline-offset:2px}.transport button{display:inline-flex;align-items:center;gap:6px}.transport .play-button{background:var(--accent);border-color:var(--accent);color:white}.progress-track{height:6px;background:var(--accent-soft);border-radius:4px;overflow:hidden}.progress-track span{display:block;height:100%;background:var(--accent);transition:width .2s}.settings-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:22px}.settings-grid label{font-size:14px;color:var(--text-secondary);min-width:0}.settings-grid strong{float:right;color:var(--text-primary)}.settings-grid input{width:100%;margin:13px 0 0;accent-color:var(--accent)}.settings-grid select{display:block;margin-top:9px;width:100%;min-height:44px;border:1px solid var(--border-subtle);border-radius:10px;background:#fff;color:var(--text-primary);padding:0 9px;font:inherit}.privacy-note{display:flex;gap:8px;align-items:start;background:var(--bg-elevated);border-radius:10px;padding:12px;margin-top:22px;color:var(--text-secondary);font-size:14px;line-height:1.6}.privacy-note .el-icon{flex:none;margin-top:2px}.error-box{margin-top:14px;background:#fff3f2;color:#9f3939;border:1px solid #f0d4d0;border-radius:9px;padding:10px;font-size:13px}.error-box button{margin-left:8px;color:#9f3939;min-height:34px}.notice,.error-text{font-size:14px;color:#9a651d}.mentor-stage{min-height:655px;position:relative;overflow:hidden;background:#e3edff;padding:24px;box-sizing:border-box}.stage-top{position:relative;z-index:1;display:flex;justify-content:space-between;align-items:start;gap:12px}.stage-top h2{font-size:19px}.provider-chip{display:inline-flex;align-items:center;gap:7px;background:#fff;padding:8px;border-radius:8px;font-size:14px;color:var(--text-secondary);white-space:nowrap}.provider-chip span{width:7px;height:7px;border-radius:50%;background:var(--accent)}.stage-copy{position:relative;z-index:1;margin-top:22px;max-width:280px}.stage-copy p{font-size:16px;font-weight:600;margin:0 0 8px}.stage-copy small{font-size:14px;color:var(--text-secondary);line-height:1.7}.stage-watermark{position:absolute;left:-40px;bottom:40px;font-size:230px;letter-spacing:-.1em;font-weight:700;color:#607ca7;line-height:1;pointer-events:none}.mentor-panel{position:absolute;right:22px;bottom:22px;z-index:2;border:1px solid var(--border-subtle);border-radius:14px;background:white;box-shadow:0 12px 30px rgb(21 38 74 / .13);overflow:hidden;touch-action:none}.mentor-handle{min-height:46px;display:flex;align-items:center;gap:8px;padding:0 10px;background:var(--bg-elevated);cursor:grab;user-select:none}.drag-mark{font-size:24px;line-height:0;color:var(--text-muted);transform:rotate(90deg)}.mentor-handle strong{font-size:14px;flex:1}.mentor-actions{display:flex;gap:1px}.mentor-actions button{border:0;background:transparent;min-width:32px;min-height:36px;padding:4px}.mentor-art{position:relative;height:270px;display:flex;align-items:end;justify-content:center;overflow:hidden;background:var(--accent-soft)}.mentor-art.campus{background:linear-gradient(#e3edff,#d4e1fa)}.campus-image{width:165px;height:270px;position:relative}.campus-image img{width:100%;height:100%;object-fit:contain}.mouth-cover{position:absolute;left:61.3%;top:18.1%;width:9%;height:2.6%;background:#e9a8a2;border-bottom:2px solid #874348;border-radius:60% 60% 45% 45%;transform:rotate(-3deg)}.mouth-cover.open{height:3.5%;border-radius:50%;background:#9b5052;border:2px solid #a66368}.mentor-art.portrait{background:#e3edff}.portrait-image{width:200px;height:240px;background-repeat:no-repeat;background-size:800px 600px;background-position:0 -55px}.portrait-image.speaking{background-position:-200px -55px}.voice-bars{position:absolute;right:18px;bottom:17px;display:flex;align-items:end;gap:3px;height:24px}.voice-bars i{width:3px;height:10px;background:var(--accent);border-radius:3px;animation:voice 620ms ease-in-out infinite alternate}.voice-bars i:nth-child(2),.voice-bars i:nth-child(4){animation-delay:210ms}.voice-bars i:nth-child(3){animation-delay:410ms}@keyframes voice{to{height:24px}}.mentor-caption{border-top:1px solid var(--border-subtle);padding:12px 14px;min-height:80px}.mentor-caption span{font-size:14px;color:var(--accent);font-weight:600}.mentor-caption p{font-size:14px;line-height:1.5;color:var(--text-secondary);margin:8px 0 0;max-height:50px;overflow:hidden}.mentor-footer{display:flex;justify-content:space-between;align-items:center;padding:0 12px 10px;gap:8px}.mentor-footer label{font-size:14px;color:var(--text-secondary);display:flex;align-items:center;gap:5px}.mentor-footer input{accent-color:var(--accent)}.mentor-footer button{display:flex;align-items:center;gap:4px;min-height:34px;font-size:14px;padding:4px 7px}.collapsed-mentor{position:absolute;right:22px;bottom:22px;z-index:2;display:flex;align-items:center;gap:6px;color:#fff!important;background:var(--accent)!important;border-color:var(--accent)!important}.history-panel{margin-top:18px;padding:22px 26px}.history-panel .section-head h2{font-size:18px}.history-panel ul{list-style:none;padding:0;margin:15px 0 0}.history-panel li{display:flex;justify-content:space-between;align-items:center;border-top:1px solid var(--border-subtle);padding:8px 0;gap:12px}.history-panel li span{display:flex;flex-direction:column;gap:4px}.history-panel li strong{font-size:13px}.history-panel li small,.empty-history{font-size:14px;color:var(--text-muted)}.history-panel li button{font-size:14px;color:#b44b4b}.mentor-stage:fullscreen{width:100vw;height:100vh}.mentor-stage:fullscreen .mentor-panel{right:5vw;bottom:5vh}@media(max-width:1000px){.studio-grid{grid-template-columns:1fr}.mentor-stage{min-height:560px}.page-intro{align-items:start}}@media(max-width:620px){.digital-human{padding:8px 0 28px}.page-intro{display:block;padding:12px 4px 20px}.page-intro a{margin-top:10px}.script-panel{padding:20px 16px}.mentor-stage{min-height:530px;padding:18px}.stage-copy{max-width:240px}.mentor-panel{right:12px;bottom:12px;max-width:calc(100% - 24px)}.settings-grid{grid-template-columns:1fr}.history-panel{padding:18px 16px}.provider-chip{font-size:10px}}@media(prefers-reduced-motion:reduce){.voice-bars i{animation:none}.progress-track span{transition:none}}
</style>
