<template>
      <el-tabs v-model="settingsTab" class="preferences-tabs">
        <el-tab-pane label="外观" name="appearance"><PreferencePanelLoader kind="appearance" /></el-tab-pane>
        <el-tab-pane label="保存位置" name="downloads" lazy><PreferencePanelLoader kind="downloads" /></el-tab-pane>
        <el-tab-pane label="模型服务" name="model" lazy><SettingsPanelLoader :backend-connected="backendConnected" :active="settingsTab === 'model'" /></el-tab-pane>
        <el-tab-pane label="连接状态" name="connection" lazy>
          <section class="connection-settings"><h3>{{ backendConnected ? '学习服务已连接' : '学习服务暂未连接' }}</h3><p>{{ backendConnected ? '可以导入、查看和保存资料。' : '请检查网络或本机服务，再重新连接。' }}</p><el-button type="primary" :loading="serviceChecking" @click="$emit('reconnect')">重新连接</el-button><p>{{ accountsEnabled ? '学习资料保存在账号的服务器私有空间；保存位置设置仅影响本机导出文件。' : '学习资料由本机服务保存；保存位置设置仅影响导出文件。' }}</p></section>
        </el-tab-pane>
      </el-tabs>
</template>
<script setup lang="ts">
import PreferencePanelLoader from './PreferencePanelLoader.vue'
import SettingsPanelLoader from './SettingsPanelLoader.vue'
const settingsTab = defineModel<string>('tab', { default: 'appearance' })
defineProps<{ backendConnected: boolean | null; serviceChecking: boolean; accountsEnabled: boolean }>()
defineEmits<{ reconnect: [] }>()
</script>
<style scoped>
.preferences-tabs{min-width:0}.preferences-tabs :deep(.el-tabs__item){font-size:17px;min-height:48px}.connection-settings h3{font-size:25px;line-height:1.5}.connection-settings p{font-size:17px;line-height:1.8;color:var(--text-secondary)}
</style>
