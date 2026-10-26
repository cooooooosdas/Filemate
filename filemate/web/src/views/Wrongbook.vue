<template><component :is="Workspace" /></template>
<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
const Workspace = defineAsyncComponent(import.meta.env.VITE_ENABLE_WRONGBOOK_V2 === 'true'
  ? () => import('../components/wrongbook/ReviewWorkspace.vue')
  : () => import('../components/wrongbook/LegacyWrongbook.vue'))
</script>
