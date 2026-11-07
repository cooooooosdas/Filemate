<template>
  <main class="trial-page">
    <section class="trial-panel">
      <header>
        <h1>试用反馈与复盘记录</h1>
        <RouterLink to="/today">返回今日行动</RouterLink>
      </header>
      <p>记录遇到的问题和改进建议，也可以回看自己保存的本周复盘。</p>
      <p v-if="error" role="alert">{{ error }}</p>
      <button v-if="!client || !identity" @click="initialize">
        重新连接当前空间
      </button>
      <template v-if="client && identity"
        ><p v-if="!allowNew">当前可查看、导出和删除已保存记录。</p>
        <form v-else @submit.prevent="preview = true">
          <fieldset>
            <legend>反馈类型</legend>
            <label v-for="item in categories" :key="item.value"
              ><input
                v-model="form.category"
                type="radio"
                :value="item.value"
              />{{ item.label }}</label
            >
          </fieldset>
          <label
            >涉及模块<select v-model="form.module">
              <option
                v-for="item in modules"
                :key="item.value"
                :value="item.value"
              >
                {{ item.label }}
              </option>
            </select></label
          ><label
            >问题或建议<textarea
              v-model="form.description"
              minlength="20"
              maxlength="2000"
              required
              placeholder="请描述具体页面、原本想完成的操作，以及实际发生的情况。"
            /></label
          ><label
            >复现步骤（可选）<textarea v-model="form.steps" maxlength="2000" />
          </label>
          <p>请核对填写内容，避免在反馈中填写密钥或个人敏感资料。</p>
          <button
            class="trial-primary"
            :disabled="!valid || !!writer?.state.pending || writer?.state.busy"
          >
            核对并提交
          </button>
        </form>
        <section v-if="preview" class="trial-notice">
          <h2>确认保存反馈</h2>
          <p class="trial-detail">{{ form.description }}</p>
          <p class="trial-detail">{{ form.steps }}</p>
          <p>网页版本 {{ form.client_version }}</p>
          <div class="trial-actions">
            <button
              class="trial-primary"
              :disabled="writer?.state.busy || !!writer?.state.pending"
              @click="save"
            >
              确认保存</button
            ><button @click="preview = false">返回修改</button>
          </div>
        </section>
        <p v-if="writer?.state.error" role="status">{{ writer.state.error }}</p>
        <button
          v-if="writer?.state.pending"
          :disabled="writer.state.busy"
          @click="recover"
        >
          查询原提交结果
        </button>
        <p v-if="writer?.state.receipt" role="status">
          {{
            writer.state.receipt.status === "deleted"
              ? "这条记录已删除。"
              : "反馈已保存到当前学习空间。"
          }}
        </p>
      </template>
    </section>
    <TrialRecords
      v-if="client && identity"
      ref="history"
      :client="client"
      :identity="identity"
      :refresh-key="writer?.state.receipt?.record_id"
    />
  </main>
</template>
<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  shallowRef,
} from "vue";
import { onBeforeRouteLeave } from "vue-router";
import { getOrchestratorBrowserScope } from "../services/orchestrator-api";
import type { FeedbackDraft, TrialClient } from "../types/trial";
import { createTrialRecordState, trialSessionStorage, trialEpoch } from "../today/trial-record-state";
import TrialRecords from "./TrialRecords.vue";
import "../trial/trial.css";
const client = shallowRef<TrialClient | null>(null),
  writer = shallowRef<ReturnType<typeof createTrialRecordState> | null>(null),
  identity = ref<string | null>(null),
  enabled = ref(false),
  error = ref(""),
  preview = ref(false);
const history = ref<{ needsLeaveConfirmation(): boolean } | null>(null);
const blank = (): FeedbackDraft => ({
  category: "bug",
  module: "today",
  description: "",
  steps: "",
  client_version: "unknown",
});
const form = reactive(blank()),
  saved = ref("");
const allowNew = computed(
  () => import.meta.env.VITE_ENABLE_TRIAL_WORKSPACE === "true" && enabled.value,
);
const valid = computed(
  () => form.description.trim().length >= 20 && form.description.length <= 2000,
);
const categories = [
  { value: "bug", label: "遇到问题" },
  { value: "suggestion", label: "功能建议" },
  { value: "other", label: "其他体验" },
];
const modules = [
  { value: "today", label: "今日行动与教练" },
  { value: "goals", label: "学习目标" },
  { value: "learning", label: "资料学习" },
  { value: "wrongbook", label: "错题复盘" },
  { value: "graph", label: "知识图谱" },
  { value: "programming", label: "编程训练" },
  { value: "interview", label: "模拟面试" },
  { value: "career", label: "求职与简历" },
  { value: "privacy", label: "隐私与账号" },
  { value: "home", label: "首页" },
  { value: "other", label: "其他" },
];
let generation = 0;
async function initialize() {
  const ticket = ++generation;
  error.value = "";
  try {
    const [port, scope] = await Promise.all([
      import("../services/trial-api"),
      getOrchestratorBrowserScope(),
    ]);
    const caps = await port.capabilities();
    if (ticket !== generation) return;
    if (!scope) throw new Error("identity");
    client.value = port;
    identity.value = scope;
    enabled.value = caps.enabled;
    writer.value = createTrialRecordState(port, trialSessionStorage(), {
      epoch: trialEpoch,
      wrap: reactive,
    });
    writer.value.bind(scope);
    try {
      const release = await fetch("/release.json").then((response) =>
        response.json(),
      );
      if (ticket === generation)
        form.client_version =
          `${release.version ?? "unknown"} ${release.web_commit ?? release.commit ?? ""}`.slice(
            0,
            100,
          );
    } catch {
      /* The server stamps its own authoritative version on save. */
    }
  } catch {
    if (ticket === generation)
      error.value = "反馈服务暂时无法连接，请保留内容并重试。";
  }
}
async function save() {
  if (!writer.value || !valid.value) return;
  const value = { ...form };
  await writer.value.save("feedback", value);
  if (writer.value.state.receipt) {
    saved.value = JSON.stringify(value);
    preview.value = false;
  }
}
async function recover() {
  await writer.value?.recover();
  if (writer.value?.state.receipt) {
    saved.value = JSON.stringify(form);
    preview.value = false;
  }
}
function dirty() {
  return (
    Boolean(form.description.trim() && JSON.stringify(form) !== saved.value) ||
    !!writer.value?.state.pending ||
    !!writer.value?.state.busy ||
    !!history.value?.needsLeaveConfirmation()
  );
}
function unload(event: BeforeUnloadEvent) {
  if (dirty()) {
    event.preventDefault();
    event.returnValue = "";
  }
}
function reset() {
  generation++;
  writer.value?.invalidate();
  writer.value = null;
  client.value = null;
  identity.value = null;
  Object.assign(form, blank());
  saved.value = "";
  preview.value = false;
  void initialize();
}
onBeforeRouteLeave(
  () => !dirty() || window.confirm("当前填写或提交结果尚待确认，确定离开吗？"),
);
onMounted(() => {
  void initialize();
  window.addEventListener("beforeunload", unload);
  window.addEventListener("filemate:today-invalidated", reset);
});
onBeforeUnmount(() => {
  generation++;
  writer.value?.bind(null);
  window.removeEventListener("beforeunload", unload);
  window.removeEventListener("filemate:today-invalidated", reset);
});
</script>
