<template>
  <section class="learning-section" aria-label="增量学习任务"><h3>把复盘变成下一步</h3><p>只新增你确认的短行动，已有目标和计划保持原样。</p>
    <template v-if="c.state.selection">
      <fieldset :disabled="c.state.busy || c.state.uncertain || !writable"><legend>编辑本次任务（最多7项）</legend><label>开始日期<input v-model="c.state.selection.start_date" type="date" /></label><label>关联已有目标（可选）<select v-model="c.state.selection.goal_id"><option :value="undefined">不关联目标</option><option v-for="goal in goals" :key="goal.artifact_id" :value="goal.artifact_id">{{ goal.title }}</option></select></label>
        <article v-for="(task,index) in c.state.selection.tasks" :key="task.action_id" class="learning-task"><h4>行动 {{ index+1 }}</h4><label>任务标题<input v-model="task.title" maxlength="120" /></label><label>具体怎么做<textarea v-model="task.instructions" maxlength="500" rows="3" /></label><div class="learning-task-time"><label>用时（分钟）<input v-model.number="task.duration_minutes" type="number" min="5" max="60" /></label><label>第几天<input :value="task.day_offset+1" type="number" min="1" max="7" @input="task.day_offset=Number(($event.target as HTMLInputElement).value)-1" /></label></div><button :disabled="c.state.selection.tasks.length===1" @click="c.state.selection.tasks.splice(index,1)">移除此行动</button></article>
      </fieldset>
      <p v-if="basis">依据近 {{ basis.window_days }} 天 {{ basis.trusted_total }} 次确定判题，其中 {{ basis.trusted_incorrect }} 次未答对；另有 {{ basis.pending_total }} 次待核对或辅助记录。规则 {{ basis.rule_version }}</p>
      <button :disabled="!writable || c.state.busy || c.state.uncertain" @click="$emit('planning');c.previewPlan()">预览新增任务</button>
    </template><p v-else>暂无可用候选，请先选择一条真实作答。</p>
  </section>
</template>
<script setup lang="ts">
import type { createReviewLearningController } from '../../wrongbook/learning-state'
import type { LearningAction } from '../../types/reviewLearning'
defineProps<{c:ReturnType<typeof createReviewLearningController>;writable:boolean;basis?:LearningAction['basis'];goals:{artifact_id:string;title:string}[]}>()
defineEmits<{planning:[]}>()
</script>
