<template>
  <div class="home-page">
    <el-card class="welcome-card">
      <h2>欢迎使用 FileMate</h2>
      <p class="description">
        智能文件管理，助你梳理工作脉络。从这里开始，上传文件开始处理。
      </p>
      <div class="quick-actions">
        <el-button type="primary" size="large" @click="$router.push('/import')">
          <el-icon><Upload /></el-icon>
          立即上传文件
        </el-button>
        <el-button size="large" @click="$router.push('/history')">
          <el-icon><Clock /></el-icon>
          查看历史
        </el-button>
      </div>
    </el-card>

    <el-row :gutter="20" class="stats-row">
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic title="已处理文件" :value="stats.total" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic title="本周处理" :value="stats.week" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic title="待确认" :value="stats.pending" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic title="已完成" :value="stats.completed" />
        </el-card>
      </el-col>
    </el-row>

    <el-card class="features-card">
      <template #header>
        <h3>功能概览</h3>
      </template>
      <el-row :gutter="20">
        <el-col :span="6">
          <div class="feature-item">
            <el-icon size="32" color="#409eff"><Upload /></el-icon>
            <h4>智能导入</h4>
            <p>支持 Word、PDF、PPT 等多种格式</p>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="feature-item">
            <el-icon size="32" color="#67c23a"><Collection /></el-icon>
            <h4>自动分类</h4>
            <p>AI 智能识别文件类型和内容</p>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="feature-item">
            <el-icon size="32" color="#e6a23c"><Edit /></el-icon>
            <h4>命名建议</h4>
            <p>规范化文件名，易于查找</p>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="feature-item">
            <el-icon size="32" color="#f56c6c"><Calendar /></el-icon>
            <h4>日程同步</h4>
            <p>自动生成日历事件</p>
          </div>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Upload, Clock } from '@element-plus/icons-vue'
import { getHistory } from '../services/api'

const stats = ref({
  total: 0,
  week: 0,
  pending: 0,
  completed: 0
})

onMounted(async () => {
  try {
    const history = await getHistory(undefined, 100)
    stats.value.total = history.length

    const now = new Date()
    const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
    stats.value.week = history.filter((h: any) =>
      new Date(h.created_at) >= weekAgo
    ).length

    stats.value.pending = history.filter((h: any) =>
      h.status === 'pending' || h.status === 'processing' || h.status === 'done'
    ).length

    stats.value.completed = history.filter((h: any) =>
      h.status === 'confirmed'
    ).length
  } catch (e) {
    console.error('Failed to load stats:', e)
  }
})
</script>

<style scoped>
.home-page {
  max-width: 1200px;
  margin: 0 auto;
}

.welcome-card {
  margin-bottom: 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.welcome-card h2 {
  margin: 0 0 10px 0;
}

.description {
  font-size: 16px;
  opacity: 0.9;
  margin-bottom: 20px;
}

.quick-actions {
  display: flex;
  gap: 12px;
}

.stats-row {
  margin-bottom: 20px;
}

.stat-card {
  text-align: center;
}

.features-card {
  margin-top: 20px;
}

.features-card h3 {
  margin: 0;
}

.feature-item {
  text-align: center;
  padding: 20px;
}

.feature-item h4 {
  margin: 12px 0 8px 0;
}

.feature-item p {
  font-size: 13px;
  color: #888;
  margin: 0;
}
</style>