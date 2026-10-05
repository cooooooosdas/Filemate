<template>
  <div class="portfolio-page">
    <header><div><p class="eyebrow">从事实出发</p><h1>我的简历</h1><p>经历由你确认，AI 帮你选材排序。</p></div><RouterLink to="/career">回到求职训练</RouterLink></header>
    <p v-if="loading" role="status">正在读取个人事实…</p>
    <DataState v-else-if="loadError" :error="loadError" @retry="load" />
    <div v-else class="portfolio-grid">
      <form class="portfolio-panel" @submit.prevent="save">
        <h2>个人事实</h2><p>填写能如实说明的内容。这些信息独立于学习能力画像。</p>
        <div class="field-grid">
          <label>姓名<input v-model="profile.name" required maxlength="80" autocomplete="name"></label>
          <label>学校<input v-model="profile.school" required maxlength="160"></label>
          <label>专业<input v-model="profile.major" maxlength="120"></label>
          <label>学历<input v-model="profile.degree" maxlength="80"></label>
          <label>就读时间<input v-model="profile.education_period" maxlength="80" placeholder="如 2023–2027"></label>
          <label>目标岗位<input v-model="profile.target_role" maxlength="160"></label>
          <label>联系邮箱<input v-model="profile.email" type="email" maxlength="254" autocomplete="email"></label>
          <label>联系电话<input v-model="profile.phone" maxlength="40" autocomplete="tel"></label>
        </div>
        <label>技能（每行一项，最多40项）<textarea v-model="skillsText" rows="3" maxlength="4840"></textarea></label>
        <div class="section-head"><h2>项目经历</h2><button type="button" :disabled="profile.projects.length >= 30" @click="addProject">添加项目</button></div>
        <fieldset v-for="(project, index) in profile.projects" :key="project.project_id">
          <legend>项目 {{ index + 1 }}</legend>
          <label>项目名称<input v-model="project.title" required maxlength="120"></label>
          <label>承担角色<input v-model="project.role" maxlength="120"></label>
          <label>实际工作与成果<textarea v-model="project.description" required maxlength="3000" rows="3"></textarea></label>
          <label>关联编程记录（可选）<select v-model="project.submission_id" :aria-label="`项目${index + 1}关联编程记录`"><option :value="null">不关联</option><option v-for="work in works" :key="work.submission_id" :value="work.submission_id">{{ work.problem_id }} · {{ work.result.verdict || '未判题' }} · {{ work.created_at.slice(0,10) }}</option><option v-if="project.submission_id && !works.some(w => w.submission_id === project.submission_id)" :value="project.submission_id">已保存的关联记录（保存时重新校验）</option></select></label>
          <button type="button" @click="removeProject(index)">移除此项目</button>
        </fieldset>
        <p v-if="worksError" role="status">编程记录暂不可用，已有个人事实保留。{{ worksError }}</p>
        <p v-if="actionError" role="alert">{{ actionError }}</p>
        <button class="primary" :disabled="busy">{{ busy ? '处理中…' : '保存个人事实' }}</button><span role="status">{{ savedMessage }}</span>
      </form>
      <section class="portfolio-panel">
        <h2>生成与回看</h2><p v-if="dirty">有未保存的修改，请先保存个人事实。</p><p v-else>已保存版本 {{ profile.revision || '暂无' }}。直接排版不会调用模型。</p>
        <label>生成方式<select v-model="mode" aria-label="生成方式"><option value="local">直接排版全部事实</option><option value="llm">AI 按目标岗位选材排序</option></select></label>
        <label v-if="mode === 'llm'" class="consent"><input v-model="consent" type="checkbox">同意将教育、技能、项目事实及目标岗位发送给已配置模型；姓名和联系方式字段不发送，项目描述请自行去除敏感信息。</label>
        <button class="primary" type="button" :disabled="busy || dirty || !profile.revision || (mode === 'llm' && !consent)" @click="generate">生成简历</button>
        <div v-if="document" class="resume-preview"><p>{{ document.mode === 'llm' ? 'AI 选材' : '直接排版' }} · 事实版本 {{ document.profile_revision }}</p><pre>{{ document.markdown }}</pre><p class="notice">{{ document.fact_policy }}关联判题记录为生成时快照。</p><div class="actions"><button type="button" @click="download('markdown')">导出 Markdown</button><button type="button" @click="download('json')">导出 JSON</button></div></div>
        <p v-else class="notice">还没有简历。保存个人事实后即可生成；模型失败时不会覆盖旧简历。</p>
        <h3>最近30份简历</h3><ul class="document-list"><li v-for="item in history" :key="item.artifact_id"><button type="button" :disabled="busy" @click="open(item.artifact_id)">{{ item.title }} · {{ item.created_at.slice(0,10) }}</button></li></ul><p v-if="!history.length">暂无保存记录。</p>
      </section>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import DataState from '../components/DataState.vue'
import { exportResume, generateResume, getCodingOverview, getResume, getResumeProfile, getResumes, saveResumeProfile } from '../services/api'
import type { ResumeDocument, ResumeProfile, SavedDocument } from '../types/portfolio'
import type { CodingSubmission } from '../types/programming'
const profile = ref<ResumeProfile>({ schema_version: 1, revision: 0, name: '', school: '', major: '', degree: '', education_period: '', target_role: '', email: '', phone: '', skills: [], projects: [] })
const skillsText = ref(''), baseline = ref(''), loading = ref(true), busy = ref(false), loadError = ref(''), actionError = ref(''), savedMessage = ref(''), worksError = ref('')
const works = ref<CodingSubmission[]>([]), document = ref<ResumeDocument | null>(null), history = ref<SavedDocument[]>([]), mode = ref<'local' | 'llm'>('local'), consent = ref(false)
const edited = computed(() => ({ ...profile.value, skills: skillsText.value.split('\n').map(s => s.trim()).filter(Boolean) }))
const dirty = computed(() => JSON.stringify(edited.value) !== baseline.value)
async function load() { loading.value = true; loadError.value = ''; try { const result = await getResumeProfile(); if (result) profile.value = result; skillsText.value = profile.value.skills.join('\n'); baseline.value = JSON.stringify(edited.value); history.value = await getResumes() } catch (e: any) { loadError.value = e.message } finally { loading.value = false }; try { works.value = (await getCodingOverview()).submissions.filter(w => w.active && !w.data_error) } catch (e: any) { worksError.value = e.message } }
function addProject() { profile.value.projects.push({ project_id: crypto.randomUUID(), title: '', role: '', description: '', submission_id: null }) }
async function removeProject(index: number) { try { await ElMessageBox.confirm('移除后需保存才会生效，旧简历快照保留。', '移除项目', { confirmButtonText: '确认移除', cancelButtonText: '取消' }); profile.value.projects.splice(index, 1) } catch {} }
async function perform(action: () => Promise<void>) { busy.value = true; actionError.value = ''; savedMessage.value = ''; try { await action() } catch (e: any) { actionError.value = e.message || '操作失败，原记录保留' } finally { busy.value = false } }
const save = () => perform(async () => { profile.value = await saveResumeProfile(edited.value); skillsText.value = profile.value.skills.join('\n'); baseline.value = JSON.stringify(edited.value); savedMessage.value = '个人事实已保存' })
const generate = () => perform(async () => { document.value = await generateResume(profile.value.revision, mode.value, consent.value); history.value = await getResumes(); savedMessage.value = '简历已保存' })
const open = (id: string) => perform(async () => { document.value = await getResume(id) })
const download = (format: 'markdown' | 'json') => perform(async () => { if (!document.value) return; const blob = await exportResume(document.value.artifact_id, format); const url = URL.createObjectURL(blob as unknown as Blob); const link = window.document.createElement('a'); link.href = url; link.download = `resume.${format === 'markdown' ? 'md' : 'json'}`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000) })
onMounted(load)
</script>
<style src="../styles/portfolio.css"></style>
