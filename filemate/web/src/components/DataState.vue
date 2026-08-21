<!--
  DataState — 数据页统一「加载/错误/空」状态组件
  用法：
    <DataState
      :loading="loading"
      :error="error"
      :empty="!items.length"
      empty-text="暂无数据"
      @retry="load"
    >
      ...数据内容（default slot）...
    </DataState>
  - loading / error / empty 同时只命中一个（按此优先级）。
  - error 时展示原因 + 重试按钮（emit 'retry'）。
  - empty 时展示 empty-text 或 default slot 里的空态内容。
-->
<template>
  <div v-if="loading" class="data-state" role="status">
    <span class="spinner" aria-hidden="true"></span>
    <span>加载中…</span>
  </div>
  <div v-else-if="error" class="data-state is-error" role="alert">
    <strong>加载失败</strong>
    <span>{{ error }}</span>
    <button type="button" class="retry-btn" @click="$emit('retry')">重试</button>
  </div>
  <div v-else-if="empty" class="data-state is-empty">
    <slot>{{ emptyText }}</slot>
  </div>
  <slot v-else />
</template>

<script setup lang="ts">
defineProps<{
  loading?: boolean
  error?: string
  empty?: boolean
  emptyText?: string
}>()
defineEmits<{ retry: [] }>()
</script>

<style scoped>
.data-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 160px;
  padding: 24px;
  text-align: center;
  color: var(--text-muted);
  background: var(--bg-surface);
  border: 1px dashed var(--border-default);
  border-radius: 14px;
}

.data-state strong {
  font-size: 15px;
  color: var(--text-primary);
}

.data-state.is-error span {
  font-size: 13px;
  color: var(--text-muted);
}

.retry-btn {
  padding: 9px 16px;
  border: 0;
  border-radius: 9px;
  background: var(--accent);
  color: #fff;
  font-weight: 700;
  cursor: pointer;
}

.retry-btn:hover {
  opacity: 0.9;
}

.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid var(--bg-elevated);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
