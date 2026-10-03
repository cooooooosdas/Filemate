<template>
  <section v-if="pageLoadFailure" class="page-load-error" role="alert" aria-label="页面加载失败">
    <div>
      <strong>目标页面暂时无法打开</strong>
      <p>请检查网络后重新打开。已保存资料仍在，未保存的输入会随重新打开而清除。</p>
    </div>
    <button type="button" @click="reopen">重新打开页面</button>
    <a href="/">返回工作台</a>
  </section>
</template>

<script setup lang="ts">
import { pageLoadFailure } from '../router/load-errors'

function reopen() {
  if (pageLoadFailure.value) window.location.assign(pageLoadFailure.value.path)
}
</script>

<style scoped>
.page-load-error{display:flex;gap:16px;align-items:center;flex-wrap:wrap;padding:16px 24px;border-bottom:1px solid #e7d1ae;background:#fff8ea;color:#614418}
.page-load-error div{flex:1;min-width:200px}.page-load-error p{margin:6px 0 0;font-size:13px;line-height:1.6}
.page-load-error button,.page-load-error a{min-height:44px;padding:10px 14px;border:1px solid #9a651d;border-radius:10px;color:#614418;background:transparent;text-decoration:none;font:inherit;cursor:pointer}
.page-load-error button:focus-visible,.page-load-error a:focus-visible{outline:2px solid #2f7d55;outline-offset:3px}
</style>
