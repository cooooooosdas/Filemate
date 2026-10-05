<template>
  <section class="portfolio-page personal-data-panel">
    <header><div><p class="eyebrow">资料由你掌握</p><h2>导出与恢复个人数据</h2><p>整包备份包含此学习空间的业务记录、托管上传与归档文件；密码、登录会话和 API 密钥不在其中。</p></div></header>
    <p>备份可恢复到同一学习空间；JSON 适合自行查阅，不能导入以免伪造判题或学习证据。浏览器密钥仍由此浏览器单独保存。外部文件夹中的原文件不由自助备份复制或恢复。</p>
    <div class="actions"><button type="button" class="primary" :disabled="busy" @click="download('backup')">下载整包备份</button><button type="button" :disabled="busy" @click="download('json')">导出个人数据 JSON</button></div>
    <p class="notice">自助容量：压缩包25MB、展开内容128MB、业务数据32MB、托管文件最多5000个。超过限制会明确失败，可使用管理员离线备份。备份包含私人资料，请保存到自己的安全位置。</p>
    <form class="portfolio-panel" @submit.prevent="preview"><h3>恢复备份</h3><label>选择 FileMate 整包备份<input ref="fileInput" type="file" accept=".zip,application/zip" :disabled="busy" @change="selectFile"></label><button type="submit" :disabled="busy || !file">校验并预览备份</button><p>先校验归属与完整性，再确认替换。恢复时请结束任务，并关闭其他操作窗口。</p></form>
    <section v-if="proposal" class="portfolio-panel restore-preview"><h3>恢复预览</h3><p>备份时间：{{ proposal.backup_created_at }}</p><div class="restore-counts"><div><strong>当前空间</strong><p>{{ proposal.current_counts.sources || 0 }}份资料 · {{ proposal.current_counts.quiz_attempts || 0 }}次课程作答 · {{ proposal.current_counts.coding_submissions || 0 }}次编程提交 · {{ proposal.current_counts.interview_sessions || 0 }}场面试 · {{ proposal.current_file_count }}个托管文件</p></div><div><strong>将恢复为</strong><p>{{ proposal.restored_counts.sources || 0 }}份资料 · {{ proposal.restored_counts.quiz_attempts || 0 }}次课程作答 · {{ proposal.restored_counts.coding_submissions || 0 }}次编程提交 · {{ proposal.restored_counts.interview_sessions || 0 }}场面试 · {{ proposal.file_count }}个托管文件</p></div></div><p>{{ proposal.notice }}</p><div class="actions"><button type="button" :disabled="busy" @click="restore">确认恢复这份备份</button><button type="button" :disabled="busy" @click="cancel">取消恢复并清理副本</button></div></section>
    <p v-if="busy" role="status">正在处理个人数据，请稍候…</p><p v-if="error" role="alert">{{ error }}</p><p v-if="message" role="status">{{ message }}</p>
  </section>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { cancelPersonalRestore, exportPersonalData, previewPersonalRestore, restorePersonalData, type PersonalRestorePreview } from '../services/api'
const emit = defineEmits<{ restored: [] }>()
const file = ref<File | null>(null), fileInput = ref<HTMLInputElement | null>(null), busy = ref(false), error = ref(''), message = ref(''), proposal = ref<PersonalRestorePreview | null>(null)
function selectFile(event: Event) { file.value = (event.target as HTMLInputElement).files?.[0] || null; proposal.value = null; error.value = ''; message.value = '' }
async function perform(action: () => Promise<void>) { busy.value = true; error.value = ''; message.value = ''; try { await action() } catch (e: any) { error.value = e.message || '操作未完成，原数据保留' } finally { busy.value = false } }
const download = (format: 'backup' | 'json') => perform(async () => { const blob = await exportPersonalData(format); const url = URL.createObjectURL(blob as unknown as Blob); const link = document.createElement('a'); link.href = url; link.download = `filemate-personal.${format === 'backup' ? 'zip' : 'json'}`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); message.value = '个人数据已导出' })
const preview = () => perform(async () => { if (!file.value) return; if (file.value.size > 25 * 1024 * 1024) throw new Error('备份文件不能超过25MB'); proposal.value = await previewPersonalRestore(file.value) })
const cancel = () => perform(async () => { if (!proposal.value) return; const result = await cancelPersonalRestore(proposal.value); proposal.value = null; message.value = result.cleanup_pending ? '恢复已取消，服务内副本仍待清理。' : '恢复已取消，预览副本已清理。' })
const restore = () => perform(async () => { if (!proposal.value) return; try { await ElMessageBox.confirm('将整体替换当前学习记录及托管文件。请确认已下载需要保留的当前数据。恢复不会重放旧文件操作，也不会恢复密码或API密钥。', '确认恢复个人备份', { confirmButtonText: '确认整体恢复', cancelButtonText: '取消' }) } catch { return }; const result = await restorePersonalData(proposal.value); if (!result.restored) throw new Error('服务未确认恢复完成，请检查原数据'); proposal.value = null; file.value = null; if (fileInput.value) fileInput.value.value = ''; window.speechSynthesis?.cancel(); message.value = result.cleanup_pending ? '业务数据已恢复，但临时副本清理未完成，请联系维护者处理。' : '个人数据与托管文件已恢复'; ElMessage.success(message.value); emit('restored') })
</script>
<style src="../styles/portfolio.css"></style>
<style scoped>.personal-data-panel{padding:26px 0;font-size:17px}.personal-data-panel h2{font-size:28px}.personal-data-panel .portfolio-panel{margin-top:20px}.restore-counts{display:grid;grid-template-columns:1fr 1fr;gap:20px}.restore-counts strong{font-size:22px}@media(max-width:480px){.restore-counts{grid-template-columns:1fr}}</style>
