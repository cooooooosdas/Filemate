<template>
  <section class="focus-review review-main" aria-label="专注复习批次">
    <header class="review-header"><div><h2>本次专注复习</h2><p v-if="s.items.length">第 {{ s.position+1 }} / {{ s.items.length }} 题 · 已核验 {{ Object.keys(s.completed).length }} 次作答</p></div><button @click="$emit('exit')">返回浏览</button></header>
    <p class="review-notice">先独立作答，再核对参考。跳过不记成绩；本机只保存题目引用与进度标识，有效期7天。</p>
    <p v-if="s.loading" role="status">正在核验批次与题目…</p><p v-if="s.message" role="status">{{ s.message }}</p><p v-if="s.error" role="alert" class="review-error">{{ s.error }}</p>
    <template v-if="!s.loading && !s.finished && question && s.items[s.position]">
      <p v-if="s.completed[s.items[s.position]!.wrong_id]" class="review-notice">此题已有经服务器核验的作答，不会重新提交。</p>
      <ReviewQuestion v-else :key="s.items[s.position]!.wrong_id" :identity="s.items[s.position]!.wrong_id" :question="question" :submission="submission" @saved="c.recordSaved()" />
    </template>
    <div v-if="s.finished" role="status"><h2>本次批次已结束</h2><p>当前核验 {{ Object.keys(s.completed).length }} 次作答；跳过 {{ s.skipped.length }} 题。作答结果以服务器证据为准。</p><button @click="$emit('exit')">回到目录查看证据</button></div>
    <div v-else-if="s.items.length && !s.expired" class="review-actions"><button :disabled="s.loading || submission.state.busy" @click="skip">跳过此题</button><button v-if="s.unavailable" :disabled="s.loading" @click="c.open(s.position)">重试本题</button><button v-if="submission.state.receipt && !s.completed[s.items[s.position]!.wrong_id]" @click="c.recordSaved()">核验已保存作答</button><button class="primary" :disabled="s.loading || !s.completed[s.items[s.position]!.wrong_id]" @click="c.next()">{{ s.position+1 === s.items.length ? '结束本次复习' : '下一题' }}</button></div>
    <div v-if="!s.items.length || s.expired || s.finished" class="review-actions"><label>每批题数<input v-model.number="size" type="number" min="1" max="20" /></label><button :disabled="s.loading" @click="c.start(filters,size)">开始新批次</button></div>
  </section>
</template>
<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessageBox } from 'element-plus'
import * as api from '../../services/review-api'
import { createReviewSubmission, browserReviewStorage } from '../../wrongbook/submission'
import { createReviewPreferences } from '../../wrongbook/browse-state'
import { createFocusReviewController } from '../../wrongbook/focus-state'
import type { ReviewFilter } from '../../types/wrongbook'
import ReviewQuestion from './ReviewQuestion.vue'
const props=defineProps<{scope:string|null;filters:ReviewFilter;enabled:boolean}>()
defineEmits<{exit:[]}>()
const observe=<T extends object>(v:T)=>reactive(v) as T
const submission=createReviewSubmission(api,{scope:props.scope,storage:browserReviewStorage(),observe})
const c=createFocusReviewController(api,submission,createReviewPreferences(browserReviewStorage(),props.scope),observe),s=c.state,size=ref(10)
const question=computed(()=>{void s.loading;void s.position;return c.question()})
async function skip(){if(submission.dirty()){try{await ElMessageBox.confirm('跳过后未提交正文不会保存，待确认请求仍可在原题核验。','跳过此题？',{confirmButtonText:'跳过',cancelButtonText:'继续作答'})}catch{return}}await c.skip()}
onMounted(async()=>{if(!props.enabled){s.error='服务端未允许写入，请返回浏览。';return}if(!await c.resume()&&!s.expired)await c.start(props.filters)})
onBeforeUnmount(()=>c.dispose())
defineExpose({dirty:()=>submission.dirty()||s.loading, invalidate:()=>c.resetIdentity(null)})
</script>
