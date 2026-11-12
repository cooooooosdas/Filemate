<template>
  <div class="logo-lockup">
    <img
      v-if="variant === 'navigation'"
      class="brand-lockup brand-lockup-navigation"
      :src="currentTheme.id === 'blue-gray' ? lightNavigation : darkNavigation"
      alt="FileMate，你的文件知识管理伙伴"
      width="936"
      height="220"
      decoding="async"
    />
    <img
      v-else
      class="brand-lockup"
      src="../assets/optimized/filemate-brand-lockup.svg"
      alt="FileMate，你的文件知识管理伙伴"
      width="432"
      height="122"
      decoding="async"
    />
  </div>
</template>

<script setup lang="ts">
import { currentTheme } from '../preferences/theme-runtime'
import lightNavigation from '../assets/optimized/filemate-brand-navigation-light.svg'
import darkNavigation from '../assets/optimized/filemate-brand-navigation.svg'

withDefaults(defineProps<{ variant?: 'default' | 'navigation' }>(), {
  variant: 'default',
})
</script>

<style scoped>
.logo-lockup {
  min-width: 0;
  display: flex;
  align-items: center;
  overflow: hidden;
}

.brand-lockup {
  width: 156px;
  height: auto;
  display: block;
  object-fit: contain;
  object-position: left center;
}

.brand-lockup-navigation {
  width: 168px;
  max-width: 100%;
}
</style>
