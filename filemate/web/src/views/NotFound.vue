<template>
  <section class="not-found">
    <span aria-hidden="true" class="code">404</span>
    <h1>页面不存在</h1>
    <p>这个地址可能已变更。可以回到工作台，或继续今日安排。</p>
    <nav aria-label="离开不存在的页面"><RouterLink to="/">返回首页</RouterLink><RouterLink to="/today">打开今日行动</RouterLink></nav>
  </section>
</template>
<style scoped>
.not-found{max-width:720px;margin:48px auto;padding:48px 24px;text-align:center}.code{font-size:72px;font-weight:700;color:var(--accent)}h1{font-size:32px}p{font-size:18px;line-height:1.8;color:var(--text-secondary)}nav{display:flex;justify-content:center;flex-wrap:wrap;gap:16px;margin-top:28px}a{display:inline-flex;align-items:center;min-height:48px;padding:10px 20px;border:1px solid var(--accent);border-radius:10px;color:var(--accent);font-size:17px;text-decoration:none}a:first-child{background:var(--action-fill,var(--accent));color:#fff}
</style>
