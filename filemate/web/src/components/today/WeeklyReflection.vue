<template>
  <section class="trial-panel" aria-labelledby="weekly-heading">
    <header>
      <div>
        <h2 id="weekly-heading" ref="heading" tabindex="-1">本周安排复盘</h2>
        <p>核对当前目标已确认的安排，以及原功能的当前完成状态。</p>
      </div>
      <button @click="close">收起复盘</button>
    </header>
    <p v-if="controller.state.error" role="alert">
      {{ controller.state.error }}
    </p>
    <button
      v-if="controller.state.pending"
      :disabled="controller.state.busy"
      @click="recover"
    >
      查询原保存结果
    </button>
    <p v-if="controller.state.busy" role="status">正在核对当前学习空间…</p>
    <template v-if="controller.state.weekly">
      <p>
        {{ controller.state.weekly.week_start }} 至
        {{ controller.state.weekly.week_end }} · 已读取到
        {{ controller.state.weekly.study_date }}
      </p>
      <div class="trial-metrics">
        <article>
          <strong>{{ controller.state.weekly.summary.planned_days }}</strong
          >已安排日期
        </article>
        <article>
          <strong>{{ controller.state.weekly.summary.total_tasks }}</strong
          >去重行动
        </article>
        <article>
          <strong>{{ controller.state.weekly.summary.completed_tasks }}</strong
          >原功能已完成
        </article>
        <article>
          <strong>{{ controller.state.weekly.summary.pending_tasks }}</strong
          >待完成
        </article>
        <article>
          <strong>{{ controller.state.weekly.summary.unresolved_tasks }}</strong
          >待核对来源
        </article>
        <article>
          <strong>{{ controller.state.weekly.summary.overdue_tasks }}</strong
          >已过截止日期的待办
        </article>
      </div>
      <p v-if="!controller.state.weekly.summary.planned_days">
        本周尚无当前范围的已确认安排，可以先记录自己的反思。
      </p>
      <details>
        <summary>查看行动及读取范围</summary>
        <ul>
          <li v-for="item in controller.state.weekly.items" :key="item.task_id">
            {{ item.task?.title ?? "原行动暂时无法核对" }} ·
            {{ labels[item.status] }} · {{ item.dates.join("、")
            }}<RouterLink
              v-if="item.task && destination(item.task)"
              :to="destination(item.task)!"
              >查看原行动</RouterLink
            >
          </li>
        </ul>
        <p>
          排除其他范围
          {{ controller.state.weekly.coverage.excluded_days }} 天，无法读取
          {{ controller.state.weekly.coverage.invalid_days }} 天，省略展示
          {{ controller.state.weekly.coverage.omitted_items }} 项。
        </p>
      </details>
      <form @submit.prevent="preview = true">
        <label
          >最影响这周执行的因素<select v-model="reason" :disabled="blocked">
            <option value="time">可用时间</option>
            <option value="difficulty">任务难度</option>
            <option value="unclear">下一步不够明确</option>
            <option value="progress">已有进展</option>
            <option value="other">其他原因</option>
          </select></label
        >
        <label
          >写下自己的复盘<textarea
            v-model="notes"
            required
            maxlength="2000"
            :disabled="blocked"
            placeholder="哪些安排有效，哪里受阻，接下来希望怎样调整？"
          />
        </label>
        <p>原因由你填写，作为本次复盘的自述保存。</p>
        <div class="trial-actions">
          <button class="trial-primary" :disabled="blocked || !notes.trim()">
            核对并保存复盘</button
          ><button
            type="button"
            :disabled="controller.state.busy"
            @click="controller.readWeekly(scope)"
          >
            重新读取安排
          </button>
        </div>
      </form>
      <section v-if="preview" class="trial-notice">
        <h3>确认保存这次复盘</h3>
        <p class="trial-detail">{{ notes }}</p>
        <div class="trial-actions">
          <button class="trial-primary" :disabled="blocked" @click="save">
            确认保存</button
          ><button @click="preview = false">返回修改</button>
        </div>
      </section>
      <section v-if="ready" class="trial-notice">
        <h3>复盘已保存</h3>
        <p>将这份已保存的反思带入当前目标的教练流程，再核对具体安排。</p>
        <button
          class="trial-primary"
          :disabled="blocked"
          @click="
            emit('coach', {
              record_id: controller.state.receipt!.record_id,
              notes,
            })
          "
        >
          带着复盘请教教练
        </button>
      </section>
    </template>
    <TrialRecords
      ref="history"
      :client="client"
      :identity="identity"
      kind="reflection"
      :refresh-key="controller.state.receipt?.record_id"
      @changed="recordDeleted"
    />
  </section>
</template>
<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from "vue";
import type {
  ScopeRequest,
  OrchestratorSnapshot,
  TaskView,
} from "../../types/orchestrator";
import type { ReflectionDraft } from "../../types/trial";
import * as client from "../../services/trial-api";
import { createTrialRecordState, trialSessionStorage, trialEpoch } from "../../today/trial-record-state";
import { resolveTodayTask } from "../../today/navigation";
import TrialRecords from "../TrialRecords.vue";
import "../../trial/trial.css";
const props = defineProps<{
  scope: ScopeRequest;
  identity: string;
  bundle: OrchestratorSnapshot;
}>();
const emit = defineEmits<{
  close: [];
  coach: [value: { record_id: string; notes: string }];
}>();
const controller = createTrialRecordState(client, trialSessionStorage(), {
  epoch: trialEpoch,
  wrap: reactive,
});
const notes = ref(""),
  reason = ref<ReflectionDraft["reason"]>("other"),
  preview = ref(false),
  saved = ref(""),
  heading = ref<HTMLElement | null>(null),
  history = ref<{ needsLeaveConfirmation(): boolean } | null>(null);
const fingerprint = () =>
  JSON.stringify({ notes: notes.value, reason: reason.value });
const blocked = computed(
  () => controller.state.busy || !!controller.state.pending,
);
const ready = computed(
  () =>
    controller.state.receipt?.kind === "reflection" &&
    controller.state.receipt.status === "saved" &&
    saved.value === fingerprint(),
);
const labels = { completed: "已完成", pending: "待完成", unresolved: "待核对" };
const destination = (task: TaskView) =>
  resolveTodayTask(task, props.bundle).primary;
function dirty() {
  return (
    Boolean(notes.value.trim() && saved.value !== fingerprint()) ||
    blocked.value ||
    !!history.value?.needsLeaveConfirmation()
  );
}
function close() {
  if (!dirty() || window.confirm("这次复盘或保存结果尚待确认，确定收起吗？"))
    emit("close");
}
async function save() {
  const weekly = controller.state.weekly;
  if (!weekly || !notes.value.trim()) return;
  const snapshot = fingerprint();
  await controller.save("reflection", {
    scope: weekly.scope,
    expected_revision: weekly.revision,
    reason: reason.value,
    notes: notes.value,
  });
  if (controller.state.receipt?.status === "saved") {
    saved.value = snapshot;
    preview.value = false;
  }
}
async function recover() {
  await controller.recover();
  const receipt = controller.state.receipt;
  if (receipt?.kind !== "reflection" || receipt.status !== "saved") return;
  try {
    const value = await client.detail(receipt.record_id);
    if (JSON.stringify(value.content.scope) !== JSON.stringify(props.scope))
      throw new Error("scope changed");
    notes.value = String(value.content.notes ?? "");
    reason.value = value.content.reason as ReflectionDraft["reason"];
    saved.value = fingerprint();
    preview.value = false;
  } catch {
    controller.state.error = "请在已保存记录中核对这份复盘。";
  }
}
function invalidate() {
  controller.invalidate();
  notes.value = "";
  saved.value = "";
  preview.value = false;
}
function recordDeleted(id: string) {
  if (controller.state.receipt?.record_id === id) {
    controller.state.receipt = null;
    saved.value = "";
  }
}
watch(
  () => [props.identity, JSON.stringify(props.scope)],
  () => {
    invalidate();
    controller.bind(props.identity);
    void controller.readWeekly(props.scope);
  },
  { immediate: true },
);
onMounted(async () => {
  await nextTick();
  heading.value?.focus();
});
onBeforeUnmount(() => controller.bind(null));
defineExpose({ needsLeaveConfirmation: dirty, invalidate });
</script>
