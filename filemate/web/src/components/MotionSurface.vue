<template>
  <component :is="as" ref="surface" class="motion-surface" @pointermove="moveLight">
    <slot />
  </component>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { waapi } from 'animejs/waapi'

withDefaults(defineProps<{ as?: string }>(), { as: 'section' })
const surface = ref<HTMLElement>()
let observer: IntersectionObserver | undefined
let animation: ReturnType<typeof waapi.animate> | undefined
let reduced: MediaQueryList | undefined
let pointer: MediaQueryList | undefined
function moveLight(event: PointerEvent): void {
  if (reduced?.matches || !pointer?.matches || event.pointerType === 'touch' || !surface.value) return
  const rect = surface.value.getBoundingClientRect()
  surface.value.style.setProperty('--light-x', `${event.clientX - rect.left}px`)
  surface.value.style.setProperty('--light-y', `${event.clientY - rect.top}px`)
}
function stopMotion(): void { if (reduced?.matches) animation?.revert() }
onMounted(() => {
  reduced = matchMedia('(prefers-reduced-motion: reduce)')
  pointer = matchMedia('(hover: hover) and (pointer: fine)')
  reduced.addEventListener('change', stopMotion)
  observer = new IntersectionObserver(entries => {
    if (!entries.some(entry => entry.isIntersecting) || !surface.value) return
    observer?.disconnect()
    if (!reduced?.matches) animation = waapi.animate(surface.value, { opacity:[.7,1], transform:['translateY(16px)','translateY(0px)'], duration:420, ease:'cubic-bezier(.22,1,.36,1)' })
  }, { threshold:.08 })
  if (surface.value) observer.observe(surface.value)
})
onUnmounted(() => { observer?.disconnect(); animation?.revert(); reduced?.removeEventListener('change', stopMotion) })
</script>

<style scoped>
.motion-surface { position:relative; isolation:isolate; }
.motion-surface::before { content:''; position:absolute; inset:0; z-index:-1; border-radius:inherit; pointer-events:none; background:radial-gradient(360px circle at var(--light-x,85%) var(--light-y,0%),#a3c5ff55,transparent 72%); opacity:0; transition:opacity var(--motion-fast); }
@media(hover:hover) and (pointer:fine) { .motion-surface:hover::before { opacity:1; } }
@media(prefers-reduced-motion:reduce) { .motion-surface::before { display:none; } }
</style>
