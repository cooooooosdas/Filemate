<template>
  <div class="editor-wrap">
    <div v-show="!failed" ref="host" class="editor-host" aria-label="C++ 编辑区" />
    <template v-if="failed">
      <p role="status">编辑器暂时无法加载，代码已保留，可继续使用文本编辑。</p>
      <textarea aria-label="C++代码" :value="modelValue" :readonly="disabled" spellcheck="false" @input="onFallback" />
    </template>
    <p v-if="loading" role="status" class="editor-loading">正在加载代码编辑器…</p>
  </div>
</template>
<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import type * as Monaco from 'monaco-editor'
const props = defineProps<{ modelValue: string; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const host = ref<HTMLDivElement | null>(null)
const failed = ref(false)
const loading = ref(true)
let editor: Monaco.editor.IStandaloneCodeEditor | undefined
let model: Monaco.editor.ITextModel | undefined
let subscription: Monaco.IDisposable | undefined
let disposed = false
onMounted(async () => {
  try {
    const [monaco, worker] = await Promise.all([
      import('monaco-editor/editor/editor.api.js'),
      import('monaco-editor/editor/editor.worker.js?worker'),
      import('monaco-editor/languages/definitions/cpp/register.js'),
    ])
    if (disposed || !host.value) return
    const scope = self as typeof self & { MonacoEnvironment?: Monaco.Environment }
    scope.MonacoEnvironment = { getWorker: () => new worker.default() }
    monaco.editor.defineTheme('filemate-light', {
      base: 'vs', inherit: true, rules: [], colors: { 'editor.background': '#fbfcf9', 'editor.lineHighlightBackground': '#f0f5ec' },
    })
    model = monaco.editor.createModel(props.modelValue, 'cpp')
    editor = monaco.editor.create(host.value, {
      model, theme: 'filemate-light', ariaLabel: 'C++代码', readOnly: props.disabled,
      automaticLayout: true, minimap: { enabled: false }, fontSize: 14,
      scrollBeyondLastLine: false, wordWrap: 'on', tabSize: 4,
      padding: { top: 16 }, accessibilitySupport: 'on',
    })
    subscription = editor!.onDidChangeModelContent(() => emit('update:modelValue', editor!.getValue()))
  } catch {
    if (!disposed) failed.value = true
  } finally {
    if (!disposed) loading.value = false
  }
})
watch(() => props.modelValue, value => { if (editor && editor.getValue() !== value) editor.setValue(value) })
watch(() => props.disabled, value => editor?.updateOptions({ readOnly: value }))
function onFallback(event: Event) { emit('update:modelValue', (event.target as HTMLTextAreaElement).value) }
onUnmounted(() => { disposed = true; subscription?.dispose(); editor?.dispose(); model?.dispose() })
</script>
<style scoped>
.editor-wrap{position:relative;border:1px solid #dce6d6;border-radius:12px;overflow:hidden;background:#fbfcf9}.editor-host{height:420px;min-width:0}.editor-loading{position:absolute;top:12px;left:60px;color:#718169;pointer-events:none}textarea{width:100%;height:420px;padding:16px;font:14px/1.6 Consolas,monospace;color:#263c27;background:#fbfcf9;border:0;resize:vertical}.editor-wrap>p{padding:8px 12px}@media(max-width:600px){.editor-host,textarea{height:340px}}
</style>
