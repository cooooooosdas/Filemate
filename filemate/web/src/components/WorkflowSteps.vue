<template>
  <nav class="workflow-steps" aria-label="资料处理步骤">
    <ol>
      <li
        v-for="(step, index) in steps"
        :key="step"
        :class="{ active: index + 1 === current, complete: index + 1 < current }"
        :aria-current="index + 1 === current ? 'step' : undefined"
      >
        <span>{{ index + 1 }}</span>
        <strong>{{ step }}</strong>
      </li>
    </ol>
  </nav>
</template>

<script setup lang="ts">
defineProps<{ current: 1 | 2 | 3 }>()

const steps = ['导入资料', '分类与命名', '查看日程']
</script>

<style scoped>
.workflow-steps {
  margin-bottom: 20px;
  padding: 14px 16px;
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-panel);
}

.workflow-steps ol {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0;
  margin: 0;
  padding: 0;
  list-style: none;
}

.workflow-steps li {
  position: relative;
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
  color: var(--text-muted);
  font-size: 16px;
}

.workflow-steps li:not(:last-child)::after {
  content: '';
  height: 1px;
  flex: 1;
  margin-right: 12px;
  background: var(--border-subtle);
}

.workflow-steps li > span {
  width: 34px;
  height: 34px;
  flex: 0 0 34px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  background: var(--bg-base);
  font-family: var(--font-mono);
  font-weight: 700;
}

.workflow-steps li > strong {
  white-space: nowrap;
}

.workflow-steps li.complete,
.workflow-steps li.active {
  color: var(--accent);
}

.workflow-steps li.complete > span {
  color: #ffffff;
  background: var(--accent);
  border-color: var(--accent);
}

.workflow-steps li.active > span {
  background: var(--accent-soft);
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

@media (max-width: 640px) {
  .workflow-steps ol {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
  }

  .workflow-steps li { flex-direction: column; text-align: center; font-size: 14px; }
  .workflow-steps li > strong { white-space: normal; }

  .workflow-steps li::after {
    display: none;
  }
}
</style>
