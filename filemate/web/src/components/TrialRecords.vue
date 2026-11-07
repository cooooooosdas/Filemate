<template>
  <section class="trial-panel" aria-labelledby="trial-history-heading">
    <header>
      <h2 id="trial-history-heading">已保存记录</h2>
      <button :disabled="loading" @click="load">刷新记录</button>
    </header>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="controller.state.error" role="status">
      {{ controller.state.error }}
    </p>
    <button
      v-if="controller.state.pending"
      :disabled="controller.state.busy"
      @click="recover"
    >
      查询原请求结果
    </button>
    <p v-if="loading" role="status">正在读取当前空间的记录…</p>
    <p v-else-if="!page?.items.length">当前还没有保存的记录。</p>
    <ul v-else class="trial-records">
      <li v-for="item in page.items" :key="item.record_id">
        <header>
          <div>
            <strong>{{
              item.kind === "reflection" ? "本周复盘" : "试用反馈"
            }}</strong>
            <p>{{ item.title }} · {{ displayTime(item.created_at) }}</p>
          </div>
          <button @click="read(item.record_id)">查看记录</button>
        </header>
      </li>
    </ul>
    <div v-if="page && page.total > 20" class="trial-actions">
      <button :disabled="offset === 0 || loading" @click="move(-20)">
        上一页</button
      ><span
        >{{ offset + 1 }}—{{ Math.min(offset + 20, page.total) }} /
        {{ page.total }}</span
      ><button
        :disabled="offset + 20 >= page.total || loading"
        @click="move(20)"
      >
        下一页
      </button>
    </div>
    <article v-if="detail" class="trial-notice">
      <header>
        <h3>{{ detail.kind === "reflection" ? "复盘内容" : "反馈内容" }}</h3>
        <button @click="detail = null">收起详情</button>
      </header>
      <p class="trial-detail">
        {{ detail.content.notes ?? detail.content.description }}
      </p>
      <p v-if="detail.content.steps" class="trial-detail">
        {{ detail.content.steps }}
      </p>
      <p v-if="detail.content.server_version">
        服务版本 {{ detail.content.server_version }}
      </p>
      <div class="trial-actions">
        <button @click="exportPreview = true">预览导出</button
        ><button
          :disabled="controller.state.busy || !!controller.state.pending"
          @click="controller.previewDelete(detail.record_id)"
        >
          预览删除
        </button>
      </div>
    </article>
    <section v-if="exportPreview && detail" class="trial-notice">
      <h3>导出当前记录</h3>
      <p>文件包含这条记录的填写内容、保存时间及版本信息。</p>
      <div class="trial-actions">
        <button class="trial-primary" @click="exportRecord">
          确认导出 JSON</button
        ><button @click="exportPreview = false">取消</button>
      </div>
    </section>
    <section v-if="controller.state.deletion" class="trial-notice">
      <h3>确认删除这条记录</h3>
      <p>
        关联教练结果
        {{
          controller.state.deletion.affected.learning_coach_results ?? 0
        }}
        份，派生计划
        {{ controller.state.deletion.affected.learning_coach_plans ?? 0 }} 份。
      </p>
      <div class="trial-actions">
        <button
          class="trial-primary"
          :disabled="controller.state.busy || !!controller.state.pending"
          @click="remove"
        >
          确认删除</button
        ><button
          :disabled="controller.state.busy"
          @click="controller.state.deletion = null"
        >
          取消
        </button>
      </div>
    </section>
  </section>
</template>
<script setup lang="ts">
import { onBeforeUnmount, reactive, ref, watch } from "vue";
import type {
  RecordKind,
  TrialClient,
  TrialDetail,
  TrialPage,
} from "../types/trial";
import { createTrialRecordState, trialSessionStorage, trialEpoch } from "../today/trial-record-state";
import { saveDownload } from "../services/downloads";
import "../trial/trial.css";
const emit = defineEmits<{ changed: [id: string] }>();
const props = defineProps<{
  client: TrialClient;
  identity: string;
  kind?: RecordKind;
  refreshKey?: string;
}>();
const controller = createTrialRecordState(props.client, trialSessionStorage(), {
  epoch: trialEpoch,
  wrap: reactive,
});
const page = ref<TrialPage | null>(null),
  detail = ref<TrialDetail | null>(null),
  error = ref(""),
  loading = ref(false),
  offset = ref(0),
  exportPreview = ref(false);
let generation = 0,
  detailGeneration = 0;
const displayTime = (value: string) =>
  new Date(
    /[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : value + "Z",
  ).toLocaleString("zh-CN");
async function load() {
  const ticket = ++generation;
  loading.value = true;
  error.value = "";
  try {
    const value = await props.client.listRecords(props.kind, offset.value);
    if (ticket === generation) page.value = value;
  } catch {
    if (ticket === generation)
      error.value = "记录暂时无法读取，请重新连接后再试。";
  } finally {
    if (ticket === generation) loading.value = false;
  }
}
async function read(id: string) {
  if (controller.state.busy || controller.state.pending || controller.state.deletion)
    return;
  const ticket = ++detailGeneration;
  detail.value = null;
  exportPreview.value = false;
  error.value = "";
  try {
    const value = await props.client.detail(id);
    if (ticket === detailGeneration) detail.value = value;
  } catch {
    if (ticket === detailGeneration)
      error.value = "记录已变化或暂时无法读取，请刷新列表。";
  }
}
function move(step: number) {
  offset.value += step;
  void load();
}
async function remove() {
  await controller.confirmDelete();
  if (controller.state.receipt?.deleted) {
    emit("changed", controller.state.receipt.record_id);
    detail.value = null;
    offset.value = 0;
    await load();
  }
}
async function recover() {
  await controller.recover();
  if (controller.state.receipt) {
    detail.value = null;
    await load();
  }
}
async function exportRecord() {
  if (!detail.value) return;
  try {
    const done = await saveDownload(
      new Blob([JSON.stringify(detail.value, null, 2)], {
        type: "application/json",
      }),
      `filemate-${detail.value.kind}-${detail.value.record_id}.json`,
    );
    if (done) exportPreview.value = false;
  } catch {
    error.value = "导出未完成，请保留当前记录并重试。";
  }
}
watch(
  () => [props.identity, props.kind, props.refreshKey],
  () => {
    generation++;
    detailGeneration++;
    detail.value = null;
    page.value = null;
    offset.value = 0;
    controller.bind(props.identity);
    void load();
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  generation++;
  controller.bind(null);
});
defineExpose({
  needsLeaveConfirmation: () =>
    controller.state.busy || !!controller.state.pending,
});
</script>
