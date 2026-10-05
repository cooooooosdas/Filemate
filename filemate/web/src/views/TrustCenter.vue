<template>
  <div class="trust-page">
    <header class="hero">
      <div class="hero-copy">
        <h1>可信与隐私</h1>
        <p class="lead">查看资料授权、任务处理过程，以及系统保存的记忆。</p>
        <div class="mode-line">
          <span class="pulse" aria-hidden="true" />
          <strong>{{ modeTitle }}</strong>
          <span>{{ modeDescription }}</span>
        </div>
      </div>
    </header>

    <div v-if="loading" class="state" aria-live="polite">正在读取本地可信记录…</div>
    <DataState v-else-if="error" :error="error" @retry="load" />
    <template v-else-if="data">
      <section class="guarantee-strip" aria-label="数据边界">
        <article v-for="(item, index) in data.guarantees" :key="item">
          <span>0{{ index + 1 }}</span><p>{{ humanizeGuarantee(item) }}</p>
        </article>
      </section>
      <PersonalDataPanel v-if="personalDataEnabled" @restored="load" />
      <AccountPrivacyPanel />

      <section class="workspace-grid">
        <article class="panel trace-panel">
          <div class="section-head">
            <div><p class="eyebrow">任务记录</p><h2>处理过程</h2></div>
            <span>{{ data.runs.length }} 次任务</span>
          </div>
          <div v-if="data.runs.length" class="run-list">
            <article v-for="run in data.runs" :key="run.run_id" class="run-card">
              <button type="button" class="run-summary" :aria-expanded="expandedRun === run.run_id" @click="toggleRun(run.run_id)">
                <span class="run-mark">{{ taskMark(run.task_type) }}</span>
                <span class="run-copy"><strong>{{ run.goal }}</strong><small>{{ taskLabel(run.task_type) }} · {{ formatDate(run.updated_at) }}</small></span>
                <span class="agent-stack"><i v-for="agent in run.selected_agents" :key="agent">{{ assistantLabel(agent) }}</i></span>
                <span class="status" :class="run.status">{{ runStatus(run.status) }}</span>
              </button>
              <ol v-if="expandedRun === run.run_id" class="steps">
                <li v-for="step in run.steps" :key="step.step_id">
                  <span>{{ step.sequence }}</span>
                  <div><strong>{{ assistantLabel(step.agent_name) }}</strong><p>{{ step.output_summary }}</p><small>只保存 {{ Object.keys(step.input_refs).length }} 个来源标识，不保存原文</small></div>
                </li>
                <li v-if="!run.steps.length" class="empty-step">尚无已完成步骤</li>
              </ol>
            </article>
          </div>
          <div v-else class="empty">完成一场模拟面试或声明资料授权后，这里会显示处理过程。</div>
        </article>

        <aside class="panel roles-panel">
          <div class="section-head"><div><p class="eyebrow">协作分工</p><h2>六位专业助手</h2></div><span>按任务选择</span></div>
          <p class="roles-intro">系统会根据当前任务安排需要的助手。</p>
          <div class="role-map">
            <article v-for="(role, index) in data.roles" :key="role.name">
              <span>{{ String(index + 1).padStart(2, '0') }}</span>
              <div><strong>{{ assistantLabel(role.name) }}</strong><p>{{ role.responsibility }}</p></div>
            </article>
          </div>
        </aside>
      </section>

      <section class="panel rights-panel">
        <div class="section-head">
          <div><p class="eyebrow">知识版权</p><h2>资料授权与分享边界</h2></div>
          <span>默认：未确认 · 仅自己可用</span>
        </div>
        <div v-if="data.source_rights.length" class="rights-list">
          <article v-for="source in data.source_rights" :key="source.source_id">
            <div class="source-title"><span>{{ fileSuffix(source.original_name) }}</span><div><strong>{{ source.original_name }}</strong><small>{{ rightsHint(drafts[source.source_id]?.rights_status || source.rights_status) }}</small></div></div>
            <label><span>资料来源</span><select v-model="drafts[source.source_id].rights_status" :name="`rights_${source.source_id}`" @change="enforcePrivate(source.source_id)"><option value="unconfirmed">暂未确认</option><option value="self_owned">本人资料</option><option value="authorized">已获授权</option><option value="public">公开资料</option></select></label>
            <label><span>分享范围</span><select v-model="drafts[source.source_id].sharing_scope" :name="`sharing_${source.source_id}`" :disabled="drafts[source.source_id].rights_status === 'unconfirmed'"><option value="private">仅自己可用</option><option value="restricted">授权范围内</option><option value="shareable">允许分享</option></select></label>
            <label class="note"><span>备注</span><input v-model.trim="drafts[source.source_id].note" :name="`note_${source.source_id}`" maxlength="500" placeholder="可选：授权说明或公开来源" /></label>
            <button type="button" :disabled="savingSource === source.source_id" @click="saveRights(source)">{{ savingSource === source.source_id ? '校验中…' : '保存声明' }}</button>
          </article>
        </div>
        <div v-else class="empty">知识库暂无资料。导入后，系统会先按“未确认、仅自己可用”处理。</div>
      </section>

      <section class="panel memory-panel">
        <div class="section-head">
          <div><p class="eyebrow">可以撤销</p><h2>系统记住了什么</h2></div>
          <span>{{ data.memories.length }} 条摘要记忆</span>
        </div>
        <div v-if="data.memories.length" class="memory-grid">
          <article v-for="memory in data.memories" :key="memory.memory_id">
            <div class="memory-meta"><span>{{ memoryLabel(memory.memory_type) }}</span><small>{{ formatDate(memory.created_at) }}</small></div>
            <p>{{ memory.summary }}</p>
            <div class="memory-scope"><span>使用范围</span><i v-for="agent in memory.allowed_agents" :key="agent">{{ assistantLabel(agent) }}</i></div>
            <button type="button" :disabled="deletingMemory === memory.memory_id" @click="removeMemory(memory)">{{ deletingMemory === memory.memory_id ? '撤销中…' : '撤销这条记忆' }}</button>
          </article>
        </div>
        <div v-else class="empty">当前没有可复用的摘要记忆。</div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import DataState from '../components/DataState.vue'
import PersonalDataPanel from '../components/PersonalDataPanel.vue'
import AccountPrivacyPanel from '../components/AccountPrivacyPanel.vue'
const personalDataEnabled = import.meta.env.VITE_ENABLE_PERSONAL_DATA !== 'false'
import {
  deleteAgentMemory,
  getTrustOverview,
  updateSourceRights,
  type AgentMemory,
  type SourceRights,
  type SourceRightsStatus,
  type SourceSharingScope,
  type TrustOverview
} from '../services/api'

function assistantLabel(value: string): string {
  const labels: Record<string, string> = {
    Planner: '规划助手', Retrieval: '资料助手', Coach: '学习助手',
    Interviewer: '面试助手', Evaluator: '评价助手', Safety: '安全助手'
  }
  const name = value.replace(/\s*Agent$/i, '')
  return labels[name] || `${name}助手`
}

function humanizeGuarantee(value: string): string {
  return value.replaceAll('Agent', '助手').replaceAll('智能协作', '任务协作')
}

interface RightsDraft {
  rights_status: SourceRightsStatus
  sharing_scope: SourceSharingScope
  note: string
}

const data = ref<TrustOverview | null>(null)
const loading = ref(true)
const error = ref('')
const expandedRun = ref('')
const savingSource = ref('')
const deletingMemory = ref('')
const drafts = ref<Record<string, RightsDraft>>({})

const modeTitle = computed(() => data.value?.mode === 'local' ? '隐私模式' : '本地优先 · 增强模式')
const modeDescription = computed(() => data.value?.mode === 'local' ? '面试评分仅使用本地规则' : '资料本地保存，明确调用时可使用外部模型')
const formatDate = (value: string) => new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
const fileSuffix = (name: string) => name.includes('.') ? name.split('.').pop()!.slice(0, 4).toUpperCase() : 'DOC'
const taskMark = (type: string) => ({ interview_session: '问', source_rights: '权', memory_deletion: '删' }[type] || '协')
const taskLabel = (type: string) => ({ interview_session: '模拟面试', source_rights: '资料授权', memory_deletion: '记忆撤销' }[type] || type)
const runStatus = (status: string) => ({ running: '进行中', completed: '已完成', failed: '需检查' }[status] || status)
const memoryLabel = (type: string) => ({ session: '会话记忆', knowledge: '知识记忆', growth: '成长记忆', operation: '操作记忆' }[type] || type)
const rightsHint = (status: SourceRightsStatus) => ({ unconfirmed: '尚未确认权利来源，保持私有', self_owned: '由本人创建或持有', authorized: '已取得使用授权', public: '来自公开发布资料' }[status])

function syncDrafts(sources: SourceRights[]): void {
  drafts.value = Object.fromEntries(sources.map(source => [source.source_id, {
    rights_status: source.rights_status,
    sharing_scope: source.sharing_scope,
    note: source.note
  }]))
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    data.value = await getTrustOverview()
    syncDrafts(data.value.source_rights)
    expandedRun.value = data.value.runs[0]?.run_id || ''
  } catch (cause: any) {
    error.value = cause?.message || '可信与隐私数据加载失败'
  } finally {
    loading.value = false
  }
}

function toggleRun(runId: string): void {
  expandedRun.value = expandedRun.value === runId ? '' : runId
}

function enforcePrivate(sourceId: string): void {
  const draft = drafts.value[sourceId]
  if (draft?.rights_status === 'unconfirmed') draft.sharing_scope = 'private'
}

async function saveRights(source: SourceRights): Promise<void> {
  const draft = drafts.value[source.source_id]
  if (!draft) return
  savingSource.value = source.source_id
  try {
    await updateSourceRights(source.source_id, draft.rights_status, draft.sharing_scope, draft.note)
    ElMessage.success('授权声明已校验并保存')
    await load()
  } catch (cause: any) {
    ElMessage.error(cause?.message || '保存失败')
  } finally {
    savingSource.value = ''
  }
}

async function removeMemory(memory: AgentMemory): Promise<void> {
  try {
    await ElMessageBox.confirm('撤销后，这条摘要将不再提供给后续助手。已有原始学习记录不会被删除。', '撤销共享记忆', { confirmButtonText: '确认撤销', cancelButtonText: '取消', type: 'warning' })
  } catch {
    return
  }
  deletingMemory.value = memory.memory_id
  try {
    await deleteAgentMemory(memory.memory_id)
    ElMessage.success('共享记忆已撤销')
    await load()
  } catch (cause: any) {
    ElMessage.error(cause?.message || '撤销失败')
  } finally {
    deletingMemory.value = ''
  }
}

onMounted(load)
</script>

<style scoped>
.trust-page{max-width:1180px;margin:0 auto;padding:28px;color:var(--text-primary)}.hero{position:relative;min-height:280px;display:flex;align-items:center;justify-content:space-between;gap:40px;overflow:hidden;padding:42px 54px;border:1px solid rgba(50,112,92,.14);border-radius:24px;background:radial-gradient(circle at 86% 22%,rgba(77,151,218,.2),transparent 34%),linear-gradient(135deg,#f6fbff 0%,#eef9f2 58%,#e7f5f0 100%)}.hero:before{content:"";position:absolute;right:-80px;bottom:-180px;width:420px;height:420px;border:1px solid rgba(45,121,96,.14);border-radius:50%;box-shadow:0 0 0 38px rgba(255,255,255,.22),0 0 0 76px rgba(255,255,255,.18)}.hero-copy{position:relative;z-index:1;max-width:720px}.eyebrow{margin:0;color:var(--accent);font-size:11px;font-weight:850;letter-spacing:.15em}.hero h1{margin:14px 0 13px;font-size:39px;line-height:1.18;letter-spacing:-.035em}.hero h1 em{color:var(--accent);font-style:normal}.lead{margin:0;color:var(--text-secondary);font-size:16px}.mode-line{display:flex;align-items:center;gap:9px;margin-top:25px;color:var(--text-secondary);font-size:12px}.mode-line strong{color:var(--text-primary)}.pulse{width:8px;height:8px;border-radius:50%;background:#27a475;box-shadow:0 0 0 5px rgba(39,164,117,.12)}.trust-seal{position:relative;z-index:1;width:142px;height:142px;flex:0 0 142px;display:flex;align-items:center;justify-content:center;flex-direction:column;border:1px solid rgba(40,108,88,.2);border-radius:50%;background:rgba(255,255,255,.58);box-shadow:inset 0 0 0 9px rgba(255,255,255,.45),0 18px 40px rgba(51,107,91,.12);backdrop-filter:blur(10px)}.trust-seal span{font-size:9px;letter-spacing:.24em;color:var(--accent)}.trust-seal strong{font-size:29px;margin:3px 0}.trust-seal small{color:var(--text-muted)}.state,.empty{padding:48px;text-align:center;color:var(--text-muted)}.guarantee-strip{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;margin:16px 0;background:var(--border-subtle);border:1px solid var(--border-subtle);border-radius:16px;overflow:hidden}.guarantee-strip article{display:flex;gap:12px;min-height:94px;padding:18px;background:var(--bg-surface)}.guarantee-strip span{font:700 11px/1.5 ui-monospace,monospace;color:var(--accent)}.guarantee-strip p{margin:0;color:var(--text-secondary);font-size:12px;line-height:1.65}.panel{background:var(--bg-surface);border:1px solid var(--border-subtle);border-radius:18px;padding:24px}.workspace-grid{display:grid;grid-template-columns:1.45fr .82fr;gap:16px}.section-head{display:flex;align-items:end;justify-content:space-between;gap:16px}.section-head h2{margin:5px 0 0;font-size:20px}.section-head>span{color:var(--text-muted);font-size:11px}.run-list{display:grid;gap:10px;margin-top:20px}.run-card{border:1px solid var(--border-subtle);border-radius:13px;overflow:hidden}.run-summary{width:100%;display:grid;grid-template-columns:38px minmax(0,1fr) auto auto;align-items:center;gap:12px;padding:14px;border:0;background:transparent;color:var(--text-primary);text-align:left;cursor:pointer}.run-summary:hover{background:var(--bg-base)}.run-mark{width:34px;height:34px;display:grid;place-items:center;border-radius:10px;background:var(--accent-soft);color:var(--accent);font-weight:800}.run-copy{min-width:0;display:flex;flex-direction:column;gap:4px}.run-copy strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px}.run-copy small{color:var(--text-muted)}.agent-stack{display:flex}.agent-stack i{margin-left:-4px;padding:4px 7px;border:2px solid white;border-radius:999px;background:#edf7f2;color:#28765e;font-size:9px;font-style:normal}.status{padding:4px 7px;border-radius:999px;background:#eef7f3;color:#28765e;font-size:10px}.status.running{background:#fff5db;color:#9a6a0b}.status.failed{background:#fff0ed;color:#b04733}.steps{position:relative;margin:0;padding:2px 18px 16px 64px;list-style:none;background:linear-gradient(90deg,#f6faf8,transparent)}.steps:before{content:"";position:absolute;left:31px;top:4px;bottom:24px;width:1px;background:var(--accent-border)}.steps li{position:relative;display:flex;gap:14px;padding:13px 0}.steps li>span{position:absolute;left:-47px;width:28px;height:28px;display:grid;place-items:center;border:1px solid var(--accent-border);border-radius:50%;background:white;color:var(--accent);font-size:10px}.steps strong{font-size:12px}.steps p{margin:5px 0;color:var(--text-secondary);font-size:12px;line-height:1.55}.steps small{color:var(--text-muted);font-size:10px}.roles-intro{margin:15px 0;color:var(--text-secondary);font-size:12px;line-height:1.65}.role-map{display:grid;gap:2px}.role-map article{display:flex;gap:12px;padding:11px 0;border-top:1px solid var(--border-subtle)}.role-map article>span{color:var(--accent);font:700 10px/1.5 ui-monospace,monospace}.role-map strong{font-size:12px}.role-map p{margin:3px 0 0;color:var(--text-muted);font-size:10px;line-height:1.45}.rights-panel,.memory-panel{margin-top:16px}.rights-list{display:grid;gap:9px;margin-top:20px}.rights-list>article{display:grid;grid-template-columns:minmax(200px,1.2fr) 150px 150px minmax(170px,1fr) auto;gap:10px;align-items:end;padding:14px;border:1px solid var(--border-subtle);border-radius:12px}.source-title{min-width:0;display:flex;align-items:center;gap:11px}.source-title>span{width:39px;height:43px;display:grid;place-items:center;flex:0 0 auto;border-radius:8px;background:var(--brand-blue-soft);color:var(--brand-blue-strong);font-size:9px;font-weight:800}.source-title div{min-width:0;display:flex;flex-direction:column;gap:4px}.source-title strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}.source-title small{color:var(--text-muted);font-size:10px}.rights-list label{display:grid;gap:5px}.rights-list label>span{color:var(--text-muted);font-size:10px}.rights-list select,.rights-list input{width:100%;height:36px;box-sizing:border-box;border:1px solid var(--border-default);border-radius:8px;padding:0 9px;background:var(--bg-base);color:var(--text-primary);font-size:11px}.rights-list select:disabled{opacity:.55}.rights-list button,.memory-grid button{height:36px;border:1px solid var(--accent-border);border-radius:8px;padding:0 12px;background:var(--accent-soft);color:var(--accent);font-size:11px;cursor:pointer}.rights-list button:disabled,.memory-grid button:disabled{opacity:.5}.memory-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:20px}.memory-grid article{display:flex;flex-direction:column;min-height:160px;padding:16px;border:1px solid var(--border-subtle);border-radius:13px;background:linear-gradient(145deg,#fff,#f8fbfa)}.memory-meta{display:flex;justify-content:space-between}.memory-meta span{color:var(--accent);font-size:10px;font-weight:800}.memory-meta small{color:var(--text-muted);font-size:10px}.memory-grid p{flex:1;margin:13px 0;color:var(--text-secondary);font-size:12px;line-height:1.65}.memory-scope{display:flex;align-items:center;gap:5px;flex-wrap:wrap;margin-bottom:12px}.memory-scope span{color:var(--text-muted);font-size:9px}.memory-scope i{padding:3px 6px;border-radius:999px;background:var(--accent-soft);color:var(--accent);font-size:9px;font-style:normal}.memory-grid button{align-self:flex-start;background:transparent;color:var(--text-muted)}@media(max-width:1050px){.workspace-grid{grid-template-columns:1fr}.rights-list>article{grid-template-columns:1fr 1fr 1fr}.source-title{grid-column:1/-1}.note{grid-column:1/3}.memory-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:760px){.trust-page{padding:16px}.hero{min-height:auto;padding:30px}.hero h1{font-size:31px}.trust-seal{display:none}.guarantee-strip{grid-template-columns:1fr 1fr}.run-summary{grid-template-columns:38px 1fr auto}.agent-stack{grid-column:2/4}.rights-list>article{grid-template-columns:1fr}.source-title,.note{grid-column:auto}.memory-grid{grid-template-columns:1fr}}@media(max-width:480px){.guarantee-strip{grid-template-columns:1fr}.panel{padding:18px}.run-summary{grid-template-columns:34px 1fr}.status{grid-column:2}.agent-stack{grid-column:2}}
</style>
