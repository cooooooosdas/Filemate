<template>
  <div class="interview-page">
    <header class="page-head">
      <div>
        <p class="eyebrow">AI INTERVIEW STUDIO</p>
        <h1>数字人模拟面试</h1>
        <p>真实问题、即时追问、四维评分，把每一次回答变成可复盘的数据。</p>
      </div>
      <span class="status-pill" aria-live="polite"><i></i>{{ session ? '面试进行中' : '准备就绪' }}</span>
    </header>

    <section v-if="!session" class="setup-card">
      <div class="setup-copy">
        <span>01 / 创建面试</span>
        <h2>选择你要训练的真实场景</h2>
        <p>第一版采用结构化面试官与浏览器语音能力，无需额外安装语音软件。</p>
      </div>
      <div class="form-grid">
        <label>目标岗位或方向<input v-model="form.targetRole" name="target_role" autocomplete="off" placeholder="例如：Java 后端开发 / 软件杯答辩" /></label>
        <label>面试场景<select v-model="form.scenario" name="interview_scenario"><option>求职面试</option><option>竞赛答辩</option><option>保研复试</option></select></label>
        <label>难度<select v-model="form.difficulty" name="interview_difficulty"><option>入门</option><option>标准</option><option>压力面</option></select></label>
      </div>
      <button class="primary" :disabled="loading || !form.targetRole.trim()" @click="begin">{{ loading ? '正在创建…' : '开始模拟面试' }}</button>
    </section>

    <template v-else>
      <section class="studio">
        <div class="interviewer-panel">
          <div class="avatar-stage" :class="{ speaking }">
            <div class="pulse pulse-one" aria-hidden="true"></div><div class="pulse pulse-two" aria-hidden="true"></div>
            <div class="avatar-face"><span>FM</span></div>
            <div class="voice-bars" aria-hidden="true"><i v-for="n in 7" :key="n"></i></div>
          </div>
          <div><p class="role">FileMate 数字面试官</p><p class="online"><i></i>在线 · 中文普通话</p></div>
          <button class="ghost" :disabled="!session.current_question" @click="speakQuestion">重新播报问题</button>
        </div>

        <div class="conversation-panel">
          <div class="progress-row"><span>第 {{ Math.min(session.current_index + 1, session.questions.length) }} / {{ session.questions.length }} 题</span><strong>{{ session.overall_score ? `${session.overall_score.toFixed(0)} 分` : '待评分' }}</strong></div>
          <div class="progress"><i :style="{ width: `${session.current_index / session.questions.length * 100}%` }"></i></div>

          <div v-if="session.status === 'active'" class="question-block">
            <p>面试官提问</p><h2>{{ session.current_question }}</h2>
            <textarea v-model="answer" name="interview_answer" autocomplete="off" aria-label="当前面试回答" rows="7" placeholder="建议用“情境—任务—行动—结果”结构回答…"></textarea>
            <div class="answer-actions">
              <button class="voice" :class="{ recording }" @click="toggleRecording">{{ recording ? '停止录音' : '语音回答' }}</button>
              <span>{{ answer.length }} 字</span>
              <button class="primary" :disabled="loading || answer.trim().length < 4" @click="submit">{{ loading ? '评分中…' : '提交并进入下一题' }}</button>
            </div>
          </div>

          <div v-else class="completion">
            <span class="score-ring">{{ session.overall_score.toFixed(0) }}</span>
            <div><p>本轮面试完成</p><h2>{{ scoreLabel }}</h2><button class="primary" @click="reset">再练一次</button></div>
          </div>
        </div>
      </section>

      <section v-if="session.latest_evaluation" class="evaluation">
        <div class="evaluation-head"><div><p class="eyebrow">即时反馈</p><h2>{{ session.latest_evaluation.feedback }}</h2></div><strong>{{ session.latest_evaluation.score.toFixed(0) }}</strong></div>
        <div class="dimension-grid"><div v-for="(score, name) in session.latest_evaluation.dimensions" :key="name"><span>{{ name }}</span><b>{{ score.toFixed(0) }}</b><i><em :style="{ width: `${score}%` }"></em></i></div></div>
      </section>

      <section v-if="session.turns.length" class="review-list">
        <h2>回答记录</h2>
        <details v-for="(turn, index) in session.turns" :key="turn.turn_id" :open="index === session.turns.length - 1"><summary><span>Q{{ index + 1 }} · {{ turn.question }}</span><b>{{ turn.score.toFixed(0) }} 分</b></summary><p>{{ turn.answer }}</p><small>{{ turn.feedback }}</small></details>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { answerInterview, startInterview, type InterviewSession } from '../services/api'

const form = ref({ targetRole: '', scenario: '求职面试', difficulty: '标准' })
const session = ref<InterviewSession | null>(null)
const answer = ref('')
const loading = ref(false)
const speaking = ref(false)
const recording = ref(false)
let recognition: any = null

const scoreLabel = computed(() => {
  const score = session.value?.overall_score || 0
  return score >= 85 ? '表现出色，可以进入实战' : score >= 70 ? '基础扎实，继续优化表达' : '已发现提升空间，建议再练一轮'
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
  try { session.value = await startInterview(form.value.targetRole, form.value.scenario, form.value.difficulty); setTimeout(speakQuestion, 180) }
  catch (error: any) { ElMessage.error(error.message || '创建失败') }
  finally { loading.value = false }
}

const submit = async () => {
  if (!session.value) return
  loading.value = true
  try { session.value = await answerInterview(session.value.interview_id, answer.value); answer.value = ''; if (session.value.status === 'active') setTimeout(speakQuestion, 180) }
  catch (error: any) { ElMessage.error(error.message || '评分失败') }
  finally { loading.value = false }
}

const toggleRecording = () => {
  if (recording.value) { recognition?.stop(); return }
  const Recognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!Recognition) { ElMessage.info('当前浏览器不支持语音识别，请使用文字回答'); return }
  recognition = new Recognition(); recognition.lang = 'zh-CN'; recognition.continuous = true; recognition.interimResults = true
  recognition.onstart = () => { recording.value = true }
  recognition.onend = () => { recording.value = false }
  recognition.onerror = () => { recording.value = false; ElMessage.warning('语音识别中断，请重试') }
  recognition.onresult = (event: any) => { answer.value = Array.from(event.results).map((result: any) => result[0].transcript).join('') }
  recognition.start()
}
const reset = () => { window.speechSynthesis?.cancel(); session.value = null; answer.value = '' }
onBeforeUnmount(() => { recognition?.stop(); window.speechSynthesis?.cancel() })
</script>

<style scoped>
.interview-page{max-width:1180px;margin:0 auto;padding:28px;color:var(--text-primary)}.page-head{display:flex;justify-content:space-between;gap:24px;align-items:end;margin-bottom:26px}.eyebrow{margin:0;color:var(--accent);font-size:11px;font-weight:800;letter-spacing:.15em}.page-head h1{font-size:32px;margin:6px 0}.page-head p{margin:0;color:var(--text-secondary)}.status-pill{display:flex;align-items:center;gap:8px;padding:8px 12px;border:1px solid var(--accent-border);border-radius:999px;color:var(--accent);background:var(--accent-soft)}.status-pill i,.online i{width:7px;height:7px;border-radius:50%;background:#36a269}.setup-card,.studio,.evaluation,.review-list{background:var(--bg-surface);border:1px solid var(--border-subtle);border-radius:18px}.setup-card{padding:30px}.setup-copy span{color:var(--accent);font-size:12px}.setup-copy h2{font-size:24px;margin:8px 0}.setup-copy p{color:var(--text-secondary)}.form-grid{display:grid;grid-template-columns:2fr 1fr 1fr;gap:14px;margin:26px 0}.form-grid label{font-size:13px;color:var(--text-secondary)}input,select,textarea{box-sizing:border-box;width:100%;margin-top:7px;padding:12px;border:1px solid var(--border-default);border-radius:10px;background:var(--bg-elevated);color:var(--text-primary);font:inherit}textarea{resize:vertical;line-height:1.7}.primary,.ghost,.voice{border:0;border-radius:10px;padding:11px 17px;cursor:pointer}.primary{background:var(--accent);color:white;font-weight:700}.primary:disabled{opacity:.45}.studio{display:grid;grid-template-columns:310px 1fr;overflow:hidden}.interviewer-panel{padding:30px;background:var(--sidebar-bg);text-align:center;border-right:1px solid var(--border-subtle)}.avatar-stage{position:relative;width:180px;height:180px;margin:12px auto 24px;display:grid;place-items:center}.avatar-face{position:relative;z-index:2;width:112px;height:112px;display:grid;place-items:center;border-radius:42% 42% 48% 48%;background:linear-gradient(145deg,#2f7d55,#68a97f);color:white;font-size:28px;font-weight:800;box-shadow:0 16px 35px rgba(47,125,85,.2)}.pulse{position:absolute;border:1px solid var(--accent-border);border-radius:50%}.pulse-one{inset:12px}.pulse-two{inset:0}.speaking .pulse{animation:pulse 1.3s infinite}.voice-bars{position:absolute;bottom:1px;display:flex;gap:3px}.voice-bars i{width:3px;height:8px;background:var(--accent);border-radius:3px}.speaking .voice-bars i{animation:bars .7s infinite alternate}.voice-bars i:nth-child(2n){animation-delay:.2s}.role{font-weight:700}.online{font-size:12px;color:var(--text-secondary)}.online i{display:inline-block;margin-right:5px}.ghost{margin-top:18px;border:1px solid var(--accent-border);background:transparent;color:var(--accent)}.conversation-panel{padding:30px}.progress-row{display:flex;justify-content:space-between;color:var(--text-secondary);font-size:13px}.progress{height:5px;background:var(--bg-elevated);border-radius:5px;margin:10px 0 28px}.progress i{display:block;height:100%;background:var(--accent);border-radius:5px}.question-block>p{font-size:12px;color:var(--accent)}.question-block h2{font-size:22px;line-height:1.5}.answer-actions{display:flex;gap:12px;align-items:center;margin-top:12px}.answer-actions span{color:var(--text-muted);font-size:12px;margin-right:auto}.voice{border:1px solid var(--accent-border);color:var(--accent);background:var(--accent-soft)}.voice.recording{background:#fff0ec;color:#b44b34}.evaluation,.review-list{margin-top:18px;padding:24px}.evaluation-head{display:flex;justify-content:space-between;gap:20px}.evaluation-head h2{font-size:17px}.evaluation-head>strong{font-size:42px;color:var(--accent)}.dimension-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}.dimension-grid>div{display:grid;grid-template-columns:1fr auto;gap:8px}.dimension-grid i{grid-column:1/-1;height:5px;background:var(--bg-elevated);border-radius:5px}.dimension-grid em{display:block;height:100%;background:var(--accent);border-radius:5px}.review-list h2{font-size:18px}.review-list details{border-top:1px solid var(--border-subtle);padding:14px 0}.review-list summary{display:flex;justify-content:space-between;gap:18px;cursor:pointer}.review-list p,.review-list small{color:var(--text-secondary);line-height:1.7}.completion{display:flex;align-items:center;justify-content:center;gap:24px;padding:60px 20px}.score-ring{width:110px;height:110px;display:grid;place-items:center;border:8px solid var(--accent-soft);outline:2px solid var(--accent);border-radius:50%;font-size:34px;font-weight:800;color:var(--accent)}@keyframes pulse{50%{transform:scale(1.05);opacity:.45}}@keyframes bars{to{height:25px}}@media(max-width:800px){.studio{grid-template-columns:1fr}.interviewer-panel{border-right:0;border-bottom:1px solid var(--border-subtle)}.form-grid,.dimension-grid{grid-template-columns:1fr 1fr}.page-head{align-items:start;flex-direction:column}}@media(max-width:520px){.form-grid,.dimension-grid{grid-template-columns:1fr}.interview-page{padding:16px}.conversation-panel{padding:20px}.answer-actions{flex-wrap:wrap}.answer-actions .primary{width:100%}}
</style>
