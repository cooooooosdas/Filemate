<template>
  <div class="logo-lockup">
    <img class="logo-mark" src="../assets/filemate-mark-64.png" alt="" aria-hidden="true" />
    <span class="logo-copy">
      <strong>FileMate</strong>
      <small>学习智能体</small>
    </span>
  </div>
</template>

<style scoped>
.logo-lockup {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 11px;
}

.logo-mark {
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  display: block;
  border-radius: 10px;
}

.logo-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.logo-copy strong {
  color: var(--text-primary);
  font-size: 17px;
  line-height: 1.1;
  letter-spacing: -0.02em;
}

.logo-copy small {
  color: var(--text-muted);
  font-size: 10px;
  letter-spacing: 0.14em;
}
</style>
