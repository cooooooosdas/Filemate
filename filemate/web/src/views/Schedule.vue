<template>
  <div class="schedule-page">
    <WorkflowSteps :current="4" />
    <section v-if="!currentFile && !loadError" class="schedule-entry-empty">
      <div class="empty-icon-wrap">
        <el-icon size="42"><Calendar /></el-icon>
      </div>
      <div class="empty-copy">
        <span>还差一份资料</span>
        <h2>导入资料后，重要日期会自动排成日程</h2>
        <p>FileMate 会从资料中提取截止日期与关键事项；所有结果都可先核对，再下载为日历文件。</p>
      </div>
      <el-button type="primary" @click="$router.push('/import')">
        <el-icon><Upload /></el-icon>
        导入资料
      </el-button>
    </section>

    <el-card v-else-if="loadError">
      <DataState :error="loadError" @retry="loadSession" />
    </el-card>

    <template v-else>
      <el-card>
        <template #header>
          <h3><el-icon><Calendar /></el-icon> 日程预览</h3>
        </template>

        <div v-if="milestones.length === 0" class="empty-schedule">
          <div class="empty-icon-wrap">
            <el-icon size="64"><Clock /></el-icon>
          </div>
          <h4>暂无日程安排</h4>
          <p>上传文件后，系统将自动提取其中的日期和里程碑信息</p>
          <el-button type="primary" @click="$router.push('/import')">
            <el-icon><Upload /></el-icon>
            前往导入
          </el-button>
        </div>

        <div v-else>
          <el-timeline>
            <el-timeline-item
              v-for="(m, idx) in milestones"
              :key="idx"
              :timestamp="m.date"
              :type="getTimelineType(idx)"
              placement="top"
            >
              <el-card shadow="hover">
                <h4>{{ m.event }}</h4>
              </el-card>
            </el-timeline-item>
          </el-timeline>

          <el-divider />

          <div class="ics-actions">
            <el-button type="primary" :loading="icsLoading" @click="downloadIcs">
              <el-icon><Download /></el-icon>
              {{ icsLoading ? '下载中…' : '下载 .ics 文件' }}
            </el-button>
          </div>
        </div>
      </el-card>

      <!-- ECharts 时间轴图表 -->
      <el-card v-if="milestones.length" style="margin-top: 20px">
        <template #header>
          <span>可视化时间轴</span>
        </template>
        <div ref="chartRef" style="height: 300px"></div>
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { Download, Calendar, Clock, Upload } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { Milestone } from '../types'
import { useFileStore } from '../stores/fileStore'
import { getSession, getIcsContent, downloadIcs as downloadIcsApi } from '../services/api'
import DataState from '../components/DataState.vue'
import WorkflowSteps from '../components/WorkflowSteps.vue'

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const route = useRoute()
const fileStore = useFileStore()
const chartRef = ref<HTMLElement>()
let chartInstance: ReturnType<typeof echarts.init> | null = null
const milestones = ref<Milestone[]>([])
const icsLoading = ref(false)
const loadError = ref('')
const currentFile = computed(() => fileStore.currentFile)

watch(currentFile, (file) => {
  if (file?.milestones) {
    milestones.value = file.milestones
    nextTick(() => {
      initChart()
      updateChart()
    })
  }
}, { immediate: true })

function handleChartResize() {
  chartInstance?.resize()
}

async function loadSession() {
  const sessionId = route.query.session as string
  if (!sessionId) {
    fileStore.setCurrentFile(null)
    return
  }
  loadError.value = ''
  fileStore.setCurrentFile(null)
  try {
    const session = await getSession(sessionId)
    fileStore.setCurrentFile(session)
  } catch (e: any) {
    loadError.value = e?.message || '日程加载失败'
  }
}

onMounted(async () => {
  await loadSession()
  await nextTick()
  initChart()
  window.addEventListener('resize', handleChartResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleChartResize)
  chartInstance?.dispose()
  chartInstance = null
})

function getTimelineType(idx: number): 'primary' | 'success' | 'warning' | 'danger' {
  const types: ('primary' | 'success' | 'warning' | 'danger')[] = ['primary', 'success', 'warning', 'danger']
  return types[idx % 4]
}

async function downloadIcs() {
  if (!currentFile.value) return
  icsLoading.value = true
  try {
    const content = await getIcsContent(currentFile.value.session_id)
    downloadIcsApi(content, `${currentFile.value.suggested_name}.ics`)
    ElMessage.success('日历文件已下载')
  } catch (e: any) {
    ElMessage.error(e?.message || '日历文件下载失败，请重试')
  } finally {
    icsLoading.value = false
  }
}

function initChart() {
  if (!chartRef.value) return
  updateChart()
}

function updateChart() {
  if (!chartRef.value || milestones.value.length === 0) return

  // 只 init 一次，后续用 setOption 更新，避免重复初始化告警与实例泄漏
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }
  const chart = chartInstance

  const dates = milestones.value.map(m => m.date)
  const events = milestones.value.map(m => m.event)

  const option = {
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#ffffff',
      borderColor: '#b9d4c0',
      borderWidth: 1,
      textStyle: { color: '#183229' }
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: '#d7e3d9' } },
      axisLabel: { color: '#4d655b' }
    },
    yAxis: {
      type: 'category',
      data: events,
      inverse: true,
      axisLine: { lineStyle: { color: '#d7e3d9' } },
      axisLabel: { color: '#4d655b' }
    },
    series: [
      {
        type: 'bar',
        data: milestones.value.map((_, i) => ({
          value: events.length - i,
          itemStyle: {
            color: {
              type: 'linear',
              x: 0, y: 0, x2: 1, y2: 0,
              colorStops: [
                { offset: 0, color: '#10b981' },
                { offset: 1, color: '#34d399' }
              ]
            },
            borderRadius: [0, 4, 4, 0]
          }
        })),
        label: {
          show: true,
          position: 'right',
            color: '#4d655b',
          fontSize: 11
        },
        barWidth: '60%',
        itemStyle: {
          emphasis: {
            shadowBlur: 10,
            shadowColor: 'rgba(16, 185, 129, 0.3)'
          }
        }
      }
    ],
    grid: {
      left: '3%',
      right: '10%',
      bottom: '3%',
      top: '3%',
      containLabel: true
    }
  }

  chart.setOption(option)
}
</script>

<style scoped>
.schedule-page {
  max-width: 1000px;
  margin: 0 auto;
}

.schedule-entry-empty {
  min-height: 280px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 22px;
  padding: 40px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-panel);
  background:
    radial-gradient(circle at 92% 14%, rgba(37, 99, 235, 0.1), transparent 30%),
    linear-gradient(135deg, var(--bg-surface), #f3faf6);
}

.schedule-entry-empty .empty-icon-wrap {
  margin: 0;
  width: 84px;
  height: 84px;
  color: var(--brand-blue);
  background: var(--brand-blue-soft);
  border: 1px solid var(--brand-blue-border);
}

.empty-copy span {
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
}

.empty-copy h2 {
  margin: 7px 0 9px;
  font-size: 22px;
  line-height: 1.35;
}

.empty-copy p {
  max-width: 560px;
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.7;
}

/* Empty state styling */
.empty-schedule {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 24px;
  text-align: center;
  background: var(--bg-card);
  border: 1px dashed var(--border-default);
  border-radius: var(--radius-lg);
}

.empty-icon-wrap {
  width: 100px;
  height: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(16, 185, 129, 0.06);
  border-radius: 50%;
  margin-bottom: 20px;
}

.empty-icon-wrap .el-icon {
  color: var(--accent-primary, #10b981);
}

.empty-schedule h4 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px;
}

.empty-schedule p {
  font-size: 14px;
  color: var(--text-muted);
  margin: 0 0 20px;
  max-width: 320px;
}

.ics-actions {
  margin-top: 20px;
  text-align: center;
}

@media (max-width: 700px) {
  .schedule-entry-empty {
    min-height: 360px;
    grid-template-columns: 1fr;
    justify-items: start;
    align-content: center;
    padding: 28px 24px;
  }

  .schedule-entry-empty .el-button {
    min-height: 44px;
  }
}
</style>
