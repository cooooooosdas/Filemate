<template>
  <div class="interview-bank-page">
    <header class="page-head">
      <div>
        <h1>面试题库管理</h1>
        <p>按场景和难度维护模拟面试题目，题目会参与面试创建时的自动选题。</p>
      </div>
    </header>

    <section class="bank-toolbar">
      <el-select v-model="filters.scenario" aria-label="按场景筛选" placeholder="全部场景" clearable @change="load">
        <el-option v-for="item in scenarios" :key="item" :label="item" :value="item" />
      </el-select>
      <el-select v-model="filters.difficulty" aria-label="按难度筛选" placeholder="全部难度" clearable @change="load">
        <el-option v-for="item in difficulties" :key="item" :label="item" :value="item" />
      </el-select>
      <el-button type="primary" @click="openCreate">新增题目</el-button>
    </section>

    <DataState v-if="loading" loading />
    <DataState v-else-if="loadError" :error="loadError" @retry="load" />
    <DataState v-else-if="questions.length === 0" empty empty-text="当前筛选下暂无题目，可新增第一道题。" />
    <template v-else>
      <p class="result-count" aria-live="polite">
        {{ questions.length === 500 ? '已显示前 500 道题，请使用筛选缩小范围' : `共 ${questions.length} 道题` }}
      </p>
      <el-table :data="questions" class="bank-table">
        <el-table-column prop="scenario" label="场景" width="140" />
        <el-table-column prop="difficulty" label="难度" width="110" />
        <el-table-column prop="text" label="题目" min-width="280" show-overflow-tooltip />
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <el-switch
              v-model="row.enabled"
              :active-value="1"
              :inactive-value="0"
              :disabled="isPending(row.id)"
              :aria-label="`${row.text}启用状态`"
              @change="toggle(row)"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button :disabled="isPending(row.id)" @click="openEdit(row)">编辑</el-button>
            <el-button type="danger" plain :loading="isPending(row.id)" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="bank-cards">
        <article v-for="row in questions" :key="row.id" class="question-card">
          <header>
            <div><span>{{ row.scenario }}</span><b>{{ row.difficulty }}</b></div>
            <el-switch
              v-model="row.enabled"
              :active-value="1"
              :inactive-value="0"
              :disabled="isPending(row.id)"
              :aria-label="`${row.text}启用状态`"
              @change="toggle(row)"
            />
          </header>
          <p>{{ row.text }}</p>
          <footer>
            <el-button :disabled="isPending(row.id)" @click="openEdit(row)">编辑</el-button>
            <el-button type="danger" plain :loading="isPending(row.id)" @click="remove(row)">删除</el-button>
          </footer>
        </article>
      </div>
    </template>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑题目' : '新增题目'"
      width="min(560px, calc(100vw - 32px))"
      :close-on-click-modal="!saving"
      :close-on-press-escape="!saving"
    >
      <el-form label-position="top">
        <el-form-item label="场景">
          <el-select v-model="form.scenario" style="width: 100%">
            <el-option v-for="item in scenarios" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="难度">
          <el-select v-model="form.difficulty" style="width: 100%">
            <el-option v-for="item in difficulties" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="题目内容">
          <el-input v-model="form.text" type="textarea" :rows="4" maxlength="1000" show-word-limit placeholder="输入面试题目" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="saving" @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" :disabled="!form.text.trim()" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import DataState from '../components/DataState.vue'
import {
  createInterviewQuestion,
  deleteInterviewQuestion,
  getInterviewQuestions,
  updateInterviewQuestion,
  type InterviewQuestion
} from '../services/api'

const scenarios = ['求职面试', '竞赛答辩', '保研复试']
const difficulties = ['入门', '标准', '压力面']
const filters = reactive({ scenario: '', difficulty: '' })
const questions = ref<InterviewQuestion[]>([])
const loading = ref(false)
const loadError = ref('')
const dialogVisible = ref(false)
const editingId = ref('')
const saving = ref(false)
const pendingIds = ref<string[]>([])
const form = reactive({ scenario: '求职面试', difficulty: '入门', text: '', enabled: true })
let loadSequence = 0

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

function isPending(questionId: string): boolean {
  return pendingIds.value.includes(questionId)
}

function setPending(questionId: string, pending: boolean): void {
  pendingIds.value = pending
    ? [...pendingIds.value, questionId]
    : pendingIds.value.filter((item) => item !== questionId)
}

async function load(): Promise<void> {
  const sequence = ++loadSequence
  loading.value = true
  loadError.value = ''
  try {
    const result = await getInterviewQuestions({
      scenario: filters.scenario || undefined,
      difficulty: filters.difficulty || undefined,
      limit: 500
    })
    if (sequence === loadSequence) questions.value = result
  } catch (error: unknown) {
    if (sequence === loadSequence) loadError.value = errorMessage(error, '加载题库失败')
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

function openCreate(): void {
  editingId.value = ''
  Object.assign(form, { scenario: '求职面试', difficulty: '入门', text: '', enabled: true })
  dialogVisible.value = true
}

function openEdit(row: InterviewQuestion): void {
  editingId.value = row.id
  Object.assign(form, {
    scenario: row.scenario,
    difficulty: row.difficulty,
    text: row.text,
    enabled: Boolean(row.enabled)
  })
  dialogVisible.value = true
}

async function save(): Promise<void> {
  const payload = {
    scenario: form.scenario,
    difficulty: form.difficulty,
    text: form.text.trim(),
    enabled: form.enabled
  }
  saving.value = true
  try {
    if (editingId.value) {
      await updateInterviewQuestion(editingId.value, payload)
      ElMessage.success('题目已更新')
    } else {
      await createInterviewQuestion(payload)
      ElMessage.success('题目已新增')
    }
    dialogVisible.value = false
    await load()
  } catch (error: unknown) {
    ElMessage.error(errorMessage(error, '保存失败'))
  } finally {
    saving.value = false
  }
}

async function toggle(row: InterviewQuestion): Promise<void> {
  setPending(row.id, true)
  try {
    await updateInterviewQuestion(row.id, { enabled: Boolean(row.enabled) })
    ElMessage.success(row.enabled ? '已启用' : '已停用')
  } catch (error: unknown) {
    ElMessage.error(errorMessage(error, '状态更新失败'))
    await load()
  } finally {
    setPending(row.id, false)
  }
}

async function remove(row: InterviewQuestion): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定删除“${row.text}”吗？删除后无法恢复。`,
      '删除面试题目',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  setPending(row.id, true)
  try {
    await deleteInterviewQuestion(row.id)
    ElMessage.success('题目已删除')
    await load()
  } catch (error: unknown) {
    ElMessage.error(errorMessage(error, '删除失败'))
  } finally {
    setPending(row.id, false)
  }
}

onMounted(load)
</script>

<style scoped>
.interview-bank-page {
  max-width: 1180px;
  margin: 0 auto;
  padding: 28px;
  color: var(--text-primary);
}
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: end;
  margin-bottom: 24px;
}
.page-head h1 {
  font-size: 32px;
  margin: 0 0 7px;
}
.page-head p {
  margin: 0;
  color: var(--text-secondary);
}
.bank-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 18px;
}
.bank-toolbar .el-select {
  width: 180px;
}
.result-count {
  margin: 0 0 10px;
  color: var(--text-muted);
  font-size: var(--type-meta);
}
.bank-table {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
}
.bank-cards {
  display: none;
}
@media (max-width: 720px) {
  .interview-bank-page {
    padding: 16px;
  }
  .page-head {
    align-items: flex-start;
  }
  .page-head h1 {
    font-size: 28px;
  }
  .bank-toolbar {
    align-items: stretch;
    flex-direction: column;
  }
  .bank-toolbar .el-select,
  .bank-toolbar .el-button {
    width: 100%;
    min-height: 44px;
  }
  .bank-table {
    display: none;
  }
  .bank-cards {
    display: grid;
    gap: 12px;
  }
  .question-card {
    padding: 16px;
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 14px;
  }
  .question-card header,
  .question-card footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .question-card header div {
    display: flex;
    gap: 8px;
    color: var(--text-secondary);
    font-size: var(--type-meta);
  }
  .question-card header b {
    color: var(--accent);
  }
  .question-card p {
    margin: 16px 0;
    line-height: 1.7;
    overflow-wrap: anywhere;
  }
  .question-card footer {
    justify-content: flex-end;
    padding-top: 12px;
    border-top: 1px solid var(--border-subtle);
  }
  .question-card footer .el-button {
    min-width: 72px;
    min-height: 44px;
  }
}
</style>
