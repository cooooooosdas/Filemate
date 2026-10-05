<template>
  <div class="skills-page">
    <header><div><p class="eyebrow">把能力目标落在证据上</p><h1>我的技能树</h1><p>自定义能力目标与前置条件，用课程练习、编程和面试记录核对进度。</p></div><button :disabled="loading || saving" @click="load">刷新证据</button></header>
    <DataState v-if="error" :error="error" @retry="load" />
    <p v-if="loading" role="status">正在读取技能与验收证据…</p>
    <template v-else-if="tree">
      <p class="rule">{{ tree.rule }}</p>
      <form class="skill-form" @submit.prevent="addSkill">
        <h2>{{ editingId ? '调整能力目标' : '下一项能力目标' }}</h2>
        <label>技能名称<input v-model.trim="label" required maxlength="120" placeholder="例如：独立实现二分查找" /></label>
        <label>验收说明<textarea v-model.trim="description" maxlength="1000" rows="2" placeholder="写清楚你希望完成什么" /></label>
        <fieldset v-if="tree.skills.length"><legend>先修技能（可选）</legend><label v-for="skill in tree.skills.filter(item => item.skill_id !== editingId)" :key="skill.skill_id"><input v-model="prerequisites" type="checkbox" :value="skill.skill_id" />{{ skill.label }}</label></fieldset>
        <label>关联验收记录<select v-model="target" aria-label="关联验收记录"><option value="">稍后关联，保持待评测</option><option v-for="(item, index) in targets" :key="index" :value="targetKey(item)">{{ item.label }}</option></select></label>
        <label>查找全部验收记录<input v-model.trim="targetQuery" maxlength="160" placeholder="题干、题集标题、编程题或岗位名" @keydown.enter.prevent="searchTargets" /></label><button type="button" :disabled="saving" @click="searchTargets">搜索验收记录</button>
        <label v-if="target !== ''">所需正确作答 / 面试回答次数<input v-model.number="requiredSuccesses" type="number" min="1" max="20" :disabled="targets.find(item => targetKey(item) === target)?.kind === 'coding'" /></label>
        <button class="primary" :disabled="saving || !label || !editingId && tree.skills.length >= 200">{{ saving ? '保存中…' : editingId ? '保存目标调整' : '加入技能树' }}</button>
        <button v-if="editingId" type="button" :disabled="saving" @click="clearDraft">取消调整</button>
      </form>
      <p v-if="!tree.skills.length" class="empty">还没有能力目标。建立第一个技能后，它会保存在当前学习空间；没有证据时保持待评测。</p>
      <section class="skill-grid" aria-label="技能与前置关系">
        <article v-for="skill in tree.skills" :key="skill.skill_id">
          <span class="state">{{ states[tree.states[skill.skill_id] || ''] || '待评测' }}</span><h2>{{ skill.label }}</h2><p>{{ skill.description }}</p>
          <p v-if="skill.prerequisites.length">先修：{{ skill.prerequisites.map(id => names.get(id) || '缺失技能').join('、') }}</p>
          <ul v-if="tree.evidence[skill.skill_id]?.length"><li v-for="(evidence, index) in tree.evidence[skill.skill_id]" :key="index"><span>{{ evidence.available ? `${evidence.observed_successes} / ${evidence.required_successes} 条验收记录` : '关联记录已删除或不可用' }}</span><RouterLink v-for="record in evidence.records" :key="record.record_id" :to="record.href">回看证据</RouterLink><button :disabled="saving" @click="detach(skill, index)">解除关联</button></li></ul>
          <form @submit.prevent="attach(skill)"><label>补充验收证据<select v-model="attachment[skill.skill_id]"><option value="">选择已有练习或训练</option><option v-for="(item, index) in targets" :key="index" :value="targetKey(item)">{{ item.label }}</option></select></label><button :disabled="saving || !attachment[skill.skill_id] && attachment[skill.skill_id] !== '0'">关联</button></form>
          <button :disabled="saving" @click="edit(skill)">调整目标与先修</button><button :disabled="saving" @click="remove(skill)">移除目标</button>
        </article>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, shallowRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import DataState from '../components/DataState.vue'
import { getSkillTargets, getSkillTree, saveSkillTree } from '../services/api'
import type { Skill, SkillCriterion, SkillTarget, SkillTree } from '../types/skills'
const tree = shallowRef<SkillTree | null>(null), targets = shallowRef<SkillTarget[]>([])
const loading = ref(false), saving = ref(false), error = ref(''), label = ref(''), description = ref(''), target = ref(''), requiredSuccesses = ref(1), prerequisites = ref<string[]>([]), attachment = ref<Record<string,string>>({})
const editingId = ref('')
const targetQuery = ref('')
const names = computed(() => new Map(tree.value?.skills.map(skill => [skill.skill_id, skill.label])))
const states: Record<string,string> = { conditions_met: '验收条件达成', prerequisites_pending: '先修条件待完成', pending_assessment: '待评测', in_progress: '继续练习' }
async function load() { loading.value = true; error.value = ''; try { const [data, records] = await Promise.all([getSkillTree(), getSkillTargets()]); tree.value = data; targets.value = records } catch (cause: any) { error.value = cause.message || '读取失败' } finally { loading.value = false } }
async function searchTargets() { try { targets.value = await getSkillTargets(targetQuery.value) } catch (cause: any) { ElMessage.error(cause.message || '搜索失败') } }
function targetKey(item: SkillTarget): string { return `${item.kind}:${item.target_id}:${item.question_index ?? -1}` }
function criterion(index: string): SkillCriterion | null { const record = targets.value.find(item => targetKey(item) === index); return index !== '' && record ? { kind: record.kind, target_id: record.target_id, question_index: record.question_index, required_successes: record.kind === 'coding' ? 1 : requiredSuccesses.value } : null }
async function save(skills: Skill[]): Promise<boolean> { if (!tree.value || saving.value) return false; saving.value = true; try { tree.value = await saveSkillTree({ schema_version: 1, revision: tree.value.revision, skills }); ElMessage.success('技能目标已保存'); return true } catch (cause: any) { ElMessage.error(cause.message || '保存失败，请刷新后重试'); return false } finally { saving.value = false } }
function clearDraft() { editingId.value = ''; label.value = ''; description.value = ''; prerequisites.value = []; target.value = ''; requiredSuccesses.value = 1 }
function edit(skill: Skill) { editingId.value = skill.skill_id; label.value = skill.label; description.value = skill.description; prerequisites.value = [...skill.prerequisites]; target.value = ''; document.querySelector('.skill-form')?.scrollIntoView({ behavior: 'smooth' }) }
async function addSkill() { if (!tree.value) return; const evidence = criterion(target.value); const existing = tree.value.skills.find(item => item.skill_id === editingId.value); const updated: Skill = { skill_id: editingId.value || crypto.randomUUID(), label: label.value, description: description.value, prerequisites: [...prerequisites.value], criteria: [...(existing?.criteria || []), ...(evidence ? [evidence] : [])] }; const skills = editingId.value ? tree.value.skills.map(item => item.skill_id === editingId.value ? updated : item) : [...tree.value.skills, updated]; if (await save(skills)) clearDraft() }
async function detach(skill: Skill, index: number) { if (tree.value) await save(tree.value.skills.map(item => item.skill_id === skill.skill_id ? { ...item, criteria: item.criteria.filter((_, position) => position !== index) } : item)) }
async function attach(skill: Skill) { if (!tree.value) return; const evidence = criterion(attachment.value[skill.skill_id] ?? ''); if (!evidence) return; if (await save(tree.value.skills.map(item => item.skill_id === skill.skill_id ? { ...item, criteria: [...item.criteria, evidence] } : item))) attachment.value[skill.skill_id] = '' }
async function remove(skill: Skill) { if (!tree.value) return; if (tree.value.skills.some(item => item.prerequisites.includes(skill.skill_id))) { ElMessage.warning('请先移除其他目标对此技能的先修引用'); return } try { await ElMessageBox.confirm(`移除「${skill.label}」？课程、代码和面试记录保留。`, '移除技能目标', { confirmButtonText: '移除', cancelButtonText: '取消' }); await save(tree.value.skills.filter(item => item.skill_id !== skill.skill_id)) } catch { /* 用户取消。 */ } }
onMounted(load)
</script>

<style scoped>
.skills-page { color:var(--text-primary); }.skills-page header { display:flex; justify-content:space-between; align-items:start; gap:20px; margin-bottom:24px; }h1 { font-size:clamp(28px,4vw,40px); margin:8px 0; }h2 { font-size:23px; }p { line-height:1.7; overflow-wrap:anywhere; }.eyebrow,.state { color:var(--accent); }.rule,.empty { padding:18px; border:1px solid var(--border-subtle); border-radius:14px; }.skill-form,.skill-grid article { border:1px solid var(--border-subtle); border-radius:18px; background:var(--bg-surface); padding:24px; min-width:0; }.skill-form { display:grid; gap:16px; margin:24px 0; }.skill-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:20px; }label { display:grid; gap:8px; font-size:17px; }input,select,textarea { font:inherit; min-width:0; max-width:100%; padding:12px; border:1px solid var(--border-subtle); border-radius:10px; background:var(--bg-elevated); color:var(--text-primary); }fieldset { display:flex; flex-wrap:wrap; gap:12px; border:1px solid var(--border-subtle); border-radius:12px; }fieldset label { display:flex; align-items:center; }button { font:inherit; min-height:44px; padding:10px 18px; border:1px solid var(--border-subtle); border-radius:10px; color:var(--text-primary); background:var(--bg-surface); cursor:pointer; }.primary { background:var(--accent); color:white; }button:disabled { opacity:.55; cursor:default; }li { margin:14px 0; }li a { display:inline-block; margin-left:12px; color:var(--accent); }article form { display:grid; gap:10px; margin:20px 0; }@media(max-width:768px) { .skill-grid { grid-template-columns:1fr; }.skills-page header { flex-direction:column; } }
</style>
