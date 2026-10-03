<template>
  <div ref="root" class="knowledge-scene" :data-motion-state="motionState" aria-hidden="true">
    <div class="knowledge-lens" />
    <svg class="knowledge-lines" viewBox="0 0 1400 800" preserveAspectRatio="xMidYMid slice">
      <g class="knowledge-stream"><path v-for="(path, index) in paths" :key="index" :d="path" /></g>
    </svg>
    <div class="knowledge-folio"><span>资料</span><strong>理解</strong><span>练习</span></div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { waapi } from 'animejs/waapi'

const root = ref<HTMLElement | null>(null)
const motionState = ref('paused')
const paths = Array.from({ length: 24 }, (_, i) =>
  `M ${700 + i * 16} -120 C ${300 + i * 17} 120, ${1380 + i * 11} 160, ${790 + i * 12} 520 S ${250 + i * 12} 530, ${460 + i * 10} 780`)
let ambient: ReturnType<typeof waapi.animate> | undefined
const animations: ReturnType<typeof waapi.animate>[] = []
let motionPreference: MediaQueryList | undefined
let observer: IntersectionObserver | undefined
let visible = false
function updateMotion(): void {
  const reduced = motionPreference?.matches
  if (reduced) { motionState.value = 'reduced'; return }
  const running = visible && document.visibilityState === 'visible'
  if (running) ambient?.resume()
  else ambient?.pause()
  motionState.value = running ? 'running' : 'paused'
}
function rebuildMotion(): void {
  animations.splice(0).forEach(animation => animation.revert())
  ambient = undefined
  if (!root.value || motionPreference?.matches) { motionState.value = 'reduced'; return }
  animations.push(waapi.animate(root.value.querySelectorAll('.knowledge-folio'), {
    transform: ['translateY(22px)', 'translateY(0px)'], opacity: [0, 1],
    duration: 850, ease: 'cubic-bezier(.22,1,.36,1)',
  }))
  ambient = waapi.animate(root.value.querySelectorAll('.knowledge-stream'), {
    transform: ['translate(-14px, -8px)', 'translate(14px, 8px)'], duration: 16000,
    alternate: true, loop: true, autoplay: false, ease: 'cubic-bezier(.45,0,.55,1)',
  })
  animations.push(ambient)
  updateMotion()
}
onMounted(() => {
  if (!root.value) return
  motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)')
  motionPreference.addEventListener('change', rebuildMotion)
  rebuildMotion()
  observer = new IntersectionObserver(entries => { visible = entries[0]?.isIntersecting ?? false; updateMotion() })
  observer.observe(root.value)
  document.addEventListener('visibilitychange', updateMotion)
})
onUnmounted(() => {
  observer?.disconnect()
  document.removeEventListener('visibilitychange', updateMotion)
  motionPreference?.removeEventListener('change', rebuildMotion)
  animations.splice(0).forEach(animation => animation.revert())
  ambient = undefined
})
</script>

<style scoped>
.knowledge-scene { position:absolute; inset:0; width:100%; height:100%; pointer-events:none; z-index:-1; overflow:hidden; }
.knowledge-scene::after { content:''; position:absolute; inset:0; background:linear-gradient(90deg,#15285be8,transparent 82%); }
.knowledge-lines { position:absolute; inset:0; width:100%; height:100%; }
.knowledge-stream { fill:none; stroke:#9bc3ff; stroke-width:1.5; opacity:.58; }
.knowledge-lens { position:absolute; width:520px; height:520px; right:-5%; top:-60px; border-radius:50%; background:radial-gradient(circle at 25% 20%,#99bfff66,transparent 65%); box-shadow:inset 0 0 60px #85b4ff55,0 0 90px #5899ef33; }
.knowledge-folio { position:absolute; right:9%; bottom:48px; width:200px; height:180px; display:grid; place-content:center; gap:8px; text-align:center; rotate:-12deg; border:1px solid #a7cfff88; border-radius:24px; background:linear-gradient(140deg,#b9d7ff33,#82aaff08); color:#e8f2ff; box-shadow:0 20px 60px #06164622; }
.knowledge-folio strong { font-size:36px; font-weight:650; }.knowledge-folio span { font-size:21px; }
@media(max-width:1150px) { .knowledge-folio { width:160px; height:160px; right:6%; bottom:35px; }.knowledge-folio strong { font-size:30px; }.knowledge-lens { right:-160px; } }
@media(max-width:700px) { .knowledge-folio { width:140px; height:120px; right:15%; bottom:24px; }.knowledge-folio strong { font-size:28px; }.knowledge-folio span { font-size:17px; }.knowledge-lens { width:420px; height:420px; top:180px; right:-180px; }.knowledge-scene::after { background:linear-gradient(160deg,#15285bdc,transparent 95%); } }
</style>
