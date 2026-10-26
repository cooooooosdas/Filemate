<template>
  <article class="learning-artifact">
    <header><div><small>{{ label }}</small><h3>{{ artifact.title }}</h3></div><button type="button" @click="download">导出</button></header>
    <AnalysisWarnings :messages="artifact.metadata?.warnings" />
    <p v-if="artifact.metadata?.source_truncated && !artifact.metadata?.warnings" class="notice">本次内容依据资料前 {{ artifact.metadata.input_characters }} 字生成，未覆盖全文。</p>
    <p v-if="artifact.metadata?.read_only_snapshot" class="notice">这是修改前的历史题集，仅供查看，不能保存新作答。</p>
    <template v-if="artifact.artifact_type === 'knowledge_cards' && cards.length">
      <div class="pager"><span>知识卡 {{ index + 1 }} / {{ cards.length }}</span><div><button :disabled="index === 0" aria-label="上一张卡片" @click="move(-1)">上一张</button><button :disabled="index === cards.length - 1" aria-label="下一张卡片" @click="move(1)">下一张</button></div></div>
      <button class="flashcard" type="button" :aria-expanded="revealed" @click="revealed = !revealed">
        <small>{{ revealed ? '参考解释' : '先回忆，再翻面' }}</small><Transition name="card-recall" mode="out-in"><p :key="`${index}-${revealed}`">{{ revealed ? cards[index]?.back : cards[index]?.front }}</p></Transition><span>{{ revealed ? '返回问题' : '点击查看解释' }}</span>
      </button>
      <p class="muted">翻面用于自主回忆，不会据此推断掌握度。</p>
    </template>
    <template v-else-if="artifact.artifact_type === 'questions' && questions.length">
      <div class="pager"><span>练习 {{ index + 1 }} / {{ questions.length }}</span><div><button :disabled="index === 0" @click="move(-1)">上一题</button><button :disabled="index === questions.length - 1" @click="move(1)">下一题</button></div></div>
      <ReviewEntry v-if="question && active" :key="`${artifact.artifact_id}-${index}`" ref="entry" :artifact-id="artifact.artifact_id" :question-index="index" :question="question" :readonly="!!artifact.metadata?.read_only_snapshot" />
      <p class="muted">作答会保存；此处的本轮答题标记不会跨页面保留。</p>
    </template>
    <div v-else-if="artifact.artifact_type === 'notes' && sections.length" class="note-content"><section v-for="(section, i) in sections" :key="i"><h4>{{ section.title }}</h4><p>{{ section.content }}</p></section></div>
    <p v-else class="read-content">{{ typeof artifact.content === 'string' ? artifact.content : JSON.stringify(artifact.content, null, 2) }}</p>
    <p v-if="error" role="alert" class="error">{{ error }} 请重试。</p>
  </article>
</template>

<script setup lang="ts">
import { saveDownload } from '../services/downloads'
import AnalysisWarnings from './AnalysisWarnings.vue'
import { computed, ref, watch, onDeactivated, onBeforeUnmount, onActivated } from 'vue'
import { ElMessageBox } from 'element-plus'
import type { KnowledgeArtifact } from '../services/api'
import ReviewEntry from './wrongbook/ReviewEntry.vue'
const props = defineProps<{ artifact: KnowledgeArtifact }>()
const index = ref(0), revealed = ref(false), error = ref(''), entry=ref<InstanceType<typeof ReviewEntry>|null>(null), active=ref(true)
const label = computed(() => ({ summary: '摘要', notes: '结构化笔记', knowledge_cards: '主动回忆', questions: '随堂练习' }[props.artifact.artifact_type] || '学习内容'))
const cards = computed(() => Array.isArray(props.artifact.content) ? props.artifact.content : [])
const questions = cards
const question = computed(() => questions.value[index.value])
const sections = computed(() => Array.isArray(props.artifact.content?.sections) ? props.artifact.content.sections : [])
watch(() => [props.artifact.artifact_id,props.artifact.content], () => { entry.value?.invalidate();index.value=0;revealed.value=false;error.value='' })
async function canLeave(){if(!entry.value?.dirty())return true;try{await ElMessageBox.confirm('未提交正文不会保存，在途请求仍可能在服务器完成。是否离开？','保留当前作答？',{confirmButtonText:'离开',cancelButtonText:'继续作答'});return true}catch{return false}}
async function move(offset:number){if(!await canLeave())return;index.value+=offset;revealed.value=false;error.value=''}
function invalidate(){entry.value?.invalidate();active.value=false}
onDeactivated(invalidate);onBeforeUnmount(invalidate);onActivated(()=>{active.value=true})
defineExpose({canLeave,invalidate,dirty:()=>entry.value?.dirty()||false})
function download() {
  const text = typeof props.artifact.content === 'string' ? props.artifact.content : JSON.stringify(props.artifact.content, null, 2)
  void saveDownload(new Blob([text], { type: 'text/plain;charset=utf-8' }), `${props.artifact.title}.txt`)
}
</script>


<style scoped>
.learning-artifact { color: var(--text-primary); min-width: 0; font-size: 18px; }
.learning-artifact header { display: flex; gap: 16px; align-items: flex-start; justify-content: space-between; padding-bottom: 24px; border-bottom: 1px solid var(--border-subtle); }
h3 { font-size: 26px; line-height: 1.5; margin: 8px 0 0; overflow-wrap: anywhere; }
small, .muted { color: var(--text-secondary); font-size: 15px; line-height: 1.8; }
button { font: inherit; font-size: 17px; min-height: 48px; padding: 10px 16px; background: white; border: 1px solid var(--border-subtle); border-radius: 10px; color: inherit; cursor: pointer; }
button:disabled { opacity: .5; cursor: default; }
button:focus-visible, textarea:focus-visible, input:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.pager { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 14px; margin: 24px 0; font-size: 17px; }
.pager > div { display: flex; gap: 10px; }
.flashcard { width: 100%; min-height: 320px; background: radial-gradient(ellipse at 100% 0, #d8eacb, transparent 80%), #ecf4e7; text-align: left; padding: 28px; display: flex; flex-direction: column; justify-content: space-between; border-radius: 20px; border-color: var(--accent-border); }
.flashcard p { font-size: 24px; line-height: 1.85; white-space: pre-wrap; overflow-wrap: anywhere; margin: 22px 0; }
.flashcard span { font-size: 17px; color: var(--accent); }
.primary { background: var(--action-fill, var(--accent)); color: white; margin-top: 20px; border-color: var(--accent); }
h4 { font-size: 24px; line-height: 1.75; margin: 24px 0 18px; }
.read-content, .note-content p { white-space: pre-wrap; line-height: 1.95; font-size: 18px; overflow-wrap: anywhere; }
.note-content section { padding: 8px 0; }
.choice { display: flex; align-items: flex-start; gap: 14px; padding: 18px 16px; margin: 12px 0; border: 1px solid var(--border-subtle); border-radius: 12px; font-size: 18px; line-height: 1.7; cursor: pointer; min-height: 54px; }
.choice:has(input:checked) { border-color: var(--accent); background: var(--accent-soft); }
.choice input { accent-color: var(--accent); flex: 0 0 auto; width: 18px; height: 18px; margin: 5px 0 0; }
.choice span { min-width: 0; overflow-wrap: anywhere; }
fieldset { border: 0; padding: 0; min-width: 0; }
textarea { width: 100%; box-sizing: border-box; padding: 16px; border: 1px solid var(--border-strong); border-radius: 12px; font: inherit; font-size: 18px; line-height: 1.7; resize: vertical; }
.answer-feedback { padding: 22px; background: var(--accent-soft); margin-top: 24px; border-radius: 14px; line-height: 1.85; font-size: 18px; overflow-wrap: anywhere; }
.answer-feedback > strong { font-size: 23px; }
.answer-feedback a { display: inline-flex; align-items: center; min-height: 48px; color: var(--accent); font-size: 17px; }
.notice { padding: 16px; background: #fff8e8; color: #77581d; font-size: 16px; line-height: 1.8; border-radius: 10px; }
.error { color: #a13939; font-size: 17px; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
.card-recall-enter-active, .card-recall-leave-active { transition: opacity .16s ease, transform .16s ease; }
.card-recall-enter-from { opacity: 0; transform: translateY(10px); }
.card-recall-leave-to { opacity: 0; transform: translateY(-8px); }
@media (max-width: 600px) { h3 { font-size: 24px; } .flashcard { padding: 24px; } }
@media (prefers-reduced-motion: reduce) { .card-recall-enter-active, .card-recall-leave-active { transition: none; } }
</style>
