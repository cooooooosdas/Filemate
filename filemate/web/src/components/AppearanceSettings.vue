<template>
  <section class="appearance-settings" aria-labelledby="appearance-title">
    <h3 id="appearance-title">选择你喜欢的工作台</h3>
    <p>点选即可预览，关闭设置后保留。所有方案沿用原来的清晰字体。</p>
    <div class="theme-choices" role="group" aria-label="显示主题">
      <button v-for="theme in themes" :key="theme.id" type="button" class="theme-choice" :aria-pressed="themePreference === theme.id" @click="choose(theme.id)">
        <span class="theme-preview" aria-hidden="true" :style="{ background: theme.colors['bg-base'] }">
          <i :style="{ background: theme.colors['sidebar-surface'] }" />
          <span><b :style="{ background: theme.colors['hero-background'] }" /><em :style="{ background: theme.colors['bg-surface'], borderColor: theme.colors['border-subtle'] }" /></span>
        </span>
        <strong>{{ theme.name }}<span v-if="themePreference === theme.id" class="selected-mark">已选</span></strong>
        <small>{{ theme.description }}</small>
      </button>
    </div>
    <label class="system-theme"><input type="checkbox" :checked="themePreference === 'system'" @change="choose(($event.target as HTMLInputElement).checked ? 'system' : currentTheme.id)"><span><strong>跟随系统自动切换</strong><small>系统浅色时使用蓝灰工作台，深色时使用午夜深蓝。</small></span></label>
    <p class="appearance-status" role="status">{{ themePreference === 'system' ? '自动模式 · 当前为' : '当前主题：' }}{{ currentTheme.name }}{{ persistWarning }}</p>
  </section>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { themes, type ThemePreference } from '../preferences/themes'
import { currentTheme, themePreference, selectAppearance } from '../preferences/theme-runtime'
const persistWarning = ref('')
function choose(value: ThemePreference) { persistWarning.value = selectAppearance(value) ? '' : '；浏览器未允许记住，本次仍可使用。' }
</script>
<style scoped>
.appearance-settings h3{margin:0 0 10px;font-size:25px;color:var(--text-primary)}.appearance-settings p{font-size:17px;line-height:1.7;color:var(--text-secondary)}.theme-choices{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:24px 0}.theme-choice{padding:12px;text-align:left;border:1px solid var(--border-strong);border-radius:12px;background:var(--bg-surface);color:var(--text-primary);cursor:pointer}.theme-choice[aria-pressed=true]{outline:2px solid var(--accent);outline-offset:2px}.theme-preview{display:flex;gap:10px;height:90px;padding:10px;border-radius:7px}.theme-preview>i{width:24px;border-radius:3px}.theme-preview>span{display:grid;flex:1;gap:8px}.theme-preview b{border-radius:3px}.theme-preview em{border:1px solid;border-radius:3px}.theme-choice strong{display:flex;justify-content:space-between;align-items:center;gap:8px;margin:14px 0 6px;font-size:18px}.theme-choice small,.system-theme small{display:block;font-size:15px;line-height:1.6;color:var(--text-secondary)}.selected-mark{font-size:15px;color:var(--accent)}.system-theme{display:flex;align-items:center;gap:14px;min-height:64px;cursor:pointer}.system-theme input{width:22px;height:22px;accent-color:var(--action-fill)}.system-theme strong{font-size:18px}.appearance-status{padding-top:14px;border-top:1px solid var(--border-subtle)}@media(max-width:480px){.theme-choices{gap:12px}.theme-choice{padding:10px}.theme-choice strong{font-size:17px}.theme-preview{height:74px}}
</style>
