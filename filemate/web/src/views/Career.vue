<template>
  <div class="career-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">岗位 · 证据 · 下一步训练</p>
        <h1>求职训练中心</h1>
        <p>从岗位要求出发，把知识练习、编程和口头表达接成一条训练路径。</p>
      </div>
      <button :disabled="loading || !!busy" @click="load">刷新记录</button>
    </header>
    <p class="boundary">
      岗位仅是带日期的训练快照，请到官方页面核对招聘状态。训练题由平台原创；训练记录不用于录用判断。
    </p>
    <p v-if="loading" role="status">正在读取岗位与训练记录…</p>
    <div v-if="error" class="error" role="alert">
      {{ error }} <button :disabled="!!busy" @click="load">重试读取</button>
    </div>
    <p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <p v-if="disabled" class="panel">
      求职训练中心暂未启用。<router-link to="/ai-tools"
        >回到学习工作区</router-link
      >
    </p>
    <template v-else>
      <div class="career-layout">
        <aside class="panel position-list" aria-labelledby="career-list-title">
          <div class="section-head">
            <h2 id="career-list-title">我的岗位</h2>
            <button :disabled="!!busy" @click="newDraft">导入岗位</button>
          </div>
          <label
            >搜索企业、岗位或地区<input
              v-model="search"
              type="search"
              maxlength="100"
              placeholder="例如：上海 / C++"
          /></label>
          <label
            >岗位类别<select v-model="employmentFilter" aria-label="岗位类别">
              <option value="">全部类别</option>
              <option>校招</option>
              <option>实习</option>
              <option>社招参考</option>
              <option>用户自定义</option>
            </select></label
          >
          <p v-if="!positions.length" class="muted">
            还没有保存岗位。先核对下方官方快照，或导入自己的岗位描述。
          </p>
          <p v-else-if="!filteredPositions.length" class="muted">
            没有匹配岗位，试着调整搜索条件。
          </p>
          <button
            v-for="item in filteredPositions"
            :key="item.position_id"
            class="position-row"
            :class="{ chosen: selected?.position_id === item.position_id }"
            :disabled="!!busy"
            @click="select(item)"
          >
            <strong>{{ item.position?.company || "岗位数据异常" }}</strong
            ><span>{{
              item.position?.title || "原记录保留，可预览删除后重新导入"
            }}</span
            ><small
              >{{ item.active ? "已保存" : "已撤销" }} ·
              {{ item.position?.region }} ·
              {{ item.position?.employment }}</small
            >
          </button>
          <details class="catalog" open>
            <summary>已核对的官方训练快照 · {{ catalog.length }}</summary>
            <div
              v-for="(item, index) in filteredCatalog"
              :key="item.source_url"
              class="catalog-row"
            >
              <strong>{{ item.company }}</strong
              ><span>{{ item.title }}</span
              ><small
                >{{ item.region }} · {{ item.employment }} · 采集
                {{ date(item.collected_at) }}</small
              ><button
                :disabled="!!busy"
                :aria-label="`核对${item.company}${item.title}`"
                @click="catalogDraft(item, index)"
              >
                核对后保存
              </button>
            </div>
            <p v-if="!filteredCatalog.length" class="muted">
              当前条件没有官方快照，可自行导入。
            </p>
          </details>
        </aside>
        <section class="career-detail" aria-label="岗位训练详情">
          <section
            v-if="draft"
            class="panel import-panel"
            aria-labelledby="career-import-title"
          >
            <div class="section-head">
              <h2 id="career-import-title">
                {{ editingId ? "核对岗位修改" : "核对岗位与来源" }}
              </h2>
              <button :disabled="!!busy" @click="closeDraft">取消导入</button>
            </div>
            <p class="muted">
              本地核对后才保存。自行导入的来源由你声明，平台未验证该企业招聘信息。
            </p>
            <div class="form-grid">
              <label
                >企业名称<input
                  v-model="draft.company"
                  maxlength="80"
                  :readonly="officialDraft" /></label
              ><label
                >岗位名称<input
                  v-model="draft.title"
                  maxlength="100"
                  :readonly="officialDraft"
              /></label>
              <label
                >行业<input
                  v-model="draft.industry"
                  maxlength="80"
                  :readonly="officialDraft" /></label
              ><label
                >地区<input
                  v-model="draft.region"
                  maxlength="80"
                  :readonly="officialDraft"
              /></label>
              <label
                >招聘类别<select
                  v-model="draft.employment"
                  :disabled="officialDraft"
                >
                  <option>校招</option>
                  <option>实习</option>
                  <option>社招参考</option>
                  <option>用户自定义</option>
                </select></label
              >
              <label
                >来源页面日期（可选）<input
                  v-model="draft.published_at"
                  maxlength="40"
                  :readonly="officialDraft" /></label
              ><label
                >来源说明<input
                  v-model="draft.source"
                  maxlength="120"
                  :readonly="officialDraft"
              /></label>
              <label class="wide"
                >来源网址（可选HTTPS）<input
                  v-model="draft.source_url"
                  maxlength="1000"
                  :readonly="officialDraft"
              /></label>
            </div>
            <p>
              采集时间：{{ date(draft.collected_at) }} ·
              {{
                officialDraft ? "已核对官方快照" : "用户自行导入，未独立核验"
              }}
            </p>
            <a
              v-if="safeSource(draft.source_url)"
              :href="draft.source_url"
              target="_blank"
              rel="noopener noreferrer"
              >打开岗位来源</a
            >
            <label
              >岗位描述<textarea
                v-model="draft.description"
                rows="6"
                maxlength="12000"
                :readonly="officialDraft"
              />
            </label>
            <div v-if="!officialDraft" class="actions">
              <label class="file-label"
                >读取本地岗位文本<input
                  type="file"
                  accept=".txt,.md"
                  :disabled="!!busy"
                  @change="readFile" /></label
              ><button
                :disabled="!!busy || draft.description.trim().length < 10"
                @click="extract"
              >
                提取待核对要求</button
              ><button
                :disabled="draft.requirements.length >= 30"
                @click="
                  draft.requirements.push({
                    label: '',
                    category: 'knowledge',
                    evidence: '',
                  })
                "
              >
                添加要求
              </button>
            </div>
            <h3>要求与原句 · {{ draft.requirements.length }}</h3>
            <p v-if="!draft.requirements.length" class="muted">
              先输入描述并提取要求，或手动添加；每项都需引用描述中的原句。
            </p>
            <div
              v-for="(item, index) in draft.requirements"
              :key="index"
              class="requirement-edit"
            >
              <label
                >技能名称<input
                  v-model="item.label"
                  maxlength="60"
                  :readonly="officialDraft" /></label
              ><label
                >训练类别<select
                  v-model="item.category"
                  :disabled="officialDraft"
                >
                  <option value="programming">编程</option>
                  <option value="knowledge">知识</option>
                  <option value="project">项目</option>
                  <option value="communication">表达</option>
                </select></label
              ><label class="wide"
                >岗位原句<input
                  v-model="item.evidence"
                  maxlength="400"
                  :readonly="officialDraft" /></label
              ><button
                v-if="!officialDraft"
                @click="draft.requirements.splice(index, 1)"
              >
                移除此要求
              </button>
            </div>
            <div class="actions">
              <button
                class="primary"
                :disabled="!!busy || !validDraft"
                @click="saveDraft"
              >
                {{
                  busy === "save"
                    ? "正在保存…"
                    : editingId
                      ? "确认保存岗位修改"
                      : "确认保存岗位"
                }}</button
              ><button
                v-if="officialDraft"
                @click="
                  draft.source_kind = 'user_import';
                  draft.source = '用户调整的官方页面参考';
                  draft.collected_at = new Date().toISOString();
                "
              >
                作为用户导入修改
              </button>
            </div>
          </section>
          <section
            v-else-if="selected?.position"
            class="panel position-detail"
            aria-labelledby="career-position-title"
          >
            <p class="eyebrow">
              {{ selected.position.company }} · {{ selected.position.region }} ·
              {{ selected.position.employment }}
            </p>
            <h2 id="career-position-title">{{ selected.position.title }}</h2>
            <p class="muted">
              {{ selected.position.source }} · 采集
              {{ date(selected.position.collected_at) }} · 距采集
              {{ selected.age_days }} 天 · 岗位版本 {{ selected.revision }} ·
              来源页面日期 {{ selected.position.published_at || "未声明" }} ·
              记录更新 {{ date(selected.updated_at) }}
            </p>
            <a
              v-if="safeSource(selected.position.source_url)"
              :href="selected.position.source_url"
              target="_blank"
              rel="noopener noreferrer"
              >核对官方或声明来源</a
            >
            <p class="description">{{ selected.position.description }}</p>
            <ul class="requirements">
              <li
                v-for="item in selected.position.requirements"
                :key="item.label"
              >
                <strong>{{ item.label }}</strong
                ><q>{{ item.evidence }}</q>
              </li>
            </ul>
            <div class="actions">
              <button :disabled="!!busy || !selected.active" @click="editDraft">
                修改本地岗位</button
              ><button :disabled="!!busy" @click="transition">
                {{ selected.active ? "撤销岗位" : "恢复岗位" }}</button
              ><button class="danger" :disabled="!!busy" @click="remove">
                预览删除岗位
              </button>
            </div>
            <p v-if="!selected.active" class="notice">
              岗位已撤销，新训练已停用；旧训练和面试仍可回看。
            </p>
            <div v-else class="training-path" aria-label="岗位训练路径">
              <div>
                <span>基础与编程</span
                ><button
                  class="primary"
                  :disabled="!!busy"
                  @click="start('written')"
                >
                  创建模拟笔试
                </button>
              </div>
              <div>
                <span>项目与口头表达</span
                ><button :disabled="!!busy" @click="start('interview')">
                  创建岗位面试
                </button>
              </div>
              <div>
                <span>证据与复盘</span
                ><button :disabled="!!busy" @click="start('review')">
                  保存训练对比
                </button>
              </div>
            </div>
          </section>
          <section v-else-if="selected?.data_error" class="panel error">
            <h2>岗位数据异常</h2>
            <p>原记录未改写，可先核对来源再重新导入。</p>
            <button :disabled="!!busy" @click="remove">预览删除岗位</button>
          </section>
          <section v-else class="panel welcome">
            <h2>先选一个你要训练的岗位</h2>
            <p>
              查看要求原句，再用真实练习证据决定下一步。从基础笔试到编程、面试和复盘，记录会持续保留。
            </p>
            <p class="muted">这里没有岗位匹配分数；没有样本时显示待评测。</p>
          </section>
          <CareerPlanPanel v-if="selected && !draft && !selected.data_error" :key="selected.position_id" :position="selected" :locked="!!busy" />
          <section
            v-if="selected && !draft"
            class="panel"
            aria-labelledby="career-evidence-title"
          >
            <div class="section-head">
              <h2 id="career-evidence-title">岗位要求与训练证据</h2>
              <button
                :disabled="!!busy || !selected.active || selected.data_error"
                @click="refreshDetail"
              >
                刷新训练证据
              </button>
            </div>
            <p v-if="detailLoading" role="status">正在核对现有训练…</p>
            <template v-if="comparison"
              ><p class="muted">{{ comparison.mapping_method }}</p>
              <div
                v-for="skill in comparison.skills"
                :key="skill.label"
                class="evidence-row"
              >
                <div class="section-head">
                  <h3>{{ skill.label }}</h3>
                  <span>{{ skill.status }}</span>
                </div>
                <p v-for="note in skill.notes" :key="note">{{ note }}</p>
                <ul>
                  <li v-for="node in skill.graph_nodes" :key="node.id">
                    <router-link
                      :to="{
                        path: '/knowledge-graph',
                        query: { node: node.id },
                      }"
                      >{{ node.label }} · {{ node.metrics.status }}</router-link
                    >
                    · 最近窗口 {{ node.metrics.recent_sample_count }} 次，正确率
                    {{ percent(node.metrics.correct_rate) }}
                  </li>
                  <li
                    v-for="coding in skill.coding_evidence"
                    :key="coding.submission_id"
                  >
                    <router-link
                      :to="{
                        path: '/programming',
                        query: { submission: coding.submission_id },
                      }"
                      >{{ coding.verdict }} · 提交
                      {{ coding.submission_id.slice(0, 8) }}</router-link
                    >
                  </li>
                </ul>
              </div>
              <h3>本岗位面试记录</h3>
              <p v-if="!comparison.interviews.length" class="muted">
                尚无本岗位口头训练记录。
              </p>
              <router-link
                v-for="item in comparison.interviews"
                :key="item.interview_id"
                class="evidence-link"
                :to="{
                  path: '/interview',
                  query: { interview: item.interview_id },
                }"
                >已答 {{ item.answered }} 题 · 内容评估 {{ item.assessed }} 题 ·
                回看面试与复盘</router-link
              >
              <p class="muted">{{ comparison.purpose }}</p></template
            >
            <p v-else-if="!detailLoading" class="muted">
              选择有效岗位后可核对当前训练证据。
            </p>
          </section>
          <section
            v-if="training"
            class="panel training-detail"
            aria-labelledby="career-training-title"
          >
            <div class="section-head">
              <h2 id="career-training-title">{{ kindText(training.kind) }}</h2>
              <div class="actions">
                <button
                  :disabled="!!busy || training.data_error"
                  @click="download('json')"
                >
                  导出训练 JSON</button
                ><button
                  :disabled="!!busy || training.data_error"
                  @click="download('markdown')"
                >
                  导出训练 Markdown
                </button>
              </div>
            </div>
            <p v-if="training.data_error" class="error">
              训练数据异常，原记录保留；可回到原面试或重新创建训练。
            </p>
            <template v-else-if="training.payload"
              ><p class="muted">
                {{ training.payload.position.company }} ·
                {{ training.payload.position.title }} · 岗位快照版本
                {{ training.payload.position_revision }} ·
                {{ date(training.created_at) }}
              </p>
              <template v-if="training.kind === 'written'"
                ><p>
                  平台原创基础题与算法题，非企业真题。算法题进入现有C++17评测页，不自动执行代码。
                </p>
                <div
                  v-for="question in training.payload.questions"
                  :key="question.id"
                  class="basic-question"
                >
                  <h3>{{ question.question }}</h3>
                  <label
                    v-for="(option, index) in question.options"
                    :key="index"
                    class="choice"
                    ><input
                      v-model="answers[question.id]"
                      type="radio"
                      :name="question.id"
                      :value="index"
                      :disabled="!!busy || !!training.payload.result"
                    />{{ option }}</label
                  >
                  <p v-if="training.payload.result">
                    {{
                      training.payload.result.answers[question.id] ===
                      question.correct
                        ? "本题正确"
                        : "本题需复习"
                    }}
                    · {{ question.explanation }}
                  </p>
                </div>
                <button
                  v-if="
                    training.payload.questions?.length &&
                    !training.payload.result
                  "
                  class="primary"
                  :disabled="!!busy || !allAnswered"
                  @click="submitWritten"
                >
                  提交基础题
                </button>
                <p v-if="training.payload.result" class="notice">
                  本轮基础题：{{ training.payload.result.correct }} /
                  {{ training.payload.result.total }} 正确。此项只描述本轮作答。
                </p>
                <h3 v-if="training.payload.problems?.length">算法训练</h3>
                <router-link
                  v-for="problem in training.payload.problems"
                  :key="problem.id"
                  class="evidence-link"
                  :to="{ path: '/programming', query: { problem: problem.id } }"
                  >{{ problem.title }} · {{ problem.difficulty }} ·
                  开始原创C++训练</router-link
                ></template
              ><router-link
                v-if="training.kind === 'interview' && training.interview_id"
                class="evidence-link"
                :to="{
                  path: '/interview',
                  query: { interview: training.interview_id },
                }"
                >进入本场岗位面试与复盘</router-link
              ><template v-if="training.kind === 'review'"
                ><p>已保存当时的训练对比；后续提交不会改写这份历史快照。</p>
                <ul>
                  <li
                    v-for="skill in training.payload.comparison?.skills"
                    :key="skill.label"
                  >
                    {{ skill.label }}：{{ skill.status }} · 基础题
                    {{ skill.written_correct_count }} /
                    {{ skill.written_count }} · 编程提交
                    {{ skill.coding_count }} 次
                  </li>
                </ul></template
              ></template
            >
          </section>
          <section v-if="selected && !draft" class="panel">
            <h2>求职训练记录 · 最近100份中的 {{ trainings.length }} 份</h2>
            <p v-if="!trainings.length" class="muted">
              创建第一轮模拟笔试或面试，记录会保存在本地。
            </p>
            <button
              v-for="item in trainings"
              :key="item.training_id"
              class="history-row"
              :disabled="!!busy"
              @click="openTraining(item)"
            >
              <span
                >{{ kindText(item.kind)
                }}{{ item.data_error ? " · 数据异常" : "" }}</span
              ><small>{{ date(item.created_at) }}</small>
            </button>
          </section>
        </section>
      </div>
      <details class="panel operation-log">
        <summary>求职操作记录 · 最近100条</summary>
        <ul>
          <li v-for="event in events" :key="event.event_id">
            {{ date(event.created_at) }} · {{ eventText(event.action) }}
          </li>
        </ul>
      </details>
    </template>
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  onMounted,
  ref,
  shallowRef,
  watch,
} from "vue";
import {
  onBeforeRouteLeave,
  onBeforeRouteUpdate,
  useRoute,
  useRouter,
} from "vue-router";
import { ElMessageBox } from "element-plus";
import CareerPlanPanel from "../components/CareerPlanPanel.vue";
import {
  getCareerCatalog,
  getCareerEvents,
  getCareerPositions,
  getCareerPosition,
  getCareerStatus,
  getCareerEvidence,
  getCareerTrainings,
  getCareerTraining,
  saveCareerPosition,
  editCareerPosition,
  changeCareerPosition,
  startCareerTraining,
  extractCareerRequirements,
  answerCareerWritten,
  previewCareerDelete,
  deleteCareerPosition,
  exportCareerTraining,
} from "../services/api";
import type {
  CareerComparison,
  CareerEvent,
  CareerPosition,
  CareerRecord,
  CareerTraining,
} from "../types/career";
const route = useRoute(),
  router = useRouter();
const positions = shallowRef<CareerRecord[]>([]),
  catalog = shallowRef<CareerPosition[]>([]),
  events = shallowRef<CareerEvent[]>([]);
const selected = shallowRef<CareerRecord | null>(null),
  comparison = shallowRef<CareerComparison | null>(null),
  trainings = shallowRef<CareerTraining[]>([]),
  training = shallowRef<CareerTraining | null>(null);
const draft = ref<CareerPosition | null>(null),
  editingId = ref(""),
  editingRevision = ref(0),
  answers = ref<Record<string, number>>({});
const search = ref(""),
  employmentFilter = ref(""),
  loading = ref(false),
  detailLoading = ref(false),
  busy = ref(""),
  error = ref(""),
  notice = ref(""),
  disabled = ref(false);
let disposed = false,
  loadEpoch = 0,
  detailEpoch = 0;
let pendingSave: { fingerprint: string; key: string } | null = null,
  pendingTraining: { fingerprint: string; key: string } | null = null;
const officialDraft = computed(
  () => draft.value?.source_kind === "official_snapshot",
);
function matches(position: CareerPosition | null) {
  return (
    !position ||
    ((!employmentFilter.value ||
      position.employment === employmentFilter.value) &&
      `${position.company} ${position.title} ${position.region} ${position.requirements.map((r) => r.label).join(" ")}`
        .toLocaleLowerCase()
        .includes(search.value.trim().toLocaleLowerCase()))
  );
}
const filteredPositions = computed(() =>
  positions.value.filter((p) => matches(p.position)),
);
const filteredCatalog = computed(() => catalog.value.filter(matches));
const validDraft = computed(
  () =>
    !!draft.value &&
    [
      draft.value.company,
      draft.value.industry,
      draft.value.region,
      draft.value.title,
      draft.value.source,
    ].every((v) => v.trim()) &&
    draft.value.description.trim().length >= 10 &&
    draft.value.requirements.length > 0 &&
    draft.value.requirements.every(
      (r) =>
        r.label.trim() &&
        r.evidence.trim() &&
        draft.value!.description.includes(r.evidence),
    ),
);
const allAnswered = computed(
  () =>
    !!training.value?.payload?.questions?.length &&
    training.value.payload.questions.every((q) =>
      Number.isInteger(answers.value[q.id]),
    ),
);
const kindText = (kind: string) =>
  (
    ({
      written: "模拟笔试",
      interview: "岗位面试",
      review: "训练对比快照",
    }) as Record<string, string>
  )[kind] || kind;
const date = (value: string) => new Date(value).toLocaleString("zh-CN");
const percent = (value: number | null) =>
  value == null ? "待评测" : `${(value * 100).toFixed(1)}%`;
const safeSource = (value: string) => {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password;
  } catch {
    return false;
  }
};
const message = (e: unknown) =>
  e instanceof Error ? e.message : "操作未完成，请重试";
const eventText = (action: string) =>
  (
    ({
      created: "保存岗位",
      edited: "修改岗位",
      undo: "撤销岗位",
      restore: "恢复岗位",
      training_created: "创建训练",
      written_submitted: "提交基础题",
      plan_saved: "保存岗位学习计划",
      plan_undo: "撤销岗位学习计划",
      plan_restore: "恢复岗位学习计划",
      exported: "导出训练",
      position_deleted: "删除岗位记录",
    }) as Record<string, string>
  )[action] || action;
async function load() {
  const current = ++loadEpoch;
  loading.value = true;
  error.value = "";
  const positionId =
    typeof route.query.position === "string" ? route.query.position : "";
  const trainingId =
    typeof route.query.training === "string" ? route.query.training : "";
  try {
    const status = await getCareerStatus();
    if (disposed || current !== loadEpoch) return;
    disabled.value = !status.enabled;
    if (disabled.value) return;
    const values = await Promise.allSettled([
      getCareerPositions(),
      getCareerCatalog(),
      getCareerEvents(),
    ]);
    if (disposed || current !== loadEpoch) return;
    if (values[0].status === "fulfilled") positions.value = values[0].value;
    if (values[1].status === "fulfilled") catalog.value = values[1].value;
    if (values[2].status === "fulfilled") events.value = values[2].value;
    error.value = values
      .filter((v) => v.status === "rejected")
      .map((v) => message((v as PromiseRejectedResult).reason))
      .join("；");
    if (positionId) {
      const row =
        positions.value.find((p) => p.position_id === positionId) ||
        (await getCareerPosition(positionId));
      if (disposed || current !== loadEpoch) return;
      await select(row, false);
    } else {
      detailEpoch++;
      selected.value = null;
      comparison.value = null;
      training.value = null;
      trainings.value = [];
      detailLoading.value = false;
    }
    if (disposed || current !== loadEpoch) return;
    if (trainingId) {
      const row = await getCareerTraining(trainingId);
      if (disposed || current !== loadEpoch) return;
      await openTraining(row, false);
    }
  } catch (e) {
    if (!disposed && current === loadEpoch) error.value = message(e);
  } finally {
    if (current === loadEpoch) loading.value = false;
  }
}
async function select(row: CareerRecord, navigate = true) {
  if (navigate && draft.value) {
    try {
      await confirmDiscard();
    } catch {
      return;
    }
  }
  if (disposed) return;
  selected.value = row;
  comparison.value = null;
  training.value = null;
  trainings.value = [];
  if (navigate) {
    draft.value = null;
    await router.push({ query: { position: row.position_id } });
  }
  if (!disposed) await refreshDetail();
}
async function refreshDetail() {
  if (!selected.value) return;
  const current = ++detailEpoch,
    id = selected.value.position_id;
  detailLoading.value = true;
  const values = await Promise.allSettled([
    getCareerTrainings(id),
    ...(selected.value.active && !selected.value.data_error
      ? [getCareerEvidence(id)]
      : []),
  ]);
  if (disposed || current !== detailEpoch || id !== selected.value?.position_id)
    return;
  if (values[0]?.status === "fulfilled")
    trainings.value = values[0].value as CareerTraining[];
  if (values[1]?.status === "fulfilled")
    comparison.value = values[1].value as CareerComparison;
  const failures = values.filter((v) => v.status === "rejected");
  if (failures.length)
    error.value = failures
      .map((v) => message((v as PromiseRejectedResult).reason))
      .join("；");
  detailLoading.value = false;
}
async function newDraft() {
  try {
    await confirmDiscard();
  } catch {
    return;
  }
  if (disposed) return;
  editingId.value = "";
  draft.value = {
    company: "",
    title: "",
    industry: "软件与科技",
    region: "",
    employment: "用户自定义",
    description: "",
    source: "用户自行导入",
    source_url: "",
    source_kind: "user_import",
    collected_at: new Date().toISOString(),
    published_at: "",
    requirements: [],
  };
}
async function confirmDiscard() {
  if (draft.value)
    await ElMessageBox.confirm(
      "离开当前核对内容将丢弃尚未保存的修改。确认继续？",
      "保留或丢弃草稿",
      { confirmButtonText: "丢弃草稿", cancelButtonText: "继续核对" },
    );
}
async function catalogDraft(item: CareerPosition, _index: number) {
  try {
    await confirmDiscard();
    editingId.value = "";
    draft.value = structuredClone(item);
    error.value = "";
    notice.value = "";
  } catch {
    /* 取消保留草稿。 */
  }
}
async function closeDraft() {
  try {
    await confirmDiscard();
    draft.value = null;
    editingId.value = "";
  } catch {
    /* 取消保留草稿。 */
  }
}
function editDraft() {
  if (!selected.value?.position) return;
  editingId.value = selected.value.position_id;
  editingRevision.value = selected.value.revision;
  draft.value = structuredClone(selected.value.position);
  draft.value.source_kind = "user_import";
  draft.value.source = "用户核对修改的岗位资料";
  draft.value.collected_at = new Date().toISOString();
}
async function readFile(event: Event) {
  const input = event.target as HTMLInputElement,
    file = input.files?.[0];
  if (!file || !draft.value) return;
  const targetDraft = draft.value;
  busy.value = "file";
  try {
    if (file.size > 64 * 1024)
      throw new Error("岗位文本需小于64KB，最多12000字符");
    if (draft.value.description)
      await ElMessageBox.confirm(
        "将用所选文本替换当前描述，并清空待核对要求。确认继续？",
        "读取岗位文本",
        { confirmButtonText: "载入文本", cancelButtonText: "保留描述" },
      );
    const text = await file.text();
    if (text.length > 12000) throw new Error("岗位描述超过12000字符");
    if (!disposed && draft.value === targetDraft) {
      targetDraft.description = text;
      targetDraft.requirements = [];
    }
  } catch (e) {
    if (e !== "cancel" && e !== "close") error.value = message(e);
  } finally {
    input.value = "";
    if (draft.value === targetDraft) busy.value = "";
  }
}
async function extract() {
  if (!draft.value) return;
  busy.value = "extract";
  error.value = "";
  try {
    const description = draft.value.description;
    const result = await extractCareerRequirements(description);
    if (!disposed && draft.value?.description === description) {
      draft.value.requirements = result.requirements;
      notice.value = result.requirements.length
        ? "已提取待核对要求，请检查原句后确认保存。"
        : "没有识别到现有词表要求，可手动添加。";
    }
  } catch (e) {
    error.value = message(e);
  } finally {
    busy.value = "";
  }
}
async function saveDraft() {
  if (!draft.value || !validDraft.value || busy.value) return;
  busy.value = "save";
  error.value = "";
  try {
    const position = JSON.parse(JSON.stringify(draft.value)) as CareerPosition;
    await ElMessageBox.confirm(
      `将保存${position.company}的${position.title}，包含${position.requirements.length}项已展示要求。既有训练保留原岗位快照。`,
      "确认岗位与来源",
      { confirmButtonText: "确认保存", cancelButtonText: "继续核对" },
    );
    if (disposed) return;
    const fingerprint = JSON.stringify(position);
    if (!pendingSave || pendingSave.fingerprint !== fingerprint)
      pendingSave = { fingerprint, key: crypto.randomUUID() };
    const row = editingId.value
      ? await editCareerPosition(
          editingId.value,
          position,
          editingRevision.value,
        )
      : await saveCareerPosition(position, pendingSave.key);
    if (disposed) return;
    pendingSave = null;
    draft.value = null;
    editingId.value = "";
    await select(row);
    notice.value = "岗位已保存，可开始训练。";
    await load();
  } catch (e) {
    if (e !== "cancel" && e !== "close") error.value = message(e);
  } finally {
    busy.value = "";
  }
}
async function start(kind: CareerTraining["kind"]) {
  if (!selected.value || busy.value) return;
  busy.value = kind;
  error.value = "";
  try {
    const id = selected.value.position_id,
      revision = selected.value.revision;
    await ElMessageBox.confirm(
      `按当前岗位版本${revision}创建${kindText(kind)}。题目是平台原创训练，面试默认只在本地记录。`,
      "确认训练快照",
      { confirmButtonText: "确认创建训练", cancelButtonText: "取消" },
    );
    if (disposed) return;
    const fingerprint = JSON.stringify([id, kind, revision]);
    if (!pendingTraining || pendingTraining.fingerprint !== fingerprint)
      pendingTraining = { fingerprint, key: crypto.randomUUID() };
    const row = await startCareerTraining(
      id,
      kind,
      pendingTraining.key,
      revision,
    );
    if (disposed) return;
    pendingTraining = null;
    await openTraining(row);
    await refreshDetail();
    events.value = await getCareerEvents();
    notice.value = `${kindText(kind)}已保存。`;
  } catch (e) {
    if (e !== "cancel" && e !== "close") error.value = message(e);
  } finally {
    busy.value = "";
  }
}
async function openTraining(row: CareerTraining, navigate = true) {
  if (disposed) return;
  if (!navigate && row.position_id !== selected.value?.position_id)
    throw new Error("训练与当前岗位不一致，请从该岗位训练记录重新打开");
  training.value = row;
  answers.value = { ...(row.payload?.result?.answers || {}) };
  if (navigate)
    await router.push({
      path: "/career",
      query: { position: row.position_id, training: row.training_id },
    });
}
async function submitWritten() {
  if (!training.value || !allAnswered.value || busy.value) return;
  busy.value = "answer";
  error.value = "";
  try {
    const row = await answerCareerWritten(training.value.training_id, {
      ...answers.value,
    });
    if (!disposed) {
      training.value = row;
      await refreshDetail();
      events.value = await getCareerEvents();
    }
  } catch (e) {
    error.value = message(e);
  } finally {
    busy.value = "";
  }
}
async function transition() {
  if (!selected.value || busy.value) return;
  busy.value = "transition";
  try {
    const action = selected.value.active ? "undo" : "restore";
    await ElMessageBox.confirm(
      action === "undo"
        ? "撤销后不能新建该岗位训练；历史、编程提交和面试保留，之后可恢复。"
        : "恢复岗位以继续创建训练。",
      "确认岗位状态",
      { confirmButtonText: "确认变更", cancelButtonText: "取消" },
    );
    if (disposed) return;
    selected.value = await changeCareerPosition(
      selected.value.position_id,
      action,
    );
    comparison.value = null;
    await load();
  } catch (e) {
    if (e !== "cancel" && e !== "close") error.value = message(e);
  } finally {
    busy.value = "";
  }
}
async function remove() {
  if (!selected.value || busy.value) return;
  busy.value = "delete";
  try {
    const id = selected.value.position_id,
      preview = await previewCareerDelete(id);
    await ElMessageBox.confirm(
      `将删除本岗位、${preview.training_count}份求职训练/对比快照和${preview.learning_plan_count}份岗位学习计划及进度。${preview.scope} 此操作不可恢复。`,
      "删除影响预览",
      {
        confirmButtonText: "确认删除岗位",
        cancelButtonText: "保留岗位",
        type: "warning",
      },
    );
    if (disposed) return;
    await deleteCareerPosition(id, preview.confirmation_token);
    selected.value = null;
    comparison.value = null;
    training.value = null;
    trainings.value = [];
    await router.replace({ query: {} });
    await load();
    notice.value = "本岗位与求职快照已删除，其他学习记录保留。";
  } catch (e) {
    if (e !== "cancel" && e !== "close") error.value = message(e);
  } finally {
    busy.value = "";
  }
}
async function download(format: "json" | "markdown") {
  if (!training.value || busy.value) return;
  busy.value = "export";
  try {
    const id = training.value.training_id,
      blob = await exportCareerTraining(id, format);
    if (disposed) return;
    const url = URL.createObjectURL(blob),
      a = document.createElement("a");
    a.href = url;
    a.download = `filemate-career-${id}.${format === "json" ? "json" : "md"}`;
    a.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    events.value = await getCareerEvents();
  } catch (e) {
    error.value = message(e);
  } finally {
    busy.value = "";
  }
}
async function guardDraftNavigation() {
  try {
    await confirmDiscard();
    if (disposed) return false;
    draft.value = null;
    editingId.value = "";
    return true;
  } catch {
    return false;
  }
}
onBeforeRouteLeave(guardDraftNavigation);
onBeforeRouteUpdate(guardDraftNavigation);
watch(
  () => [route.query.position, route.query.training],
  () => {
    const pid =
      typeof route.query.position === "string" ? route.query.position : "";
    const tid =
      typeof route.query.training === "string" ? route.query.training : "";
    if (
      pid === (selected.value?.position_id || "") &&
      tid === (training.value?.training_id || "")
    )
      return;
    void load();
  },
);
onMounted(load);
onBeforeUnmount(() => {
  disposed = true;
  loadEpoch++;
  detailEpoch++;
});
</script>

<style scoped>
.career-page a {
  color: var(--accent);
}
.career-page {
  overflow-wrap: anywhere;
  max-width: 1420px;
  margin: 0 auto;
  color: var(--text-primary);
}
.page-heading,
.section-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
}
.page-heading h1 {
  font-size: 30px;
  letter-spacing: -0.5px;
  margin: 6px 0 12px;
}
.page-heading p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.7;
}
.eyebrow {
  font-size: 12px;
  color: var(--accent) !important;
}
.boundary {
  font-size: 13px;
  line-height: 1.8;
  color: var(--text-secondary);
  padding: 14px 0;
  border-bottom: 1px solid var(--border-subtle);
}
.career-layout {
  display: grid;
  grid-template-columns: minmax(250px, 0.72fr) minmax(0, 1.65fr);
  gap: 24px;
  margin-top: 24px;
  align-items: start;
}
.panel {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: 14px;
  padding: 24px;
  margin-bottom: 24px;
  min-width: 0;
}
.panel h2 {
  font-size: 20px;
  margin: 0 0 16px;
}
.section-head h2 {
  margin: 0;
}
.section-head {
  margin-bottom: 16px;
}
.panel h3 {
  font-size: 15px;
  margin: 16px 0 10px;
}
.muted,
small {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.7;
}
.panel p {
  line-height: 1.8;
}
.career-detail {
  min-width: 0;
}
button,
input,
select,
textarea {
  font: inherit;
  font-size: 13px;
}
button {
  min-height: 44px;
  padding: 10px 14px;
  border: 1px solid var(--accent-border);
  border-radius: 10px;
  color: var(--accent);
  background: var(--bg-elevated);
  cursor: pointer;
}
button:hover:enabled {
  border-color: var(--accent);
}
button:disabled {
  opacity: 0.5;
  cursor: default;
}
.primary {
  background: var(--accent);
  color: #fff;
}
.danger {
  color: #b44b4b;
}
.position-row {
  display: grid;
  gap: 6px;
  text-align: left;
  width: 100%;
  padding: 16px 12px;
  margin: 8px 0;
  background: transparent;
}
.position-row.chosen {
  background: var(--accent-soft);
  border-color: var(--accent);
}
.position-row strong {
  color: var(--text-primary);
  font-size: 16px;
}
.position-row span {
  overflow-wrap: anywhere;
}
.catalog {
  margin-top: 24px;
  border-top: 1px solid var(--border-subtle);
  padding-top: 18px;
}
.catalog summary,
.operation-log summary {
  cursor: pointer;
  font-weight: 600;
  font-size: 14px;
  min-height: 44px;
}
.catalog-row {
  display: grid;
  gap: 8px;
  padding: 16px 0;
  border-top: 1px solid var(--border-subtle);
  font-size: 13px;
}
.catalog-row strong {
  font-size: 15px;
}
.catalog-row button {
  justify-self: start;
}
label {
  display: grid;
  gap: 8px;
  font-size: 13px;
  margin: 12px 0;
}
input:not([type="radio"]),
select,
textarea {
  min-width: 0;
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--border-default);
  border-radius: 10px;
  padding: 10px;
  color: var(--text-primary);
  background: var(--bg-surface);
  min-height: 44px;
}
textarea {
  resize: vertical;
  line-height: 1.7;
}
input:read-only,
textarea:read-only {
  background: var(--bg-elevated);
}
.form-grid,
.requirement-edit {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 0 16px;
}
.wide {
  grid-column: 1/-1;
}
.requirement-edit {
  padding: 12px 0;
  border-top: 1px solid var(--border-subtle);
}
.requirement-edit button {
  justify-self: start;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.file-label {
  margin: 0;
  max-width: 260px;
}
.file-label input {
  padding: 8px;
}
.description {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.requirements {
  list-style: none;
  padding: 0;
}
.requirements li {
  padding: 12px 0;
  border-top: 1px solid var(--border-subtle);
}
.requirements strong {
  display: block;
  font-size: 14px;
  color: var(--accent);
}
q {
  display: block;
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 8px;
}
.training-path {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  border-top: 1px solid var(--border-subtle);
  padding-top: 20px;
  margin-top: 20px;
}
.training-path > div {
  display: grid;
  gap: 12px;
}
.training-path span {
  font-size: 12px;
  color: var(--text-secondary);
}
.evidence-row {
  border-top: 1px solid var(--border-subtle);
  padding: 14px 0;
}
.evidence-row .section-head {
  margin: 0;
}
.evidence-row h3 {
  margin: 0;
}
.evidence-row span {
  color: var(--accent);
  font-size: 12px;
}
.evidence-row p,
.evidence-row li {
  font-size: 13px;
}
.evidence-row ul {
  padding-left: 18px;
  line-height: 1.9;
  overflow-wrap: anywhere;
}
.evidence-link {
  display: block;
  padding: 12px 0;
  line-height: 1.6;
  min-height: 20px;
  border-bottom: 1px solid var(--border-subtle);
  font-size: 13px;
  color: var(--accent);
  overflow-wrap: anywhere;
}
a:focus-visible,
button:focus-visible,
input:focus-visible,
select:focus-visible,
textarea:focus-visible,
summary:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
}
.history-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  margin: 8px 0;
  text-align: left;
}
.basic-question {
  padding: 12px 0;
  border-top: 1px solid var(--border-subtle);
}
.choice {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  margin: 0;
}
.choice input {
  accent-color: var(--accent);
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}
.error,
.notice {
  padding: 12px 16px;
  border: 1px solid #ecd2bc;
  border-radius: 10px;
  line-height: 1.8;
  overflow-wrap: anywhere;
  background: #fff8f5;
  color: #965631;
}
.notice {
  background: var(--accent-soft);
  border-color: var(--accent-border);
  color: var(--accent);
}
.welcome {
  min-height: 220px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.operation-log li {
  line-height: 2;
  font-size: 13px;
}
@media (max-width: 1050px) {
  .career-layout {
    grid-template-columns: minmax(230px, 0.7fr) minmax(0, 1.3fr);
    gap: 16px;
  }
  .panel {
    padding: 18px;
  }
  .training-path {
    grid-template-columns: 1fr;
  }
  .training-path > div {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }
}
@media (max-width: 720px) {
  .career-layout {
    grid-template-columns: 1fr;
  }
  .page-heading {
    align-items: start;
  }
  .page-heading h1 {
    font-size: 25px;
  }
  .page-heading > button {
    flex-shrink: 0;
  }
  .panel {
    padding: 16px;
  }
  .form-grid,
  .requirement-edit {
    grid-template-columns: 1fr;
  }
  .section-head {
    flex-wrap: wrap;
  }
  .history-row {
    flex-wrap: wrap;
  }
  .requirements q {
    overflow-wrap: anywhere;
  }
}
</style>
