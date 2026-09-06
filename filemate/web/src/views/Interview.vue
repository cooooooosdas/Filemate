<template>
  <div class="interview-page">
    <header class="page-head">
      <div>
        <h1>模拟面试训练</h1>
        <p>真实问题、即时追问、分项评分，把每一次回答变成可复盘的数据。</p>
      </div>
      <span class="status-pill" aria-live="polite"><i></i>{{ session?.status === 'completed' ? '本轮已完成' : session ? '面试进行中' : '准备就绪' }}</span>
    </header>

    <section v-if="!session" class="resume-panel" aria-labelledby="resume-title">
      <div class="resume-heading"><div><h2 id="resume-title">接着上次练</h2><p>已提交的回答会保留；未提交文字和本地录像不会在刷新后恢复。</p></div><button class="ghost" :disabled="historyLoading || loading" @click="loadRecent">刷新记录</button></div>
      <p v-if="historyLoading" role="status">正在读取练习记录…</p>
      <DataState v-else-if="historyError" :error="historyError" @retry="loadRecent" />
      <div v-else-if="recentInterviews.length" class="resume-list">
        <button v-for="item in recentInterviews" :key="item.interview_id" class="resume-item" :disabled="loading" @click="restoreInterview(item.interview_id)">
          <span><b>{{ item.target_role }}</b><small>{{ item.scenario }} · 已答 {{ item.current_index }} 题</small></span>
          <span class="resume-action">{{ item.status === 'completed' ? '回看回答' : '继续练习' }} →</span>
        </button>
      </div>
      <p v-else class="resume-empty">还没有练习记录，从下方创建第一场面试。</p>
      <p v-if="loading" role="status">正在准备面试…</p>
      <DataState v-if="resumeError" :error="resumeError" @retry="restoreInterview(requestedInterviewId)" />
    </section>

    <section v-if="!session" class="setup-card">
      <div class="setup-copy">
        <span>创建一场训练</span>
        <h2>选择你要训练的真实场景</h2>
        <p>结构化提问结合浏览器语音能力，无需额外安装软件；也可以全程使用文字回答。</p>
      </div>
      <div class="form-grid">
        <label>目标岗位或方向<input v-model="form.targetRole" name="target_role" autocomplete="off" placeholder="例如：Java 后端开发 / 软件杯答辩" /></label>
        <label>面试场景<select v-model="form.scenario" name="interview_scenario"><option>求职面试</option><option>竞赛答辩</option><option>保研复试</option></select></label>
        <label>难度<select v-model="form.difficulty" name="interview_difficulty"><option>入门</option><option>标准</option><option>压力面</option></select></label>
        <label class="source-field">面试依据（可选）<select v-model="form.sourceId" name="interview_source"><option value="">不使用资料，按题库训练</option><option v-for="source in knowledgeSources" :key="source.source_id" :value="source.source_id">{{ source.original_name }}</option></select><small>主动选择后才会使用；授权未确认时只用资料名在本地组织问题。</small></label>
      </div>
      <button class="primary" :disabled="loading || !form.targetRole.trim()" @click="begin">{{ loading ? '正在创建…' : '开始模拟面试' }}</button>
      <DataState v-if="error" :error="error" @retry="begin" />
    </section>

    <template v-else>
      <section class="studio">
        <div class="interviewer-panel">
          <div class="avatar-stage" :class="{ speaking }">
            <div class="pulse pulse-one" aria-hidden="true"></div><div class="pulse pulse-two" aria-hidden="true"></div>
            <div class="avatar-face"><img :src="mascotUrl" alt="FileMate 形象伙伴" /></div>
            <div class="voice-bars" aria-hidden="true"><i v-for="n in 7" :key="n"></i></div>
          </div>
          <div><p class="role">FileMate 面试伙伴</p><p class="online"><i></i>在线 · 中文普通话</p></div>
          <button class="ghost" :disabled="!session.current_question" @click="speakQuestion">重新播报问题</button>
          <div class="camera-dock" :class="{ active: cameraActive }">
            <div class="camera-preview">
              <video ref="cameraVideo" v-show="cameraActive" autoplay muted playsinline />
              <div v-if="!cameraActive" class="camera-placeholder">
                <span>你的面试画面</span>
                <small>开启后仅在本机浏览器预览</small>
              </div>
            </div>
            <button type="button" class="camera-toggle" @click="toggleCamera">
              {{ cameraActive ? '关闭摄像头' : '开启摄像头' }}
            </button>
            <button
              type="button"
              class="record-toggle"
              :class="{ recording: videoRecording }"
              :disabled="!cameraActive || !recordingSupported"
              @click="toggleVideoRecording"
            >
              {{ videoRecording ? `停止本地录像 · ${videoRecordingDuration}s` : '开始本地录像（含声音）' }}
            </button>
            <small v-if="cameraError" class="camera-error">{{ cameraError }}</small>
            <small v-else-if="videoRecording">正在浏览器内存录制{{ recordingHasAudio ? '画面与声音' : '静音画面' }}，不会上传</small>
            <small v-else>预览默认不录像；本地录像需单独授权麦克风，刷新后清除</small>
          </div>
        </div>

        <div class="conversation-panel">
          <div class="progress-row"><span>第 {{ Math.min(session.current_index + 1, session.questions.length) }} / {{ session.questions.length }} 题</span><strong>{{ displayScore(session.overall_score) }}</strong></div>
          <div class="progress"><i :style="{ width: `${session.current_index / session.questions.length * 100}%` }"></i></div>

          <div v-if="session.status === 'active'" class="question-block">
            <p>面试官提问</p>
            <span v-if="session.source_context?.source_name" class="source-evidence">依据：{{ session.source_context.source_name }} · {{ session.source_context.mode === 'authorized_excerpt' ? '已授权片段' : '仅本地资料名' }}</span>
            <h2>{{ session.current_question }}</h2>
            <textarea v-model="answer" name="interview_answer" autocomplete="off" aria-label="当前面试回答" rows="7" placeholder="建议用“情境—任务—行动—结果”结构回答…"></textarea>
            <div class="answer-actions">
              <button class="voice" :class="{ recording }" @click="toggleRecording">{{ recording ? '停止录音' : '语音回答' }}</button>
              <span>{{ answer.length }} 字</span>
              <button class="primary" :disabled="loading || videoRecording || answer.trim().length < 4" @click="submit">{{ loading ? '评分中…' : videoRecording ? '先停止本地录像' : '提交并进入下一题' }}</button>
            </div>
            <div v-if="recording || fluencyMetrics" class="fluency-strip" aria-live="polite">
              <span><b>{{ recordingDuration }}</b> 秒回答时长</span>
              <span><b>{{ liveCharsPerMinute }}</b> 字/分钟</span>
              <span><b>{{ fillerCount }}</b> 个口头语</span>
              <span><b>{{ longPauseCount }}</b> 次较长停顿</span>
              <small>仅语音回答生成流畅度参考；有内容评估时计入总分的 15%</small>
            </div>
            <div v-if="fluencyMarkers.length" class="live-timeline" aria-label="当前回答表达时间轴">
              <div class="timeline-track"><i v-for="marker in fluencyMarkers" :key="`${marker.kind}-${marker.second}`" :class="marker.kind" :style="{ left: markerPosition(marker.second, recordingDuration) }" /></div>
              <p><span>表达时间轴</span><b>{{ fluencyMarkers.length }} 个可复盘位置</b></p>
            </div>
          </div>

          <div v-else class="completion">
            <span class="score-ring" :class="{ unassessed: session.overall_score == null }">{{ session.overall_score == null ? '已记录' : session.overall_score.toFixed(0) }}</span>
            <div><p>本轮面试完成</p><h2>{{ scoreLabel }}</h2><button class="primary" @click="reset">再练一次</button></div>
          </div>
        </div>
      </section>

      <CompanionCard
        v-if="session.status === 'completed'"
        class="completion-companion"
        :mood="completionCompanion.mood"
        :title="completionCompanion.title"
        :message="completionCompanion.message"
        :evidence="completionCompanion.evidence"
        route="/growth"
        action-label="查看成长证据"
      />

      <section v-if="session.latest_evaluation" class="evaluation">
        <div class="evaluation-head"><div><p class="eyebrow">{{ session.latest_evaluation.scoring_mode === 'llm' ? '模型评估 · 仅供训练参考' : '本地练习 · 内容待评估' }}</p><h2>{{ session.latest_evaluation.feedback }}</h2></div><strong>{{ displayScore(session.latest_evaluation.score) }}</strong></div>
        <div class="dimension-grid"><div v-for="(score, name) in session.latest_evaluation.dimensions" :key="name"><span>{{ name }}</span><b>{{ score.toFixed(0) }}</b><i><em :style="{ width: `${score}%` }"></em></i></div></div>
      </section>

      <section v-if="session.turns.length" class="review-list">
        <h2>回答记录</h2>
        <details v-for="(turn, index) in session.turns" :key="turn.turn_id" :open="index === session.turns.length - 1">
          <summary><span>Q{{ index + 1 }} · {{ turn.question }}</span><b>{{ displayScore(turn.score) }}</b></summary>
          <small>{{ turn.scoring_mode === 'llm' ? '模型评估 · 仅供训练参考' : turn.scoring_mode === 'local_fallback' ? '本地练习 · 不计入能力均分' : '历史评分来源未确认 · 不计入能力均分' }}</small>
          <p>{{ turn.answer }}</p><small>{{ turn.feedback }}</small>
          <div v-if="localRecordings[index]" class="local-replay">
            <div class="replay-head"><strong>本地录像回放</strong><span>仅保留在当前页面，未上传</span></div>
            <video :id="`interview-replay-${index}`" :src="localRecordings[index].url" controls playsinline />
            <div v-if="turn.fluency_metrics?.markers?.length" class="replay-timeline">
              <div class="timeline-track">
                <button v-for="marker in turn.fluency_metrics.markers" :key="`${marker.kind}-${marker.second}`" type="button" :class="marker.kind" :style="{ left: markerPosition(marker.second, localRecordings[index].duration) }" :aria-label="`${marker.label}，${marker.second.toFixed(1)} 秒`" @click="seekRecording(index, marker.second)" />
              </div>
              <div class="marker-list"><button v-for="marker in turn.fluency_metrics.markers" :key="`label-${marker.kind}-${marker.second}`" type="button" @click="seekRecording(index, marker.second)"><i :class="marker.kind" />{{ marker.second.toFixed(1) }}s · {{ marker.label }}</button></div>
            </div>
          </div>
          <div v-else-if="turn.fluency_metrics?.markers?.length" class="evidence-only-timeline">
            <strong>表达时间轴</strong><span>本轮未保存录像，时间点仍作为评分证据保留</span>
            <div class="marker-list"><span v-for="marker in turn.fluency_metrics.markers" :key="`${marker.kind}-${marker.second}`"><i :class="marker.kind" />{{ marker.second.toFixed(1) }}s · {{ marker.label }}</span></div>
          </div>
        </details>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  answerInterview,
  getKnowledgeSources,
  getInterview,
  getLearningAnalytics,
  startInterview,
  type InterviewFluencyMarker,
  type InterviewFluencyMetrics,
  type InterviewSession,
  type KnowledgeSource,
  type LearningAnalytics
} from '../services/api'
import CompanionCard from '../components/CompanionCard.vue'
import DataState from '../components/DataState.vue'
import { publishCompanionEvent, type CompanionMood } from '../composables/useCompanion'
import mascotUrl from '../assets/filemate-mascot.png'

const form = ref({ targetRole: '', scenario: '求职面试', difficulty: '标准', sourceId: '' })
const route = useRoute()
const router = useRouter()
const recentInterviews = ref<LearningAnalytics['recent_interviews']>([])
const historyLoading = ref(false)
const historyError = ref('')
const resumeError = ref('')
const requestedInterviewId = ref('')
let disposed = false
const knowledgeSources = ref<KnowledgeSource[]>([])
const session = ref<InterviewSession | null>(null)
const answer = ref('')
const loading = ref(false)
const error = ref('')
const speaking = ref(false)
const recording = ref(false)
const recordingDuration = ref(0)
const fillerCount = ref(0)
const longPauseCount = ref(0)
const fluencyMetrics = ref<InterviewFluencyMetrics | undefined>()
const cameraVideo = ref<HTMLVideoElement | null>(null)
const cameraActive = ref(false)
const cameraError = ref('')
let recognition: any = null
let recordingStartedAt = 0
let lastSpeechAt = 0
let recordingTimer: number | undefined
let cameraStream: MediaStream | null = null
let localRecordingStream: MediaStream | null = null
let mediaRecorder: MediaRecorder | null = null
let localVideoChunks: Blob[] = []
let videoRecordingStartedAt = 0
let videoRecordingTimer: number | undefined
let recordingQuestionIndex = -1
let discardPendingRecording = false

interface LocalRecording {
  url: string
  duration: number
  mimeType: string
  hasAudio: boolean
}

const recordingSupported = typeof MediaRecorder !== 'undefined'
const videoRecording = ref(false)
const videoRecordingDuration = ref(0)
const recordingHasAudio = ref(false)
const fluencyMarkers = ref<InterviewFluencyMarker[]>([])
const localRecordings = ref<Record<number, LocalRecording>>({})

const liveCharsPerMinute = computed(() => {
  if (!recordingDuration.value) return 0
  return Math.round(answer.value.replace(/\s+/g, '').length * 60 / recordingDuration.value)
})

const markerPosition = (second: number, duration: number) => {
  if (!duration) return '0%'
  return `${Math.max(0, Math.min(100, second / duration * 100))}%`
}

const displayScore = (value: number | null | undefined) => value == null ? '待评估' : `${value.toFixed(0)} 分`

const scoreLabel = computed(() => {
  const score = session.value?.overall_score
  if (score == null) return '回答已保存，先回看一题，再继续练习'
  return score >= 85 ? '表现出色，可以进入实战' : score >= 70 ? '基础扎实，继续优化表达' : '已发现提升空间，建议再练一轮'
})

const completionCompanion = computed((): {
  mood: CompanionMood
  title: string
  message: string
  evidence: string
} => {
  const score = session.value?.overall_score
  if (score == null) return {
    mood: 'happy',
    title: '又完成了一次练习',
    message: '内容质量尚未评估，可以对照资料回看自己的回答。',
    evidence: `依据：已记录 ${session.value?.turns.length || 0} 次回答`
  }
  if (score >= 85) return {
    mood: 'wink',
    title: '这轮表达已经具备实战说服力',
    message: '保持内容证据，再尝试压力面或更短的限时回答。',
    evidence: `依据：本轮面试均分 ${Math.round(score)} 分`
  }
  if (score >= 60) return {
    mood: 'focused',
    title: '基础已经站稳，下一轮重点打磨表达',
    message: '从回答记录中选择最低分问题，补上具体行动和量化结果。',
    evidence: `依据：本轮面试均分 ${Math.round(score)} 分`
  }
  return {
    mood: 'encouraging',
    title: '我已经帮你找到最值得重练的位置',
    message: '先复盘一题即可，不需要一次把所有问题都改完。',
    evidence: `依据：本轮面试均分 ${Math.round(score)} 分`
  }
})

const speakQuestion = () => {
  const text = session.value?.current_question
  if (!text || !('speechSynthesis' in window)) return
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = 'zh-CN'; utterance.rate = .95
  utterance.onstart = () => { speaking.value = true }
  utterance.onend = () => { speaking.value = false }
  window.speechSynthesis.speak(utterance)
}

const begin = async () => {
  loading.value = true
  error.value = ''
  try {
    const created = await startInterview(form.value.targetRole, form.value.scenario, form.value.difficulty, form.value.sourceId || undefined)
    if (disposed) return
    session.value = created
    resumeError.value = ''
    await router.replace({ query: { interview: created.interview_id } })
    speakQuestion()
  }
  catch (e: any) { error.value = e?.message || '创建失败'; ElMessage.error(error.value) }
  finally { loading.value = false }
}

const submit = async () => {
  if (!session.value) return
  loading.value = true
  try {
    session.value = await answerInterview(
      session.value.interview_id,
      answer.value,
      fluencyMetrics.value
    )
    const latestScore = session.value.latest_evaluation?.score
    publishCompanionEvent({
      mood: latestScore == null ? 'happy' : latestScore >= 85 ? 'wink' : latestScore >= 60 ? 'focused' : 'encouraging',
      title: latestScore == null ? '这一题的回答已保存' : latestScore >= 85 ? '这一题回答得很有力量' : latestScore >= 60 ? '思路已经清楚，再补一层证据' : '这一题值得慢下来重新组织',
      message: session.value.latest_evaluation?.feedback || '继续完成下一题，我会保留每轮证据。',
      evidence: latestScore == null ? '本地练习记录 · 内容质量待评估' : `依据：本题模型评分 ${Math.round(latestScore)} 分`,
      route: session.value.status === 'completed' ? '/growth' : '/interview',
      actionLabel: session.value.status === 'completed' ? '查看成长证据' : '继续面试'
    })
    answer.value = ''
    fluencyMetrics.value = undefined
    fluencyMarkers.value = []
    recordingDuration.value = 0
    fillerCount.value = 0
    longPauseCount.value = 0
    if (session.value.status === 'active') setTimeout(speakQuestion, 180)
  }
  catch (error: any) { ElMessage.error(error.message || '评分失败') }
  finally { loading.value = false }
}

const loadRecent = async () => {
  historyLoading.value = true
  historyError.value = ''
  try { recentInterviews.value = (await getLearningAnalytics()).recent_interviews }
  catch { historyError.value = '练习记录暂时未能加载，可以重试；仍可新建面试。' }
  finally { historyLoading.value = false }
}

const restoreInterview = async (interviewId: string) => {
  if (!interviewId || loading.value) return
  requestedInterviewId.value = interviewId
  loading.value = true
  resumeError.value = ''
  try {
    const restored = await getInterview(interviewId)
    if (disposed) return
    session.value = restored
    form.value = { targetRole: restored.target_role, scenario: restored.scenario, difficulty: restored.difficulty, sourceId: restored.source_context?.source_id || '' }
    answer.value = ''
    await router.replace({ query: { interview: restored.interview_id } })
  } catch { resumeError.value = '这场面试暂时无法恢复。请确认后端已启动，或从下方新建面试。' }
  finally { loading.value = false }
}

const finalizeFluency = () => {
  if (!recordingStartedAt) return
  recordingDuration.value = Math.max(1, Math.round((Date.now() - recordingStartedAt) / 1000))
  fluencyMetrics.value = {
    duration_seconds: recordingDuration.value,
    chars_per_minute: liveCharsPerMinute.value,
    filler_count: fillerCount.value,
    long_pause_count: longPauseCount.value,
    source: 'speech_recognition',
    markers: fluencyMarkers.value
  }
  recordingStartedAt = 0
  if (recordingTimer !== undefined) window.clearInterval(recordingTimer)
  recordingTimer = undefined
}

const toggleRecording = () => {
  if (recording.value) { recognition?.stop(); return }
  const Recognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!Recognition) { ElMessage.info('当前浏览器不支持语音识别，请使用文字回答'); return }
  recognition = new Recognition(); recognition.lang = 'zh-CN'; recognition.continuous = true; recognition.interimResults = true
  recognition.onstart = () => {
    recording.value = true
    recordingStartedAt = Date.now()
    lastSpeechAt = 0
    recordingDuration.value = 0
    fillerCount.value = 0
    longPauseCount.value = 0
    fluencyMarkers.value = []
    fluencyMetrics.value = undefined
    recordingTimer = window.setInterval(() => {
      recordingDuration.value = Math.max(1, Math.round((Date.now() - recordingStartedAt) / 1000))
    }, 500)
  }
  recognition.onend = () => { recording.value = false; finalizeFluency() }
  recognition.onerror = () => { recording.value = false; finalizeFluency(); ElMessage.warning('语音识别中断，请重试') }
  recognition.onresult = (event: any) => {
    const now = Date.now()
    const elapsed = Math.max(0, (now - recordingStartedAt) / 1000)
    if (lastSpeechAt && now - lastSpeechAt > 2500) {
      longPauseCount.value += 1
      fluencyMarkers.value.push({ second: elapsed, kind: 'long_pause', label: '较长停顿' })
    }
    lastSpeechAt = now
    answer.value = Array.from(event.results).map((result: any) => result[0].transcript).join('')
    const detectedFillers = answer.value.match(/嗯|呃|那个|就是说|然后呢|就是/g)?.length || 0
    if (detectedFillers > fillerCount.value) {
      for (let index = fillerCount.value; index < detectedFillers; index += 1) {
        fluencyMarkers.value.push({ second: elapsed, kind: 'filler', label: '出现口头语' })
      }
    }
    fillerCount.value = detectedFillers
  }
  recognition.start()
}

const startCamera = async () => {
  cameraError.value = ''
  if (!navigator.mediaDevices?.getUserMedia) {
    cameraError.value = '当前环境不支持摄像头预览'
    return
  }
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } },
      audio: false
    })
    cameraActive.value = true
    await nextTick()
    if (cameraVideo.value) cameraVideo.value.srcObject = cameraStream
  } catch {
    cameraError.value = '未获得摄像头权限，可继续使用文字或语音回答'
    cameraActive.value = false
  }
}

const stopCamera = () => {
  if (videoRecording.value) stopVideoRecording()
  cameraStream?.getTracks().forEach(track => track.stop())
  cameraStream = null
  cameraActive.value = false
  if (cameraVideo.value) cameraVideo.value.srcObject = null
}

const toggleCamera = () => { cameraActive.value ? stopCamera() : startCamera() }

const stopLocalRecordingTracks = () => {
  localRecordingStream?.getTracks().forEach(track => track.stop())
  localRecordingStream = null
  if (videoRecordingTimer !== undefined) window.clearInterval(videoRecordingTimer)
  videoRecordingTimer = undefined
}

const startVideoRecording = async () => {
  if (!cameraStream || !session.value || !recordingSupported) return
  cameraError.value = ''
  let microphoneStream: MediaStream | null = null
  try {
    microphoneStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
  } catch {
    ElMessage.warning('未获得麦克风权限，将只录制本地画面')
  }
  const videoTracks = cameraStream.getVideoTracks().map(track => track.clone())
  const audioTracks = microphoneStream?.getAudioTracks() || []
  localRecordingStream = new MediaStream([...videoTracks, ...audioTracks])
  recordingHasAudio.value = audioTracks.length > 0
  localVideoChunks = []
  recordingQuestionIndex = session.value.current_index
  discardPendingRecording = false
  const mimeType = ['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm']
    .find(type => MediaRecorder.isTypeSupported(type))
  mediaRecorder = mimeType
    ? new MediaRecorder(localRecordingStream, { mimeType })
    : new MediaRecorder(localRecordingStream)
  mediaRecorder.ondataavailable = event => {
    if (event.data.size > 0) localVideoChunks.push(event.data)
  }
  mediaRecorder.onerror = () => {
    videoRecording.value = false
    stopLocalRecordingTracks()
    ElMessage.error('本地录像中断，请重新开启')
  }
  mediaRecorder.onstop = () => {
    const duration = Math.max(1, Math.round((Date.now() - videoRecordingStartedAt) / 1000))
    if (!discardPendingRecording && localVideoChunks.length && recordingQuestionIndex >= 0) {
      const previous = localRecordings.value[recordingQuestionIndex]
      if (previous) URL.revokeObjectURL(previous.url)
      const blob = new Blob(localVideoChunks, { type: mediaRecorder?.mimeType || 'video/webm' })
      localRecordings.value = {
        ...localRecordings.value,
        [recordingQuestionIndex]: {
          url: URL.createObjectURL(blob),
          duration,
          mimeType: blob.type,
          hasAudio: recordingHasAudio.value
        }
      }
      ElMessage.success('本轮录像已保存在当前页面，可在回答记录中回放')
    }
    videoRecording.value = false
    stopLocalRecordingTracks()
    mediaRecorder = null
    localVideoChunks = []
  }
  videoRecordingStartedAt = Date.now()
  videoRecordingDuration.value = 0
  videoRecording.value = true
  mediaRecorder.start(500)
  videoRecordingTimer = window.setInterval(() => {
    videoRecordingDuration.value = Math.max(1, Math.round((Date.now() - videoRecordingStartedAt) / 1000))
  }, 500)
}

const stopVideoRecording = (discard = false) => {
  discardPendingRecording = discard
  if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop()
  else {
    videoRecording.value = false
    stopLocalRecordingTracks()
  }
}

const toggleVideoRecording = () => {
  if (videoRecording.value) stopVideoRecording()
  else void startVideoRecording()
}

const seekRecording = (index: number, second: number) => {
  const video = document.getElementById(`interview-replay-${index}`) as HTMLVideoElement | null
  if (!video) return
  video.currentTime = second
  void video.play()
}

const clearLocalRecordings = () => {
  Object.values(localRecordings.value).forEach(recording => URL.revokeObjectURL(recording.url))
  localRecordings.value = {}
}

const reset = () => {
  window.speechSynthesis?.cancel()
  recognition?.stop()
  stopVideoRecording(true)
  stopCamera()
  clearLocalRecordings()
  session.value = null
  answer.value = ''
  fluencyMarkers.value = []
  resumeError.value = ''
  void router.replace({ query: {} })
  void loadRecent()
}
onBeforeUnmount(() => {
  disposed = true
  recognition?.stop()
  stopVideoRecording(true)
  stopCamera()
  clearLocalRecordings()
  if (recordingTimer !== undefined) window.clearInterval(recordingTimer)
  window.speechSynthesis?.cancel()
})
onMounted(async () => {
  void loadRecent()
  if (typeof route.query.interview === 'string') void restoreInterview(route.query.interview)
  try { knowledgeSources.value = await getKnowledgeSources(100) }
  catch { knowledgeSources.value = [] }
})
</script>

<style scoped>
.interview-page{max-width:1180px;margin:0 auto;padding:28px;color:var(--text-primary)}.page-head{display:flex;justify-content:space-between;gap:24px;align-items:end;margin-bottom:26px}.eyebrow{margin:0;color:var(--accent);font-size:11px;font-weight:800;letter-spacing:.15em}.page-head h1{font-size:32px;margin:0 0 7px}.page-head p{margin:0;color:var(--text-secondary)}.status-pill{display:flex;align-items:center;gap:8px;padding:8px 12px;border:1px solid var(--accent-border);border-radius:999px;color:var(--accent);background:var(--accent-soft)}.status-pill i,.online i{width:7px;height:7px;border-radius:50%;background:#36a269}.setup-card,.studio,.evaluation,.review-list{background:var(--bg-surface);border:1px solid var(--border-subtle);border-radius:18px}.setup-card{padding:30px}.setup-copy span{color:var(--accent);font-size:12px;font-weight:700}.setup-copy h2{font-size:24px;margin:8px 0}.setup-copy p{color:var(--text-secondary)}.form-grid{display:grid;grid-template-columns:2fr 1fr 1fr;gap:14px;margin:26px 0}.form-grid label{font-size:13px;color:var(--text-secondary)}input,select,textarea{box-sizing:border-box;width:100%;margin-top:7px;padding:12px;border:1px solid var(--border-default);border-radius:10px;background:var(--bg-elevated);color:var(--text-primary);font:inherit}textarea{resize:vertical;line-height:1.7}.primary,.ghost,.voice{border:0;border-radius:10px;padding:11px 17px;cursor:pointer}.primary{background:var(--accent);color:white;font-weight:700}.primary:disabled{opacity:.45}.studio{display:grid;grid-template-columns:310px 1fr;overflow:hidden}.interviewer-panel{padding:30px;background:var(--sidebar-bg);text-align:center;border-right:1px solid var(--border-subtle)}.avatar-stage{position:relative;width:180px;height:180px;margin:12px auto 24px;display:grid;place-items:center}.avatar-face{position:relative;z-index:2;width:124px;height:124px;display:grid;place-items:center;overflow:hidden;border:4px solid rgba(255,255,255,.9);border-radius:50%;background:linear-gradient(145deg,var(--brand-blue-soft),#e7f6ee);box-shadow:0 16px 35px rgba(37,99,235,.18)}.avatar-face img{width:100%;height:100%;object-fit:cover;object-position:50% 22%;transform:scale(1.08)}.pulse{position:absolute;border:1px solid var(--brand-blue-border);border-radius:50%}.pulse-one{inset:12px}.pulse-two{inset:0}.speaking .pulse{animation:pulse 1.3s infinite}.voice-bars{position:absolute;bottom:1px;display:flex;gap:3px}.voice-bars i{width:3px;height:8px;background:var(--accent);border-radius:3px}.speaking .voice-bars i{animation:bars .7s infinite alternate}.voice-bars i:nth-child(2n){animation-delay:.2s}.role{font-weight:700}.online{font-size:12px;color:var(--text-secondary)}.online i{display:inline-block;margin-right:5px}.ghost{margin-top:18px;border:1px solid var(--accent-border);background:transparent;color:var(--accent)}.conversation-panel{padding:30px}.progress-row{display:flex;justify-content:space-between;color:var(--text-secondary);font-size:13px}.progress{height:5px;background:var(--bg-elevated);border-radius:5px;margin:10px 0 28px}.progress i{display:block;height:100%;background:var(--accent);border-radius:5px}.question-block>p{font-size:12px;color:var(--accent)}.question-block h2{font-size:22px;line-height:1.5}.answer-actions{display:flex;gap:12px;align-items:center;margin-top:12px}.answer-actions span{color:var(--text-muted);font-size:12px;margin-right:auto}.voice{border:1px solid var(--accent-border);color:var(--accent);background:var(--accent-soft)}.voice.recording{background:#fff0ec;color:#b44b34}.evaluation,.review-list{margin-top:18px;padding:24px}.evaluation-head{display:flex;justify-content:space-between;gap:20px}.evaluation-head h2{font-size:17px}.evaluation-head>strong{font-size:42px;color:var(--accent)}.dimension-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}.dimension-grid>div{display:grid;grid-template-columns:1fr auto;gap:8px}.dimension-grid i{grid-column:1/-1;height:5px;background:var(--bg-elevated);border-radius:5px}.dimension-grid em{display:block;height:100%;background:var(--accent);border-radius:5px}.review-list h2{font-size:18px}.review-list details{border-top:1px solid var(--border-subtle);padding:14px 0}.review-list summary{display:flex;justify-content:space-between;gap:18px;cursor:pointer}.review-list p,.review-list small{color:var(--text-secondary);line-height:1.7}.completion{display:flex;align-items:center;justify-content:center;gap:24px;padding:60px 20px}.score-ring{width:110px;height:110px;display:grid;place-items:center;border:8px solid var(--accent-soft);outline:2px solid var(--accent);border-radius:50%;font-size:34px;font-weight:800;color:var(--accent)}@keyframes pulse{50%{transform:scale(1.05);opacity:.45}}@keyframes bars{to{height:25px}}@media(max-width:800px){.studio{grid-template-columns:1fr}.interviewer-panel{border-right:0;border-bottom:1px solid var(--border-subtle)}.form-grid,.dimension-grid{grid-template-columns:1fr 1fr}.page-head{align-items:start;flex-direction:column}}@media(max-width:520px){.form-grid,.dimension-grid{grid-template-columns:1fr}.interview-page{padding:16px}.conversation-panel{padding:20px}.answer-actions{flex-wrap:wrap}.answer-actions .primary{width:100%}}
</style>

<style scoped>
.camera-dock {
  margin-top: 20px;
  padding-top: 18px;
  border-top: 1px solid var(--border-subtle);
}
.source-field { grid-column: 1 / -1; }
.source-field small { display: block; margin-top: 6px; color: var(--text-muted); font-size: 10px; line-height: 1.5; }
.source-evidence { display: inline-flex; margin-top: 3px; padding: 5px 8px; border: 1px solid var(--brand-blue-border); border-radius: 7px; background: var(--brand-blue-soft); color: var(--brand-blue-strong); font-size: 10px; }

.camera-preview {
  position: relative;
  width: 100%;
  aspect-ratio: 4 / 3;
  overflow: hidden;
  border: 1px solid #cbd9e4;
  border-radius: 14px;
  background: linear-gradient(145deg, #eaf2ff, #eef8f3);
}

.camera-preview video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transform: scaleX(-1);
}

.camera-placeholder {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  gap: 6px;
  padding: 14px;
  color: var(--text-secondary);
  text-align: center;
}

.camera-placeholder::before {
  width: 46px;
  height: 34px;
  margin: 0 auto 4px;
  border: 2px solid var(--brand-blue);
  border-radius: 9px;
  background: rgba(255, 255, 255, .65);
  box-shadow: 10px 0 0 -6px var(--brand-blue);
  content: '';
}

.camera-placeholder span { font-size: 13px; font-weight: 700; }
.camera-placeholder small,
.camera-dock > small { color: var(--text-muted); font-size: 11px; line-height: 1.5; }
.camera-toggle {
  width: 100%;
  margin: 10px 0 7px;
  padding: 9px 11px;
  border: 1px solid var(--accent-border);
  border-radius: 9px;
  background: #fff;
  color: var(--accent);
  font-weight: 700;
  cursor: pointer;
}
.camera-dock.active .camera-toggle { color: #9a493c; border-color: #efc4bc; background: #fff7f5; }
.record-toggle {
  width: 100%;
  margin: 0 0 7px;
  padding: 9px 11px;
  border: 1px solid #c9d9e7;
  border-radius: 9px;
  background: #f5f9ff;
  color: #315f8f;
  font-weight: 700;
  cursor: pointer;
}
.record-toggle.recording {
  border-color: #eab5aa;
  background: #fff0ed;
  color: #ad402f;
  box-shadow: 0 0 0 3px rgba(190, 69, 49, .08);
}
.record-toggle:disabled { cursor: not-allowed; opacity: .5; }
.camera-error { display: block; color: #a34235 !important; }

.fluency-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-top: 14px;
  padding: 13px;
  border: 1px solid #cfe0e8;
  border-radius: 12px;
  background: linear-gradient(90deg, #f4f8ff, #f2faf6);
}
.fluency-strip span { color: var(--text-secondary); font-size: 11px; }
.fluency-strip b { display: block; margin-bottom: 3px; color: var(--text-primary); font-size: 18px; }
.fluency-strip small { grid-column: 1 / -1; color: var(--text-muted); }
.live-timeline,
.replay-timeline,
.evidence-only-timeline {
  margin-top: 12px;
  padding: 12px 13px;
  border: 1px solid var(--border-subtle);
  border-radius: 11px;
  background: #fbfcfd;
}
.timeline-track {
  position: relative;
  height: 8px;
  margin: 4px 6px 9px;
  border-radius: 999px;
  background: linear-gradient(90deg, #d7e7df, #d8e7f5);
}
.timeline-track > i,
.timeline-track > button {
  position: absolute;
  top: 50%;
  width: 12px;
  height: 12px;
  margin: -6px 0 0 -6px;
  padding: 0;
  border: 2px solid #fff;
  border-radius: 50%;
  background: #d28b2e;
  box-shadow: 0 1px 5px rgba(34, 65, 55, .24);
}
.timeline-track > .filler { background: #3c7fb2; }
.timeline-track > button { cursor: pointer; }
.timeline-track > button:focus-visible { outline: 3px solid rgba(45, 118, 91, .24); outline-offset: 2px; }
.live-timeline p { display: flex; justify-content: space-between; margin: 0; color: var(--text-muted); font-size: 10px; }
.live-timeline b { color: var(--text-secondary); font-weight: 650; }
.local-replay { margin-top: 14px; padding: 14px; border: 1px solid #cfe0e8; border-radius: 12px; background: linear-gradient(145deg, #f7fbff, #f6fbf8); }
.replay-head { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.replay-head strong { font-size: 12px; }
.replay-head span,
.evidence-only-timeline > span { color: var(--text-muted); font-size: 10px; }
.local-replay video { width: min(100%, 620px); max-height: 350px; display: block; margin: 0 auto; border-radius: 10px; background: #132019; }
.marker-list { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 9px; }
.marker-list button,
.marker-list span { display: inline-flex; align-items: center; gap: 5px; padding: 5px 7px; border: 1px solid var(--border-subtle); border-radius: 7px; background: #fff; color: var(--text-secondary); font-size: 10px; }
.marker-list button { cursor: pointer; }
.marker-list i { width: 7px; height: 7px; border-radius: 50%; background: #d28b2e; }
.marker-list i.filler { background: #3c7fb2; }
.evidence-only-timeline > strong { margin-right: 8px; font-size: 11px; }
.completion-companion { margin-top: 18px; }
.resume-panel { margin-bottom: 24px; padding: 24px; background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 14px; }
.resume-heading { display: flex; align-items: start; justify-content: space-between; gap: 16px; }
.resume-heading h2 { margin: 0 0 8px; font-size: 20px; }
.resume-heading p, .resume-empty { color: var(--text-secondary); font-size: 13px; }
.resume-heading p { margin: 0 0 16px; }
.resume-heading .ghost { white-space: nowrap; }
.resume-list { display: grid; }
.resume-item { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 16px 4px; min-height: 64px; border: 0; border-top: 1px solid var(--border-subtle); text-align: left; background: transparent; color: var(--text-primary); cursor: pointer; }
.resume-item:hover { background: var(--accent-soft); }
.resume-item:disabled { opacity: .6; cursor: wait; }
.resume-item b, .resume-item small { display: block; overflow-wrap: anywhere; }
.resume-item small { margin-top: 6px; color: var(--text-secondary); }
.resume-action { flex-shrink: 0; font-size: 13px; color: var(--accent); }
@media (max-width: 600px) { .resume-panel { padding: 16px; } .resume-heading { flex-wrap: wrap; } }
.score-ring { flex-shrink: 0; }
.score-ring.unassessed { font-size: 22px; white-space: nowrap; text-align: center; }
.evaluation-head > strong { flex-shrink: 0; white-space: nowrap; }
.dimension-grid { grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); }

@media (max-width: 800px) {
  .camera-preview { max-width: 300px; margin: 0 auto; }
  .camera-toggle { max-width: 300px; }
}

@media (max-width: 620px) {
  .fluency-strip { grid-template-columns: 1fr 1fr; }
  .replay-head { align-items: flex-start; flex-direction: column; }
}

@media (prefers-reduced-motion: reduce) {
  .speaking .pulse,
  .speaking .voice-bars i { animation: none; }
}
</style>
