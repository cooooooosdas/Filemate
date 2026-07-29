<!--
  Component: Logo
  Design: Modern monogram with glass effect
-->
<template>
  <div class="logo-container" @click="handleClick">
    <div class="logo-icon">
      <div class="logo-bg"></div>
      <svg viewBox="0 0 40 40" class="logo-svg">
        <defs>
          <linearGradient id="logoGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#10b981" />
            <stop offset="100%" stop-color="#34d399" />
          </linearGradient>
        </defs>
        <path
          d="M8 6h16l8 8v20a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z"
          fill="url(#logoGrad)"
        />
        <path
          d="M24 6v8h8"
          fill="#6ee7b7"
          opacity="0.6"
        />
        <text
          x="20"
          y="24"
          text-anchor="middle"
          fill="white"
          font-size="14"
          font-weight="700"
          font-family="system-ui"
        >F</text>
      </svg>
      <div class="logo-glow"></div>
    </div>
    <div class="logo-text-wrap">
      <span class="logo-main">FileMate</span>
      <span class="logo-sub">智能文件管理</span>
    </div>
  </div>
</template>

<script setup lang="ts">
const handleClick = () => {
  // Optional: trigger animation replay
}
</script>

<style scoped>
.logo-container {
  display: flex;
  align-items: center;
  gap: 14px;
  cursor: pointer;
  padding: 6px 8px;
  border-radius: var(--radius-md, 12px);
  transition: background var(--transition-fast, 0.15s);
}

.logo-container:hover {
  background: rgba(255, 255, 255, 0.03);
}

.logo-icon {
  position: relative;
  width: 40px;
  height: 40px;
  flex-shrink: 0;
}

.logo-bg {
  position: absolute;
  inset: 0;
  background: rgba(16, 185, 129, 0.1);
  border-radius: var(--radius-sm, 8px);
}

.logo-svg {
  width: 100%;
  height: 100%;
  position: relative;
  z-index: 1;
}

.logo-glow {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 48px;
  height: 48px;
  background: radial-gradient(circle, rgba(16, 185, 129, 0.25) 0%, transparent 70%);
  pointer-events: none;
  animation: glowPulse 3s ease-in-out infinite;
}

@keyframes glowPulse {
  0%, 100% { opacity: 0.4; transform: translate(-50%, -50%) scale(1); }
  50% { opacity: 0.7; transform: translate(-50%, -50%) scale(1.1); }
}

.logo-text-wrap {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}

.logo-main {
  font-size: 18px;
  font-weight: 700;
  background: linear-gradient(135deg, #f4f4f5 0%, #d4d4d8 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  letter-spacing: -0.02em;
}

.logo-sub {
  font-size: 10px;
  color: #71717a;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
</style>