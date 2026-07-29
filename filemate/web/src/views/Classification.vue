<template>
  <div class="classification-page">
    <el-alert
      title="请先在导入页面上传文件"
      type="info"
      :closable="false"
      v-if="!currentFile"
    />

    <template v-else>
      <el-card>
        <template #header>
          <div class="card-header">
            <h3>🏷️ 分类预览</h3>
          </div>
        </template>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-card shadow="hover">
              <template #header>
                <span>分类结果</span>
              </template>
              <div class="result-item">
                <el-tag type="primary" size="large">
                  {{ currentFile.category || '待确认' }}
                </el-tag>
                <span class="confidence">
                  置信度: {{ (currentFile.confidence * 100).toFixed(1) }}%
                </span>
              </div>
            </el-card>
          </el-col>

          <el-col :span="12">
            <el-card shadow="hover">
              <template #header>
                <span>修改分类</span>
              </template>
              <el-select v-model="selectedCategory" placeholder="选择分类" style="width: 100%">
                <el-option label="课件" value="课件" />
                <el-option label="作业" value="作业" />
                <el-option label="竞赛通知" value="竞赛通知" />
                <el-option label="考试通知" value="考试通知" />
                <el-option label="参考资料" value="参考资料" />
                <el-option label="大创通知" value="大创通知" />
                <el-option label="待确认" value="待确认" />
              </el-select>
              <el-button
                type="primary"
                style="margin-top: 12px"
                @click="confirmCategory"
                :loading="confirming"
              >
                确认分类
              </el-button>
            </el-card>
          </el-col>
        </el-row>
      </el-card>

      <!-- ECharts 饼图：分类统计 -->
      <el-card style="margin-top: 20px">
        <template #header>
          <span>分类分布（待实现）</span>
        </template>
        <div ref="chartRef" style="height: 300px"></div>
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getSession, confirmSession } from '../services/api'
import { useFileStore } from '../stores/fileStore'
import type { Category } from '../types'
import * as echarts from 'echarts'

const route = useRoute()
const fileStore = useFileStore()
const chartRef = ref<HTMLElement>()

const currentFile = computed(() => fileStore.currentFile)
const selectedCategory = ref<Category | ''>('')
const confirming = ref(false)

watch(currentFile, (file) => {
  if (file) {
    selectedCategory.value = file.category
  }
})

onMounted(() => {
  const sessionId = route.query.session as string
  if (sessionId) {
    loadSession(sessionId)
  }
  initChart()
})

async function loadSession(sessionId: string) {
  try {
    const session = await getSession(sessionId)
    fileStore.setCurrentFile(session)
  } catch (e) {
    console.error('Failed to load session:', e)
  }
}

async function confirmCategory() {
  if (!currentFile.value) return

  confirming.value = true
  try {
    const result = await confirmSession(currentFile.value.session_id, {
      accepted: true,
      edits: { category: selectedCategory.value }
    })

    if (result.ok) {
      ElMessage.success('分类已确认')
      fileStore.updateFile({
        ...currentFile.value,
        category: selectedCategory.value
      })
    } else {
      ElMessage.error(result.error || '确认失败')
    }
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    confirming.value = false
  }
}

function initChart() {
  if (!chartRef.value) return

  const chart = echarts.init(chartRef.value)
  const option = {
    tooltip: { trigger: 'item' },
    legend: { orient: 'vertical', left: 'left' },
    series: [
      {
        name: '分类',
        type: 'pie',
        radius: '50%',
        data: [
          { value: 35, name: '课件' },
          { value: 28, name: '作业' },
          { value: 15, name: '竞赛通知' },
          { value: 12, name: '考试通知' },
          { value: 10, name: '参考资料' }
        ],
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: 'rgba(0, 0, 0, 0.5)'
          }
        }
      }
    ]
  }
  chart.setOption(option)
}
</script>

<style scoped>
.classification-page {
  max-width: 1000px;
  margin: 0 auto;
}

.card-header h3 {
  margin: 0;
}

.result-item {
  display: flex;
  align-items: center;
  gap: 16px;
}

.confidence {
  color: #888;
  font-size: 14px;
}
</style>