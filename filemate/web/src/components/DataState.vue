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
  <div v-if="loading" class="data-state" :class="{ compact }" role="status" aria-live="polite">
    <span class="spinner" aria-hidden="true"></span>
    <span>加载中…</span>
  </div>
  <div v-else-if="error" class="data-state is-error" :class="{ compact }" role="alert">
    <strong>加载失败</strong>
    <span>{{ error }}</span>
    <button type="button" class="retry-btn" @click="$emit('retry')">重试</button>
  </div>
  <div v-else-if="empty" class="data-state is-empty" :class="{ compact }">
    <slot name="icon"><svg class="empty-icon" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10H3Z"/><path d="M8 12h8m-8 4h5"/></svg></slot>
    <div class="empty-copy"><h3 v-if="title">{{ title }}</h3><slot name="empty"><slot>{{ emptyText }}</slot></slot><div v-if="$slots.action" class="empty-action"><slot name="action" /></div></div>
  </div>
  <slot v-else />
</template>

<script setup lang="ts">
defineProps<{
  loading?: boolean
  error?: string
  empty?: boolean
  emptyText?: string
  title?: string
  compact?: boolean
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
  min-height: 260px;
  padding: 48px 24px;
  text-align: center;
  color: var(--text-secondary);
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: 14px;
}
.empty-copy { min-width:0;max-width:720px;overflow-wrap:anywhere;font-size:17px;line-height:1.8; }.empty-copy h3 { margin:0 0 12px;font-size:24px;line-height:1.5;color:var(--text-primary); }.empty-action { margin:16px 0 24px; }.data-state.compact { min-height:132px;padding:24px;flex-direction:row;text-align:left;justify-content:flex-start;gap:20px; }.compact .empty-copy h3 { font-size:21px;margin-bottom:4px; }.compact .empty-action { margin:8px 0 0; }.compact .empty-copy :deep(p) { margin:0; }.data-state :deep(.el-icon) { flex-shrink:0;font-size:32px;color:var(--accent); }.empty-action :deep(a) { display:inline-flex;align-items:center;min-height:44px;gap:8px;color:var(--accent);font-size:17px; }
.empty-icon{flex-shrink:0;color:var(--accent)}

.data-state strong {
  font-size: 18px;
  color: var(--text-primary);
}

.data-state.is-error span {
  font-size: var(--type-meta);
  color: var(--text-muted);
}

.retry-btn {
  min-height:44px;
  font-size:17px;
  padding: 9px 16px;
  border: 0;
  border-radius: 9px;
  background: var(--action-fill, var(--accent));
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
@media(prefers-reduced-motion:reduce){.spinner{animation:none}}
</style>
