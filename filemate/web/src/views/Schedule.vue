<template>
  <div class="schedule-page">
    <el-alert
      title="请先在导入页面上传文件"
      type="info"
      :closable="false"
      v-if="!currentFile"
    />

    <template v-else>
      <el-card>
        <template #header>
          <h3>📅 日程预览</h3>
        </template>

        <div v-if="milestones.length === 0">
          <el-empty description="暂无里程碑" />
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
            <el-button type="primary" @click="downloadIcs">
              <el-icon><Download /></el-icon>
              下载 .ics 文件
            </el-button>
          </div>
        </div>
      </el-card>

      <!-- ECharts 时间轴图表 -->
      <el-card style="margin-top: 20px">
        <template #header>
          <span>可视化时间轴</span>
        </template>
        <div ref="chartRef" style="height: 300px"></div>
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Download } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import type { Milestone } from '../types'
import { useFileStore } from '../stores/fileStore'
import { getSession, getIcsContent, downloadIcs as downloadIcsApi } from '../services/api'

const route = useRoute()
const fileStore = useFileStore()
const chartRef = ref<HTMLElement>()
const milestones = ref<Milestone[]>([])
const currentFile = computed(() => fileStore.currentFile)

watch(currentFile, (file) => {
  if (file?.milestones) {
    milestones.value = file.milestones
    updateChart()
  }
})

onMounted(async () => {
  const sessionId = route.query.session as string
  if (sessionId) {
    const session = await getSession(sessionId)
    fileStore.setCurrentFile(session)
  }
  initChart()
})

function getTimelineType(idx: number): 'primary' | 'success' | 'warning' | 'danger' {
  const types: ('primary' | 'success' | 'warning' | 'danger')[] = ['primary', 'success', 'warning', 'danger']
  return types[idx % 4]
}

async function downloadIcs() {
  if (!currentFile.value) return
  try {
    const content = await getIcsContent(currentFile.value.session_id)
    downloadIcsApi(content, `${currentFile.value.suggested_name}.ics`)
  } catch (e) {
    console.error('Failed to download ICS:', e)
  }
}

function initChart() {
  if (!chartRef.value) return
  updateChart()
}

function updateChart() {
  if (!chartRef.value || milestones.value.length === 0) return

  const chart = echarts.init(chartRef.value)

  const dates = milestones.value.map(m => m.date)
  const events = milestones.value.map(m => m.event)

  const option = {
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: dates
    },
    yAxis: {
      type: 'category',
      data: events,
      inverse: true
    },
    series: [
      {
        type: 'bar',
        data: milestones.value.map((_, i) => ({
          value: events.length - i,
          itemStyle: { color: '#409eff' }
        })),
        label: { show: true, position: 'right' }
      }
    ]
  }

  chart.setOption(option)
}
</script>

<style scoped>
.schedule-page {
  max-width: 1000px;
  margin: 0 auto;
}

.ics-actions {
  margin-top: 20px;
  text-align: center;
}
</style>