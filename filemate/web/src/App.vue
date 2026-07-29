<template>
  <el-container class="app-container">
    <!-- 侧边栏 -->
    <el-aside width="220px" class="sidebar">
      <div class="logo">
        <h1>📁 FileMate</h1>
        <p class="tagline">智能文件管理</p>
      </div>
      <el-menu
        :default-active="currentRoute"
        :router="true"
        class="sidebar-menu"
      >
        <el-menu-item index="/">
          <el-icon><House /></el-icon>
          <span>首页</span>
        </el-menu-item>
        <el-menu-item index="/import">
          <el-icon><Upload /></el-icon>
          <span>导入文件</span>
        </el-menu-item>
        <el-menu-item index="/classification">
          <el-icon><Collection /></el-icon>
          <span>分类预览</span>
        </el-menu-item>
        <el-menu-item index="/naming">
          <el-icon><Edit /></el-icon>
          <span>命名预览</span>
        </el-menu-item>
        <el-menu-item index="/schedule">
          <el-icon><Calendar /></el-icon>
          <span>日程预览</span>
        </el-menu-item>
        <el-menu-item index="/history">
          <el-icon><Clock /></el-icon>
          <span>历史记录</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- 主内容区 -->
    <el-container>
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { House, Upload, Collection, Edit, Calendar, Clock } from '@element-plus/icons-vue'

const route = useRoute()
const currentRoute = computed(() => route.path)
</script>

<style scoped>
.app-container {
  height: 100vh;
}

.sidebar {
  background-color: #1a1a2e;
  color: white;
}

.logo {
  padding: 20px;
  text-align: center;
  border-bottom: 1px solid #333;
}

.logo h1 {
  font-size: 24px;
  margin: 0;
  color: #fff;
}

.tagline {
  font-size: 12px;
  color: #888;
  margin: 4px 0 0 0;
}

.sidebar-menu {
  border: none;
  background-color: transparent;
}

.sidebar-menu .el-menu-item {
  color: #ccc;
  margin: 4px 8px;
  border-radius: 8px;
}

.sidebar-menu .el-menu-item:hover,
.sidebar-menu .el-menu-item.is-active {
  background-color: #16213e;
  color: #fff;
}

.main-content {
  background-color: #f5f7fa;
  padding: 20px;
}
</style>