<template><div class="review-workspace review-entry"><p v-if="c.state.loading" role="status">正在核验题目…</p><ReviewQuestion v-else :question="question" :identity="`${artifactId}-${questionIndex}`" :submission="c.submission" :readonly="c.state.readonly" :readonly-reason="c.state.message" :allow-assistance="c.state.mode === 'v2'" @saved="$emit('saved')" /><button v-if="c.state.readonly && !readonly" @click="open">重新连接</button></div></template>
<script setup lang="ts">
import { reactive, watch, onMounted, onBeforeUnmount } from 'vue'
import * as reviewApi from '../../services/review-api'
import { submitQuizAttempt } from '../../services/api'
import { createReviewEntry } from '../../wrongbook/entry-state'
import { browserReviewStorage } from '../../wrongbook/submission'
import ReviewQuestion from './ReviewQuestion.vue'
import './review-workspace.css'
const props=defineProps<{artifactId:string;questionIndex:number;question:Record<string,unknown>;readonly?:boolean}>()
defineEmits<{saved:[]}>()
const c=createReviewEntry({...reviewApi,submitQuizAttempt},{enabled:import.meta.env.VITE_ENABLE_WRONGBOOK_V2==='true',storage:browserReviewStorage(),observe:v=>reactive(v) as typeof v})
function open(){return c.open({artifact_id:props.artifactId,question_index:props.questionIndex},props.question,props.readonly)}
watch(()=>[props.artifactId,props.questionIndex,props.question,props.readonly],open,{immediate:true})
function identityChanged(){c.invalidate();void open()}
onMounted(()=>{window.addEventListener('filemate:data-restored',identityChanged);window.addEventListener('filemate:session-expired',identityChanged)})
onBeforeUnmount(()=>{window.removeEventListener('filemate:data-restored',identityChanged);window.removeEventListener('filemate:session-expired',identityChanged);c.dispose()})
defineExpose({dirty:c.dirty,invalidate:c.invalidate})
</script>
<style scoped>.review-entry{padding:0;container-type:normal;max-width:none}</style>
