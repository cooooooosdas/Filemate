<template>
  <section v-if="account?.user || deleted" class="portfolio-page account-privacy-panel">
    <h2>注销账号</h2>
    <template v-if="!deleted">
      <p>注销会删除此账号的全部学习资料、代码、报告、服务内备份和登录会话。请先下载需要保留的个人数据。</p>
      <button type="button" :disabled="busy" @click="preview">预览账号注销</button>
      <form v-if="proposal" class="portfolio-panel" @submit.prevent="erase">
        <h3>核对删除范围</h3>
        <p>{{ proposal.counts.sources || 0 }}份资料 · {{ proposal.counts.quiz_attempts || 0 }}次课程作答 · {{ proposal.counts.coding_submissions || 0 }}次编程提交 · {{ proposal.counts.interview_sessions || 0 }}场面试 · {{ proposal.counts.files || 0 }}个托管文件</p>
        <p>{{ proposal.notice }}</p>
        <label>输入当前密码确认<input v-model="password" type="password" autocomplete="current-password" maxlength="128" required :disabled="busy"></label>
        <div class="actions"><button type="submit" :disabled="busy || !password">确认注销此账号</button><button type="button" :disabled="busy" @click="cancel">取消注销</button></div>
      </form>
    </template>
    <p v-if="busy" role="status">正在处理，请勿关闭页面…</p><p v-if="error" role="alert">{{ error }}</p><p v-if="message" role="status">{{ message }}</p>
    <a v-if="deleted" href="/login">返回登录页面</a>
  </section>
</template>
<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { deleteMyAccount, getAccountState, previewAccountDelete, type AccountDeletePreview } from '../services/api'
import type { AccountState } from '../types/account'
const account = ref<AccountState | null>(null), proposal = ref<AccountDeletePreview | null>(null), password = ref(''), busy = ref(false), error = ref(''), message = ref(''), deleted = ref(false)
onMounted(async () => { try { account.value = await getAccountState() } catch { error.value = '账号状态读取失败，请刷新重试' } })
onBeforeUnmount(() => { password.value = '' })
const cancel = () => { proposal.value = null; password.value = ''; error.value = '' }
async function perform(action: () => Promise<void>) { busy.value = true; error.value = ''; try { await action() } catch (e: any) { error.value = e.message || '注销未完成，请重新预览' } finally { busy.value = false; password.value = '' } }
const preview = () => perform(async () => { proposal.value = await previewAccountDelete() })
const erase = () => perform(async () => {
  if (!proposal.value) return
  try { await ElMessageBox.confirm('此账号及全部学习数据将永久删除，所有设备会退出登录。已下载备份和第三方模型留存仍需自行处理。', '最后确认账号注销', { confirmButtonText: '永久注销', cancelButtonText: '保留账号' }) } catch { return }
  const result = await deleteMyAccount(proposal.value, password.value)
  if (!result.deleted) throw new Error('服务未确认注销，请重新登录检查')
  deleted.value = true; proposal.value = null; window.speechSynthesis?.cancel()
  message.value = result.cleanup_pending ? '账号已注销，登录已撤销，但服务内资料副本仍待清理，请联系维护者。' : '账号与服务内学习资料已删除，所有登录已撤销。'
  if (result.browser_cleanup_pending) message.value += ' 此浏览器密钥清理失败，请手动清除该网站的浏览器数据。'
  window.dispatchEvent(new Event('filemate:session-expired'))
})
</script>
<style src="../styles/portfolio.css"></style>
<style scoped>.account-privacy-panel{padding:26px 0;font-size:17px}.account-privacy-panel h2{font-size:28px}.account-privacy-panel .portfolio-panel{margin-top:20px}</style>
