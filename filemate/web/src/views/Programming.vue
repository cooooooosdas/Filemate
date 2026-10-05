<template>
  <div class="coding-page">
    <header class="page-heading"><div><p class="eyebrow">写代码 · 跑测试 · 留下复盘</p><h1>编程练习</h1><p>从一道题开始，用真实编译与测试检查每一次进步。</p></div><button :disabled="!!busy || loading" @click="load">刷新记录</button></header>
    <section class="environment" aria-label="评测环境">
      <div><strong>{{ environment?.ready ? '隔离评测已就绪' : '评测环境待准备' }}</strong><p>{{ environment?.ready ? 'C++17 · 单测试点 1 秒 / 256 MB · 禁止网络 · 单进程' : environment?.error || '正在核对本地环境…' }}</p></div>
      <button v-if="environment && !environment.ready && environment.setup_supported" :disabled="!!busy || !environment.installed" @click="setup">{{ busy === 'setup' ? '正在准备…' : '准备本地评测环境' }}</button>
    </section>
    <p v-if="environment && !environment.ready && environment.installed && environment.setup_supported" class="muted">首次准备会在应用专用目录复制本机 C++ 工具链，并执行隔离自检。</p>
    <div v-if="error" role="alert" class="message error">{{ error }}</div><p v-if="notice" role="status" class="message">{{ notice }}</p>
    <p v-if="loading" role="status">正在读取题目与提交记录…</p>
    <nav class="tabs" aria-label="编程工作台" role="tablist">
      <button v-for="item in tabs" :key="item.id" role="tab" :aria-selected="tab === item.id" :class="{ active: tab === item.id }" @click="tab = item.id">{{ item.label }}</button>
    </nav>

    <section v-if="tab === 'practice'" class="practice-grid">
      <aside class="panel problem-panel">
        <div class="filters"><label>题目难度<select v-model="difficulty" aria-label="题目难度" :disabled="!!busy"><option value="">全部难度</option><option>简单</option><option>中等</option><option>困难</option></select></label><label>知识分类<select v-model="category" aria-label="知识分类" :disabled="!!busy"><option value="">全部分类</option><option v-for="tag in tags" :key="tag">{{ tag }}</option></select></label></div>
        <label>选择题目<select :value="problemId" aria-label="选择题目" :disabled="!!busy" @change="chooseProblem(($event.target as HTMLSelectElement).value)"><option v-for="p in filteredProblems" :key="p.id" :value="p.id">{{ p.difficulty }} · {{ p.title }}</option><option v-if="!filteredProblems.length" value="">没有符合条件的题目</option></select></label>
        <template v-if="problem"><div class="problem-title"><span>{{ problem.difficulty }} · {{ problem.test_count }} 个测试点</span><h2>{{ problem.title }}</h2></div><div class="tags"><span v-for="tag in problem.tags" :key="tag">{{ tag }}</span></div><p class="statement">{{ problem.statement }}</p><h3>输入输出示例</h3><div v-for="(example, i) in problem.examples" :key="i" class="example"><span>输入</span><pre>{{ example.input }}</pre><span>输出</span><pre>{{ example.output }}</pre></div><details><summary>查看解题提示</summary><p>{{ problem.hint }}</p></details><p class="attribution">{{ problem.attribution }}</p></template>
      </aside>
      <section class="panel code-panel" aria-label="C++ 编辑与提交">
        <div class="panel-title"><h2>C++ 编辑器</h2><span>{{ environment?.provider?.includes('Linux') ? 'GCC' : 'MSVC' }} · 标准 C++17</span></div><p class="muted">使用标准头文件（如 &lt;iostream&gt;、&lt;vector&gt;），便于跨平台练习。代码与判题结果会保存在当前学习空间。</p>
        <CodeEditor v-model="code" :disabled="!!busy" />
        <div class="editor-actions"><button class="primary" :disabled="!problem || !code.trim() || !!busy || !environment?.ready" @click="submit">{{ busy === 'run' ? '正在编译评测…' : '提交并评测' }}</button><button v-if="current && ['queued', 'running'].includes(current.status)" :disabled="cancelling" @click="cancelRun">{{ cancelling ? '正在取消…' : '取消评测' }}</button><span class="muted">最多 100 KB，输出超过 64 KB 会终止该测试点。</span></div>
      </section>
    </section>

    <section v-if="tab === 'wrongbook'" class="panel">
      <h2>编程错题复盘</h2><p class="muted">每次错误提交保留代码与失败测试点，同题连续两次通过后标记已复习。</p><p v-if="!overview?.profile.wrongbook.length" class="empty">还没有编程错题记录。</p>
      <article v-for="wrong in overview?.profile.wrongbook" :key="wrong.problem_id" class="wrong-row"><div><h3>{{ wrong.title }}</h3><p>{{ wrong.error_count }} 次错误 / {{ wrong.submission_count }} 次有效提交 · {{ wrong.mastered ? '已复习' : '待复习' }} · 连续通过 {{ wrong.correct_streak }} 次</p><p>最近复盘：{{ wrong.last_review_at ? dateText(wrong.last_review_at) : '尚未保存复盘' }}</p></div><div class="row-actions"><button :disabled="!!busy" @click="openSubmission(wrong.latest_error_id)">查看失败代码与测试点</button><button :disabled="!!busy" @click="practiceProblem(wrong.problem_id)">再练一次</button></div></article>
    </section>

    <section v-if="tab === 'history'" class="panel">
      <h2>提交记录</h2><p class="muted">显示最近 100 次提交，撤销会排除统计，原始记录仍保留。</p><p v-if="!overview?.submissions.length" class="empty">还没有提交。选择一道题开始练习。</p>
      <article v-for="s in overview?.submissions" :key="s.submission_id" class="history-row"><div><h3>{{ titleFor(s.problem_id) }} <span class="verdict" :class="{ accepted: s.result.verdict === 'AC' }">{{ verdictText(s) }}</span></h3><p>{{ dateText(s.created_at) }} · {{ submissionEvidenceText(s) }} · {{ s.result.passed || 0 }}/{{ s.result.total || 0 }} 个测试点</p></div><button :disabled="!!busy" @click="openSubmission(s.submission_id)">查看提交</button></article>
    </section>

    <section v-if="tab === 'profile'" class="panel">
      <h2>编程练习证据</h2><p class="muted">统计全部有效完成的提交。没有练习的分类显示待评测，能力建议仍需结合题目难度与样本量判断。</p><div class="metrics"><div><span>有效完成提交</span><strong>{{ overview?.profile.attempt_count || 0 }}</strong></div><div><span>全部通过</span><strong>{{ overview?.profile.accepted_count || 0 }}</strong></div><div><span>待复习题目</span><strong>{{ overview?.profile.wrongbook.filter(w => !w.mastered).length || 0 }}</strong></div></div>
      <p>本周练习 {{ overview?.profile.weekly.problems || 0 }} 道题，完成 {{ overview?.profile.weekly.submissions || 0 }} 次提交。AC {{ overview?.profile.weekly.verdicts.AC || 0 }} · WA {{ overview?.profile.weekly.verdicts.WA || 0 }} · TLE {{ overview?.profile.weekly.verdicts.TLE || 0 }} · RE {{ overview?.profile.weekly.verdicts.RE || 0 }} · CE {{ overview?.profile.weekly.verdicts.CE || 0 }}。</p>
      <p>每道已练习题目的平均提交次数：{{ overview?.profile.average_submissions_per_problem ?? '待评测' }}。{{ overview?.profile.lowest_acceptance_tags.length ? '提交通过率最低的分类（至少 3 次提交）：' + overview.profile.lowest_acceptance_tags.join('、') : '分类薄弱点仍待积累更多练习。' }}</p>
      <p>{{ overview?.profile.rule }}</p><div class="category-grid"><article v-for="item in overview?.profile.categories" :key="item.tag"><h3>{{ item.tag }}</h3><p>{{ item.submissions ? `${item.accepted} / ${item.submissions} 次通过` : '待评测' }}</p><progress v-if="item.accept_rate !== null" :aria-label="item.tag + '提交通过率'" :value="item.accept_rate" max="1" /><span v-if="item.accept_rate !== null">{{ Math.round(item.accept_rate * 100) }}% 提交通过率</span></article></div>
      <h3>最近的实际提交</h3><p v-if="!overview?.profile.trend.length">还没有可展示的练习记录。</p><ol class="trend"><li v-for="point in overview?.profile.trend" :key="point.submission_id">{{ dateText(point.created_at) }} · {{ titleFor(point.problem_id) }} · {{ point.verdict }} · {{ point.score }} 分</li></ol>
    </section>

    <section v-if="tab === 'events'" class="panel"><h2>操作日志</h2><p class="muted">只记录操作与提交标识，日志不包含源代码或模型凭据。</p><p v-if="!overview?.events.length">暂无操作记录。</p><ol class="event-list"><li v-for="event in overview?.events" :key="event.event_id"><strong>{{ actionText(event.action) }}</strong><span>{{ dateText(event.created_at) }}</span><code>{{ event.submission_id?.slice(0, 12) || '环境准备' }}</code></li></ol></section>

    <section v-if="current" class="panel result-panel" aria-label="评测结果">
      <div class="panel-title"><div><p class="eyebrow">{{ titleFor(current.problem_id) }} · {{ current.submission_id.slice(0, 12) }}</p><h2>评测结果 <span class="verdict" :class="{ accepted: current.result.verdict === 'AC' }">{{ verdictText(current) }}</span></h2></div><div class="row-actions"><button v-if="current.status === 'queued'" :disabled="!!busy || !environment?.ready || current.data_error" @click="run(current.submission_id)">继续评测</button><button v-if="tab !== 'practice' && ['queued', 'running'].includes(current.status)" :disabled="cancelling" @click="cancelRun">{{ cancelling ? '正在取消…' : '取消评测' }}</button><button v-if="!['queued', 'running'].includes(current.status)" :disabled="!!busy || (current.data_error && !current.active)" @click="transition(current.active ? 'undo' : 'restore')">{{ current.active ? '撤销这次提交' : '恢复这次提交' }}</button><button :disabled="!!busy || current.data_error" @click="reuseCode">载入这份代码</button><button v-if="!['queued', 'running'].includes(current.status)" :disabled="!!busy" @click="eraseSubmission">彻底删除此提交</button></div></div>
      <p v-if="current.data_error" role="alert" class="message error">提交记录损坏或题目版本不可用，原始数据已保留，暂不能评测、修改或恢复。</p><p v-if="current.result.error" role="alert" class="message error">{{ current.result.error }}</p><p v-if="!current.active" class="message">这次提交已撤销，不计入练习统计。恢复后，只有有效完成的评测记录才会重新计入。</p>
      <div class="metrics"><div><span>通过测试点</span><strong>{{ current.result.passed || 0 }} / {{ current.result.total || 0 }}</strong></div><div><span>测试得分</span><strong>{{ current.result.score ?? '待评测' }}</strong></div><div><span>评测状态</span><strong class="state-text">{{ current.data_error ? '记录不可用' : stateText(current.status) }}</strong></div></div>
      <details v-if="current.result.compile_log" class="compile-log" :open="current.result.verdict === 'CE'"><summary>编译器诊断</summary><pre>{{ current.result.compile_log }}</pre></details>
      <div class="test-list"><details v-for="point in current.result.tests" :key="point.index"><summary><span>{{ point.index + 1 }}. {{ point.name }}</span><strong :class="{ accepted: point.verdict === 'AC' }">{{ point.verdict }}</strong><span>{{ point.elapsed_ms }} ms · {{ (point.peak_memory_bytes / 1048576).toFixed(1) }} MB</span></summary><div class="test-evidence"><div><h4>测试输入{{ point.input_truncated ? '（前 4096 字符）' : '' }}</h4><pre>{{ point.input || '（空输入）' }}</pre></div><div><h4>期望输出</h4><pre>{{ point.expected }}</pre></div><div><h4>实际输出</h4><pre>{{ point.actual || '（无输出）' }}</pre></div></div><p>退出码 {{ point.exit_code }}{{ point.reason ? ' · ' + point.reason : '' }}</p><pre v-if="point.stderr">{{ point.stderr }}</pre></details></div>
      <details class="submitted-code"><summary>查看这次提交的原始代码</summary><pre>{{ current.code }}</pre></details>
      <section class="feedback" aria-label="代码复盘"><h3>代码复盘</h3><p class="muted">判题得分仅由测试决定。模型复盘中的复杂度和修改建议均供参考。</p><div class="review-actions"><button :disabled="!!busy || current.status !== 'completed' || !current.active || current.data_error" @click="review('local')">保存本地复盘</button><button :disabled="!!busy || !externalConsent || current.status !== 'completed' || !current.active || current.data_error" @click="review('llm')">{{ busy === 'review' ? '正在生成复盘…' : 'AI 代码复盘' }}</button></div><label class="consent"><input v-model="externalConsent" type="checkbox" :disabled="!!busy" />我同意将题面、这次提交的代码与测试结果发送给已配置的外部模型。</label>
        <template v-if="feedback"><p class="feedback-label">{{ feedback.provider === 'external_model' ? '模型参考建议' : '本地规则提示' }}</p><p>{{ feedback.summary }}</p><ul><li v-for="(issue, index) in feedback.issues" :key="index">第 {{ issue.line }} 行：{{ issue.message }}</li><li v-for="point in feedback.failed_tests" :key="point.index">{{ point.name }}（{{ point.verdict }}）：{{ point.message }}</li></ul><p>时间复杂度：{{ feedback.time_complexity }}；空间复杂度：{{ feedback.space_complexity }}</p><p>{{ feedback.suggestion }}</p></template>
        <label>我的复盘笔记<textarea v-model="notes" aria-label="我的复盘笔记" maxlength="8000" :disabled="!!busy || !current.active || current.data_error" placeholder="记录哪里出错、如何修改，以及下次要注意的边界。" /></label><button :disabled="!!busy || ['queued', 'running'].includes(current.status) || !current.active || current.data_error" @click="saveNotes">保存复盘笔记</button>
      </section>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import CodeEditor from '../components/CodeEditor.vue'
import { getProgrammingProblems, getProgrammingStatus, setupProgramming, getCodingOverview, getCodingSubmission, createCodingSubmission, runCodingSubmission, changeCodingSubmission, reviewCodingSubmission, saveCodingNotes, previewCodingDeletion, deleteCodingSubmission } from '../services/api'
import type { CodingOverview, CodingProblem, CodingSubmission, ProgrammingStatus } from '../types/programming'
import { codingStateText as stateText, submissionVerdictText as verdictText, submissionEvidenceText } from '../programming/submissionState'
const problems = shallowRef<CodingProblem[]>([])
const route = useRoute(), router = useRouter()
const overview = shallowRef<CodingOverview | null>(null)
const environment = shallowRef<ProgrammingStatus | null>(null)
const current = shallowRef<CodingSubmission | null>(null)
const problemId = ref(''), difficulty = ref(''), category = ref(''), code = ref(''), notes = ref('')
const loading = ref(false), busy = ref(''), cancelling = ref(false), error = ref(''), notice = ref(''), externalConsent = ref(false)
const tab = ref('practice')
const tabs = [{ id: 'practice', label: '题目练习' }, { id: 'wrongbook', label: '编程错题' }, { id: 'history', label: '提交记录' }, { id: 'profile', label: '练习证据' }, { id: 'events', label: '操作日志' }]
const drafts = new Map<string, string>()
const tags = computed(() => [...new Set(problems.value.flatMap(p => p.tags))].sort())
const filteredProblems = computed(() => problems.value.filter(p => (!difficulty.value || p.difficulty === difficulty.value) && (!category.value || p.tags.includes(category.value))))
const problem = computed(() => problems.value.find(p => p.id === problemId.value))
const feedback = computed(() => current.value?.review || current.value?.local_feedback)
let disposed = false, loadEpoch = 0, runEpoch = 0, pollTimer: number | undefined, polling = false
let pending: { problem: string; code: string; key: string } | null = null
function message(cause: unknown) { return cause instanceof Error ? cause.message : '操作失败，请稍后重试' }
function selectRecord(row: CodingSubmission) { if (row.submission_id !== current.value?.submission_id) externalConsent.value = false; current.value = row; notes.value = row.notes || '' }
function chooseProblem(id: string) { if (busy.value) return; if (problemId.value) drafts.set(problemId.value, code.value); problemId.value = id; code.value = drafts.get(id) ?? problems.value.find(p => p.id === id)?.starter ?? '' }
watch(filteredProblems, list => { if (!list.some(p => p.id === problemId.value)) chooseProblem(list[0]?.id || '') })
async function load() {
  const epoch = ++loadEpoch; loading.value = true; error.value = ''
  const values = await Promise.allSettled([getProgrammingProblems(), getCodingOverview(), getProgrammingStatus()])
  if (disposed || epoch !== loadEpoch) return
  if (values[0].status === 'fulfilled') problems.value = values[0].value
  if (values[1].status === 'fulfilled') overview.value = values[1].value
  if (values[2].status === 'fulfilled') environment.value = values[2].value
  error.value = values.filter(v => v.status === 'rejected').map(v => message((v as PromiseRejectedResult).reason)).join('；')
  if (!problemId.value && problems.value.length) chooseProblem(problems.value.find(p => p.id === route.query.problem)?.id || problems.value[0]!.id)
  if (typeof route.query.submission === 'string' && !current.value) await openSubmission(route.query.submission)
  loading.value = false
}
async function refreshOverview() { const value = await getCodingOverview(); if (!disposed) overview.value = value }
async function setup() { busy.value = 'setup'; error.value = ''; try { const value = await setupProgramming(); if (!disposed) { environment.value = value; notice.value = value.ready ? '隔离自检已通过，可以开始评测。' : value.error; await refreshOverview() } } catch (e) { if (!disposed) error.value = message(e) } finally { if (!disposed) busy.value = '' } }
async function submit() {
  if (busy.value || !problem.value || !code.value.trim()) return
  busy.value = 'create'; error.value = ''; notice.value = ''
  if (!pending || pending.problem !== problemId.value || pending.code !== code.value) pending = { problem: problemId.value, code: code.value, key: crypto.randomUUID() }
  try {
    const row = await createCodingSubmission(pending.problem, pending.code, pending.key)
    if (disposed) return
    selectRecord(row); pending = null; busy.value = ''; await run(row.submission_id)
  } catch (e) { if (!disposed) { error.value = message(e); busy.value = '' } }
}
function stopPolling() { runEpoch++; if (pollTimer !== undefined) window.clearInterval(pollTimer); pollTimer = undefined }
async function run(id: string) {
  if (busy.value || disposed) return
  busy.value = 'run'; error.value = ''; stopPolling()
  const epoch = runEpoch
  pollTimer = window.setInterval(async () => {
    if (polling || disposed) return
    polling = true
    try { const row = await getCodingSubmission(id); if (!disposed && epoch === runEpoch && current.value?.submission_id === id && (current.value.status !== 'cancelled' || row.status === 'cancelled')) current.value = row } catch { /* 最终请求会显示网络错误并保留记录。 */ } finally { polling = false }
  }, 900)
  try { const row = await runCodingSubmission(id); if (!disposed) { selectRecord(row); notice.value = row.status === 'completed' ? `评测完成：${row.result.verdict}，通过 ${row.result.passed}/${row.result.total} 个测试点。` : stateText(row.status) } }
  catch (e) { if (!disposed) { error.value = message(e); try { const row = await getCodingSubmission(id); if (!disposed) selectRecord(row) } catch { /* 代码仍在编辑区，可刷新或重试读取。 */ } } }
  finally { stopPolling(); if (!disposed) { busy.value = ''; try { await refreshOverview() } catch (e) { error.value = message(e) } } }
}
async function cancelRun() { if (!current.value || cancelling.value) return; cancelling.value = true; try { const row = await changeCodingSubmission(current.value.submission_id, 'cancel'); if (!disposed) { selectRecord(row); notice.value = '评测已取消，提交代码已保留。' } } catch (e) { if (!disposed) error.value = message(e) } finally { if (!disposed) cancelling.value = false } }
async function openSubmission(id: string) { if (busy.value) return; busy.value = 'open'; try { const row = await getCodingSubmission(id); if (!disposed) selectRecord(row) } catch (e) { if (!disposed) error.value = message(e) } finally { if (!disposed) busy.value = '' } }
function practiceProblem(id: string) { difficulty.value = ''; category.value = ''; chooseProblem(id); tab.value = 'practice' }
async function reuseCode() { if (!current.value || busy.value) return; busy.value = 'reuse'; try { if (code.value.trim() && code.value !== problem.value?.starter && code.value !== current.value.code) await ElMessageBox.confirm('将用下方已展示的提交代码替换当前编辑内容，请先保留未提交的修改。', '载入提交代码', { confirmButtonText: '载入代码', cancelButtonText: '取消' }); if (disposed) return; const row = current.value; busy.value = ''; practiceProblem(row.problem_id); code.value = row.code; drafts.set(row.problem_id, row.code) } catch { /* 用户取消时保留编辑内容。 */ } finally { if (!disposed) busy.value = '' } }
async function eraseSubmission() {
  if (!current.value || busy.value) return
  const row = current.value; busy.value = 'delete'; error.value = ''
  try {
    const preview = await previewCodingDeletion(row.submission_id)
    await ElMessageBox.confirm(`将删除此提交的源码与反馈，并移除${preview.related_reports}份关联报告、解除${preview.profile_links}处个人事实关联。${preview.notice}`, '彻底删除编程提交', { confirmButtonText: '确认彻底删除', cancelButtonText: '取消' })
    if (disposed) return
    await deleteCodingSubmission(row.submission_id, preview.confirmation_token)
    stopPolling(); drafts.delete(row.problem_id); pending = null
    if (code.value === row.code) code.value = problem.value?.starter || ''
    current.value = null; notes.value = ''; externalConsent.value = false
    await refreshOverview(); ElMessage.success('此提交的源码、反馈与关联报告已删除')
    if (route.query.submission === row.submission_id) await router.replace({ path: '/programming', query: { problem: row.problem_id } })
  } catch (e) { if (!disposed && e !== 'cancel' && e !== 'close') error.value = message(e) } finally { if (!disposed) busy.value = '' }
}
async function transition(action: 'undo' | 'restore') { if (!current.value || busy.value) return; busy.value = action; try { if (action === 'undo') await ElMessageBox.confirm(current.value.data_error ? '这次提交会被撤销，原始记录保留；数据或题目版本恢复可用前，不能恢复统计资格。' : '这次提交会从练习统计与编程错题证据中排除。原始代码和测试结果保留，之后可恢复。', '撤销这次提交', { confirmButtonText: '确认撤销', cancelButtonText: '取消' }); if (disposed) return; const row = await changeCodingSubmission(current.value.submission_id, action); if (!disposed) { selectRecord(row); await refreshOverview() } } catch (e) { if (!disposed && e !== 'cancel' && e !== 'close') error.value = message(e) } finally { if (!disposed) busy.value = '' } }
async function review(mode: 'local' | 'llm') { if (!current.value || busy.value) return; busy.value = 'review'; error.value = ''; try { const row = await reviewCodingSubmission(current.value.submission_id, mode, externalConsent.value); if (!disposed) { selectRecord(row); notice.value = '代码复盘已保存。'; await refreshOverview() } } catch (e) { if (!disposed) error.value = message(e) } finally { if (!disposed) busy.value = '' } }
async function saveNotes() { if (!current.value || busy.value) return; busy.value = 'notes'; error.value = ''; try { const row = await saveCodingNotes(current.value.submission_id, notes.value); if (!disposed) { selectRecord(row); notice.value = '复盘笔记已保存。'; await refreshOverview() } } catch (e) { if (!disposed) error.value = message(e) } finally { if (!disposed) busy.value = '' } }
function titleFor(id: string) { return problems.value.find(p => p.id === id)?.title || id }
function dateText(value: string) { const date = new Date(value); return Number.isFinite(date.getTime()) ? date.toLocaleString('zh-CN') : '时间待核对' }
function actionText(action: string) { return ({ created: '保存提交', started: '开始评测', completed: '完成评测', cancelled: '取消评测', failed: '评测环境异常', interrupted: '服务中断', undo: '撤销提交', restore: '恢复提交', review_saved: '保存代码复盘', notes_saved: '保存复盘笔记', environment_checked: '环境自检' } as Record<string, string>)[action] || action }
onMounted(load)
onUnmounted(() => { disposed = true; loadEpoch++; stopPolling() })
</script>

<style scoped>
.coding-page{max-width:1500px;margin:auto;padding:32px;color:#293f2d}.page-heading,.panel-title,.environment{display:flex;justify-content:space-between;gap:20px;align-items:center}.page-heading h1{font-size:30px;margin:4px 0 10px;letter-spacing:-.5px}.eyebrow{font-size:14px;color:var(--text-muted);letter-spacing:1px;margin:0 0 6px}.page-heading p,.environment p{color:var(--text-muted);font-size:14px}.environment{margin:24px 0 8px;padding:16px 20px;background:var(--accent-soft);border:1px solid #dce7d4;border-radius:14px}.environment p{margin:6px 0 0}.panel{background:#fff;border:1px solid #e0e8da;border-radius:16px;padding:24px;min-width:0;margin-bottom:20px}h2{font-size:20px;margin:0 0 16px}h3{font-size:15px;margin:16px 0 10px}p{line-height:1.75}.muted,.attribution{font-size:14px;color:var(--text-muted)}.attribution{margin-top:24px}.message{border-radius:10px;padding:12px 16px;font-size:14px;background:var(--accent-soft);border:1px solid #d9e5d1;overflow-wrap:anywhere}.message.error{background:#fff5ee;color:#955a31;border-color:#ecd2bc}button,select,textarea{font:inherit}button{border:1px solid #d8e4ce;background:#f8fbf4;color:#405b33;border-radius:9px;padding:9px 14px;cursor:pointer;font-size:13px;min-height:38px}button:hover:enabled{background:var(--accent-soft)}button:disabled{opacity:.48;cursor:not-allowed}button:focus-visible,select:focus-visible,textarea:focus-visible{outline:2px solid var(--accent);outline-offset:3px}.primary{background:var(--accent);color:#fff;border-color:var(--accent)}.primary:hover:enabled{background:var(--accent-hover)}.tabs{display:flex;flex-wrap:wrap;gap:8px;margin:24px 0}.tabs button{background:transparent;border-color:transparent}.tabs .active{background:var(--accent-soft);color:#425e31;border-color:#d5e3c6}.practice-grid{display:grid;grid-template-columns:minmax(270px,.78fr) minmax(0,1.6fr);gap:20px}.filters{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px}label{display:flex;flex-direction:column;gap:8px;font-size:13px;margin-bottom:12px}select{min-width:0;width:100%;background:#fbfcf9;color:#334d31;border:1px solid #dce6d6;border-radius:9px;padding:10px}.problem-title{margin:24px 0 12px}.problem-title>span,.panel-title>span{font-size:14px;color:var(--text-muted)}.problem-title h2{margin:6px 0}.tags{display:flex;flex-wrap:wrap;gap:6px}.tags span{font-size:14px;padding:4px 8px;border-radius:6px;background:#eff4e9;color:#61754d}.statement{font-size:14px;white-space:pre-wrap}.example{background:#f7faf3;padding:14px;border-radius:9px}.example>span{font-size:14px;color:var(--text-muted)}pre{font:12px/1.7 Consolas,'Microsoft YaHei',monospace;margin:6px 0 12px;white-space:pre-wrap;overflow-wrap:anywhere;background:#f7faf3;border-radius:8px;padding:12px;max-height:300px;overflow:auto}.example pre{padding:4px 0}.editor-actions,.row-actions,.review-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.editor-actions{margin-top:16px}.panel-title{margin-bottom:10px}.panel-title h2{margin-bottom:0}.wrong-row,.history-row{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:18px 0;border-bottom:1px solid #e6ece1}.wrong-row h3,.history-row h3{margin:0 0 5px}.wrong-row p,.history-row p{font-size:14px;color:var(--text-muted);margin:4px 0}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:20px 0}.metrics>div{border:1px solid #e1e8da;border-radius:10px;background:#fafcf6;padding:14px}.metrics span{display:block;font-size:14px;color:var(--text-muted)}.metrics strong{display:block;font-size:26px;margin-top:8px}.metrics .state-text{font-size:20px}.verdict{font-size:14px;border:1px solid #e1d7ca;border-radius:6px;padding:3px 8px;margin-left:8px;color:#896443;background:#fbf7ed}.accepted{color:#55753a!important}.verdict.accepted{border-color:#d7e6c9;background:#f0f7e9}.test-list details{border:1px solid #e0e7d9;border-radius:10px;margin:10px 0;padding:12px}.test-list summary{display:flex;gap:12px;justify-content:space-between;align-items:center;cursor:pointer;font-size:14px;flex-wrap:wrap}.test-list summary>span:first-child{flex:1;min-width:100px}.test-list strong{color:#9a7049}.test-evidence{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:10px}h4{font-size:14px;margin:10px 0}.compile-log,.submitted-code{margin:16px 0;font-size:13px}summary{cursor:pointer;line-height:1.6}.feedback{border-top:1px solid #e1e8da;margin-top:24px;padding-top:8px}.feedback ul{font-size:13px;line-height:1.8;padding-left:20px;overflow-wrap:anywhere}.feedback p{font-size:13px}.feedback-label{color:var(--accent);font-weight:600}.consent{flex-direction:row;align-items:flex-start;line-height:1.7;font-size:14px;margin-top:12px;max-width:100%}.consent input{margin-top:4px;accent-color:var(--accent);flex-shrink:0}textarea{min-height:110px;border:1px solid #dce6d6;border-radius:9px;padding:12px;resize:vertical;max-width:100%;background:#fbfcf9;color:#3a5035}.category-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;margin:20px 0}.category-grid article{padding:14px;background:#f9fbf5;border:1px solid #e0e8d9;border-radius:10px}.category-grid h3{margin:0 0 8px}.category-grid p,.category-grid span{font-size:14px;color:var(--text-muted)}.category-grid progress{display:block;width:100%;height:7px;margin:10px 0;accent-color:var(--accent)}.trend{font-size:13px;line-height:2;padding-left:20px}.event-list{padding:0;list-style:none;font-size:14px}.event-list li{display:flex;gap:16px;flex-wrap:wrap;border-bottom:1px solid #e4eadf;padding:12px 0}.event-list span{color:var(--text-muted)}.empty{color:var(--text-muted);padding:28px 0;text-align:center}@media(max-width:1024px){.coding-page{padding:22px}.practice-grid{grid-template-columns:1fr}.problem-panel .statement{max-width:80ch}}@media(max-width:600px){.coding-page{padding:16px 10px}.page-heading{align-items:flex-start}.page-heading h1{font-size:25px}.page-heading>button{flex-shrink:0}.panel{padding:16px}.environment{align-items:flex-start;flex-direction:column;gap:12px}.metrics{grid-template-columns:1fr}.test-evidence{grid-template-columns:1fr}.wrong-row,.history-row,.panel-title{align-items:flex-start;flex-direction:column;gap:12px}.tabs{gap:4px}.tabs button{padding:8px 10px}.editor-actions{align-items:flex-start}.code-panel .panel-title{flex-direction:row}}
</style>
