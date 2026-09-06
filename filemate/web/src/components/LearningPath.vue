<template>
  <section class="learning-path" aria-label="学习行动路径">
    <header><div><h2>把下一步，看得更清楚</h2><p>按推荐顺序展开；可自由进入，不设置人为关卡。</p></div><strong>{{ completed }} / {{ goal.tasks.length }} 已完成</strong></header>
    <div class="path-layout">
      <ol class="path-nodes"><li v-for="(task, index) in goal.tasks" :key="task.task_id" :class="{ completed: task.status === 'completed', selected: selected?.task_id === task.task_id }"><button :aria-pressed="selected?.task_id === task.task_id" @click="selectedId = task.task_id"><span class="step-number"><el-icon v-if="task.status === 'completed'"><Check /></el-icon><template v-else>{{ String(index + 1).padStart(2, '0') }}</template></span><span class="node-copy"><small>{{ task.status === 'completed' ? '已完成' : '待完成' }}</small><strong>{{ task.title }}</strong><time :datetime="task.due_date">{{ task.due_date }} 前</time></span><el-icon><ArrowRight /></el-icon></button></li></ol>
      <aside v-if="selected" class="task-detail"><small>当前选中的行动</small><h3>{{ selected.title }}</h3><p>{{ selected.reason }}</p><div v-if="goal.source_name" class="task-source"><el-icon><Document /></el-icon><span>关联资料<strong>{{ goal.source_name }}</strong></span></div><p class="task-explainer">进入功能页时保留资料关联。完成后回到这里确认，进度会保存到本机。</p><router-link class="start-task" :to="destination">{{ selected.status === 'completed' ? '再次练习' : '开始这一步' }}<el-icon><ArrowRight /></el-icon></router-link><button class="complete-task" :disabled="Boolean(updatingTask)" @click="$emit('toggle', selected)">{{ updatingTask === selected.task_id ? '正在保存…' : selected.status === 'completed' ? '改为未完成' : '标记这一步已完成' }}</button></aside>
      <p v-else>暂无行动任务，可以根据最新进度重排。</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowRight, Check, Document } from '@element-plus/icons-vue'
import type { ReverseGoalPlan, ReverseGoalTask } from '../services/api'
const props = defineProps<{ goal: ReverseGoalPlan; updatingTask: string }>()
defineEmits<{ toggle: [task: ReverseGoalTask] }>()
const selectedId = ref('')
watch(() => props.goal.goal_id, () => { selectedId.value = '' })
const completed = computed(() => props.goal.tasks.filter(task => task.status === 'completed').length)
const selected = computed(() => props.goal.tasks.find(task => task.task_id === selectedId.value) || props.goal.tasks.find(task => task.status === 'pending') || props.goal.tasks[0])
const destination = computed(() => {
  const route = selected.value?.route || '/today'
  const url = new URL(route, 'http://filemate.local')
  // 仅学习工作区支持 source 深链，其他功能保留服务端已生成的查询参数。
  if (url.pathname === '/ai-tools' && props.goal.source_id) url.searchParams.set('source', props.goal.source_id)
  return `${url.pathname}${url.search}`
})
</script>

<style scoped>
.learning-path{background:#fff;border:1px solid #d7e3d9;border-radius:14px;margin:20px 0 26px;overflow:hidden;color:#183229}.learning-path header{padding:24px 28px;display:flex;justify-content:space-between;gap:20px;align-items:center;border-bottom:1px solid #e2eae0}.learning-path h2{font-size:21px;font-weight:600;margin:0 0 8px}.learning-path header p{font-size:12px;color:#566e60;margin:0}.learning-path header>strong{font-size:13px;color:#2f7d55;white-space:nowrap}.path-layout{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(240px,1fr)}.path-nodes{list-style:none;margin:0;padding:25px 28px;background:#f6f8f2;max-height:560px;overflow:auto}.path-nodes li{position:relative;padding-bottom:18px}.path-nodes li:last-child{padding-bottom:0}.path-nodes li:not(:last-child):after{content:'';position:absolute;left:32px;bottom:0;height:18px;border-left:2px solid #c4d4c2}.path-nodes button{display:flex;align-items:center;gap:16px;border:1px solid #dbe5d5;background:#fff;border-radius:10px;padding:16px;width:100%;text-align:left;color:inherit;cursor:pointer}.path-nodes .selected button{border-color:#3b7a50;background:#edf4e8}.step-number{font-size:16px;font-family:ui-monospace,monospace;width:32px;flex-shrink:0;color:#56704d}.completed .step-number{color:#2f7d55}.node-copy{flex:1;min-width:0}.node-copy small{display:block;font-size:10px;color:#566e60}.node-copy strong{display:block;font-size:14px;line-height:1.7;margin:4px 0;overflow-wrap:anywhere}.node-copy time{font-size:11px;color:#566e60}.task-detail{padding:32px;display:flex;flex-direction:column;align-items:stretch}.task-detail>small{font-size:11px;color:#566e60}.task-detail h3{font-size:24px;line-height:1.6;margin:16px 0}.task-detail>p{font-size:14px;line-height:1.95;color:#4d655b}.task-source{display:flex;align-items:start;gap:12px;padding:18px 0;border-block:1px solid #e2eae0;margin:18px 0;color:#566e60;font-size:11px}.task-source strong{display:block;font-size:13px;line-height:1.8;margin-top:6px;color:#183229;overflow-wrap:anywhere}.task-source .el-icon{font-size:22px}.task-detail .task-explainer{font-size:11px;line-height:1.9}.start-task,.complete-task{min-height:44px;border-radius:8px;display:flex;align-items:center;justify-content:center;gap:10px;font:inherit;font-size:13px;cursor:pointer;text-decoration:none;padding:10px 15px;box-sizing:border-box}.start-task{background:#2f7d55;color:#fff;margin-top:20px}.complete-task{background:#fff;border:1px solid #d7e3d9;color:#2f7d55;margin-top:10px}.complete-task:disabled{opacity:.5}.learning-path button:focus-visible,.learning-path a:focus-visible{outline:2px solid #2f7d55;outline-offset:3px}@media(max-width:700px){.learning-path header{align-items:start;flex-direction:column;padding:20px}.path-layout{grid-template-columns:1fr}.path-nodes{padding:20px;max-height:400px}.task-detail{padding:22px}.task-detail h3{font-size:21px}}
</style>
