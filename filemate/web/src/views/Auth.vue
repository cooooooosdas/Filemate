<template>
  <main class="auth-page">
    <section class="auth-story" aria-labelledby="auth-story-title">
      <router-link class="auth-brand" to="/" aria-label="返回 FileMate 学习工作台"><Logo /></router-link>
      <div class="story-copy">
        <p class="eyebrow">A SPACE TO LEARN & GROW</p>
        <h1 id="auth-story-title">学有所据，<br /><span>进步有迹。</span></h1>
        <p>把散落的课件、笔记和想法收在一起。<br />从读懂一份资料，到看见自己的成长。</p>
      </div>
      <div class="learning-trace" aria-label="FileMate 学习轨迹示例">
        <div class="trace-head"><span>从资料，到掌握</span><span class="trace-status">学习流程示意</span></div>
        <ol>
          <li><span class="trace-index">01</span><div><strong>收好每一份资料</strong><small>课件、笔记与作业，有序归档</small></div><el-icon><DocumentAdd /></el-icon></li>
          <li><span class="trace-index">02</span><div><strong>读懂，再变成自己的</strong><small>重点笔记、知识卡片，随时回看</small></div><el-icon><Notebook /></el-icon></li>
          <li class="trace-current"><span class="trace-index">03</span><div><strong>每次复习，都有方向</strong><small>练习与错题，串起学习的下一步</small></div><el-icon><Reading /></el-icon></li>
        </ol>
      </div>
      <p class="story-footnote"><el-icon><Lock /></el-icon>资料默认私有，未经确认不会对外共享</p>
    </section>

    <section class="auth-panel" aria-labelledby="auth-form-title">
      <div class="auth-card">
        <header class="auth-card-head">
          <p>YOUR SPACE TO LEARN</p>
          <h2 id="auth-form-title">{{ recoveryResult ? '保存你的恢复码' : isRecover ? '找回密码' : isRegister ? '注册 FileMate' : '登录 FileMate' }}</h2>
          <span>{{ recoveryResult ? '恢复码只显示这一次，请妥善保存。' : isRecover ? '使用注册时保存的恢复码，设置新密码。' : '把每一份努力，留在自己的学习空间。' }}</span>
        </header>
        <section v-if="recoveryResult" class="recovery-result" aria-label="恢复码保存">
          <p>{{ isRecover ? '密码已更新，所有设备已退出登录。旧恢复码已失效。' : '账号已创建，当前设备已登录。' }}</p>
          <label for="saved-recovery-code">{{ isRecover ? '新的恢复码' : '账号恢复码' }}</label>
          <textarea id="saved-recovery-code" :value="recoveryResult" readonly rows="2" spellcheck="false" />
          <div class="recovery-actions"><button type="button" class="guest-action" @click="copyRecovery">复制恢复码</button><button type="button" class="guest-action" @click="saveRecovery">下载保存</button></div>
          <p class="auth-boundary">拥有恢复码的人可以重设你的密码。请保存到私密位置，切勿分享。丢失密码和恢复码后，无法找回账号。</p>
          <label class="check-row"><input v-model="savedRecovery" type="checkbox" /><span>我已妥善保存恢复码</span></label>
          <button class="primary-action" type="button" :disabled="!savedRecovery" @click="finishRecovery">{{ isRecover ? '返回登录' : '进入学习空间' }}</button>
        </section>
        <template v-else>
          <nav class="auth-switch" aria-label="账号操作">
            <router-link to="/login" :aria-current="!isRegister && !isRecover ? 'page' : undefined">登录</router-link>
            <router-link to="/register" :aria-current="isRegister ? 'page' : undefined">注册</router-link>
          </nav>
          <p v-if="serviceUnavailable" class="auth-boundary" role="status">{{ serviceUnavailable }}</p>
          <form novalidate :aria-busy="submitting" @submit.prevent="handleSubmit">
            <fieldset :disabled="submitting" class="auth-fields">
              <div v-if="isRegister" class="field-group">
                <label for="display-name">姓名或昵称</label>
                <div class="field-control"><el-icon><User /></el-icon><input id="display-name" :aria-invalid="invalidField === 'display-name'" :aria-describedby="invalidField === 'display-name' ? 'auth-error' : undefined" v-model.trim="displayName" autocomplete="name" maxlength="30" placeholder="例如：林同学" /></div>
              </div>
              <div class="field-group">
                <label for="account">邮箱</label>
                <div class="field-control"><el-icon><Message /></el-icon><input id="account" :aria-invalid="invalidField === 'account'" :aria-describedby="invalidField === 'account' ? 'auth-error' : undefined" v-model.trim="account" type="email" autocomplete="username" maxlength="254" placeholder="请输入邮箱地址" /></div>
              </div>
              <div v-if="isRecover" class="field-group">
                <label for="recovery-code">恢复码</label>
                <div class="field-control"><el-icon><Key /></el-icon><input id="recovery-code" :aria-invalid="invalidField === 'recovery-code'" :aria-describedby="invalidField === 'recovery-code' ? 'auth-error' : undefined" v-model.trim="recoveryCode" autocomplete="off" maxlength="64" placeholder="粘贴已保存的恢复码" /></div>
              </div>
              <div class="field-group">
                <div class="field-label-row"><label for="password">{{ isRecover ? '新密码' : '密码' }}</label><router-link v-if="!isRegister && !isRecover" class="text-button" to="/recover">忘记密码？</router-link></div>
                <div class="field-control"><el-icon><Key /></el-icon><input id="password" :aria-invalid="invalidField === 'password'" :aria-describedby="invalidField === 'password' ? 'auth-error' : undefined" v-model="password" :type="showPassword ? 'text' : 'password'" :autocomplete="isRegister || isRecover ? 'new-password' : 'current-password'" maxlength="128" :placeholder="isRegister || isRecover ? '15–128 个字符，支持中文长口令' : '请输入密码'" /><button type="button" class="reveal-button" :aria-label="showPassword ? '隐藏密码' : '显示密码'" @click="showPassword = !showPassword"><el-icon><View v-if="!showPassword" /><Hide v-else /></el-icon></button></div>
              </div>
              <div v-if="isRegister || isRecover" class="field-group">
                <label for="confirm-password">确认密码</label>
                <div class="field-control"><el-icon><Key /></el-icon><input id="confirm-password" :aria-invalid="invalidField === 'confirm-password'" :aria-describedby="invalidField === 'confirm-password' ? 'auth-error' : undefined" v-model="confirmPassword" :type="showPassword ? 'text' : 'password'" autocomplete="new-password" maxlength="128" placeholder="请再次输入密码" /></div>
              </div>
              <template v-if="isRegister">
                <label class="check-row"><input v-model="keepGuestData" type="checkbox" /><span>把当前游客资料保留到新账号</span></label>
                <label class="check-row"><input id="agreement" :aria-invalid="invalidField === 'agreement'" :aria-describedby="invalidField === 'agreement' ? 'auth-error' : undefined" v-model="accepted" type="checkbox" /><span>我会保存恢复码，并了解邮箱暂不验证归属</span></label>
              </template>
              <label v-if="!isRecover" class="check-row"><input v-model="rememberMe" type="checkbox" /><span>在这台设备上保持登录 30 天</span></label>
              <p v-if="error" id="auth-error" class="field-error" role="alert" tabindex="-1" ref="errorElement">{{ error }}</p>
              <button class="primary-action" type="submit" :disabled="Boolean(serviceUnavailable)">{{ submitting ? '正在处理…' : isRecover ? '重设密码' : isRegister ? '创建账号' : '登录' }}<el-icon><Right /></el-icon></button>
            </fieldset>
          </form>
          <div class="guest-divider"><span>先开始学习</span></div>
          <button class="guest-action" type="button" :disabled="submitting" @click="continueGuest">以游客身份继续</button>
          <p class="auth-boundary"><el-icon><Lock /></el-icon>邮箱用于登录识别，密码和恢复码不会明文保存。找回密码无需邮件服务。</p>
        </template>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { DocumentAdd, Hide, Key, Lock, Message, Notebook, Reading, Right, User, View } from '../icons'
import Logo from '../components/Logo.vue'
import { getAccountState, loginAccount, logoutAccount, recoverAccount, registerAccount } from '../services/api'

const route = useRoute()
const isRegister = computed(() => route.name === 'Register')
const isRecover = computed(() => route.name === 'Recover')
const displayName = ref(''), account = ref(''), password = ref(''), confirmPassword = ref(''), recoveryCode = ref('')
const accepted = ref(false), rememberMe = ref(true), keepGuestData = ref(true), showPassword = ref(false)
const submitting = ref(false), recoveryResult = ref(''), savedRecovery = ref(false), error = ref(''), serviceUnavailable = ref('')
const errorElement = ref<HTMLElement | null>(null)
const invalidField = ref('')
let accountEnabled = false
let mustLogout = false
watch(() => route.name, () => { password.value = ''; confirmPassword.value = ''; recoveryCode.value = ''; error.value = ''; invalidField.value = ''; showPassword.value = false })
onMounted(async () => {
  try {
    const state = await getAccountState()
    accountEnabled = state.enabled
    mustLogout = Boolean(state.user || state.expired)
    if (!accountEnabled) serviceUnavailable.value = '当前是本地独立模式，无需账号，可直接进入学习空间。'
  } catch { serviceUnavailable.value = '账号服务暂时未连接，请刷新后重试。' }
})

async function showError(message: string, field = ''): Promise<void> {
  error.value = message
  invalidField.value = field
  await nextTick()
  if (field) document.getElementById(field)?.focus()
  else errorElement.value?.focus()
}
async function handleSubmit(): Promise<void> {
  if (submitting.value) return
  error.value = ''; invalidField.value = ''
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(account.value)) return showError('请输入有效的邮箱地址', 'account')
  if (!password.value) return showError('请输入密码', 'password')
  if (isRegister.value || isRecover.value) {
    if ([...password.value].length < 15 || [...password.value].length > 128) return showError('密码需为 15–128 个字符，可使用中文长口令', 'password')
    if (password.value !== confirmPassword.value) return showError('两次输入的密码不一致', 'confirm-password')
  }
  if (isRegister.value && displayName.value.length < 2) return showError('请输入至少 2 个字的昵称', 'display-name')
  if (isRegister.value && !accepted.value) return showError('请确认会保存恢复码', 'agreement')
  if (isRecover.value && !recoveryCode.value) return showError('请输入注册时保存的恢复码', 'recovery-code')
  submitting.value = true
  try {
    if (isRegister.value) {
      const result = await registerAccount({ email: account.value, display_name: displayName.value, password: password.value, keep_guest_data: keepGuestData.value, remember: rememberMe.value })
      recoveryResult.value = result.recovery_code
    } else if (isRecover.value) {
      recoveryResult.value = await recoverAccount(account.value, recoveryCode.value, password.value)
    } else {
      await loginAccount(account.value, password.value, rememberMe.value)
      window.location.assign('/')
    }
    password.value = ''; confirmPassword.value = ''; recoveryCode.value = ''
  } catch (cause) { await showError(cause instanceof Error ? cause.message : '操作失败，请重试') }
  finally { submitting.value = false }
}
async function continueGuest(): Promise<void> {
  if (submitting.value) return
  submitting.value = true
  try {
    if (accountEnabled && mustLogout) await logoutAccount()
    window.location.assign('/')
  } catch (cause) { await showError(cause instanceof Error ? cause.message : '退出失败，请重试') }
  finally { submitting.value = false }
}
async function copyRecovery(): Promise<void> {
  try { await navigator.clipboard.writeText(recoveryResult.value); ElMessage.success('恢复码已复制，请保存到私密位置') }
  catch { ElMessage.info('请选中恢复码复制，或下载保存') }
}
function saveRecovery(): void {
  const url = URL.createObjectURL(new Blob([`FileMate 账号：${account.value}\n恢复码：${recoveryResult.value}\n请保密；重设密码后此恢复码失效。\n`], { type: 'text/plain;charset=utf-8' }))
  const link = document.createElement('a'); link.href = url; link.download = 'FileMate-恢复码.txt'; link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
function finishRecovery(): void {
  if (!savedRecovery.value) return
  recoveryResult.value = ''
  window.location.assign(isRecover.value ? '/login' : '/')
}
function guardRecovery(): boolean { return !recoveryResult.value || savedRecovery.value }
onBeforeRouteLeave(guardRecovery)
onBeforeRouteUpdate(guardRecovery)
function beforeUnload(event: BeforeUnloadEvent): void {
  if (!guardRecovery()) { event.preventDefault(); event.returnValue = '' }
}
window.addEventListener('beforeunload', beforeUnload)
onUnmounted(() => { window.removeEventListener('beforeunload', beforeUnload); recoveryResult.value = ''; password.value = '' })
</script>

<style scoped>
.auth-page {
  min-height: 100dvh;
  display: grid;
  grid-template-columns: minmax(0, 7fr) minmax(440px, 5fr);
  color: var(--text-primary);
  background: var(--bg-surface);
}
.auth-story {
  min-height: 100dvh;
  padding: 40px clamp(32px, 6vw, 88px);
  display: flex;
  flex-direction: column;
  background: radial-gradient(ellipse at 10% 100%, #91bbf788, transparent 65%), var(--panel-tint);
  border-right: 1px solid var(--border-subtle);
}
.auth-brand { display: block; width: fit-content; }
.story-copy { margin: clamp(48px, 8vh, 88px) 0 36px; }
.eyebrow,
.auth-card-head > p {
  margin: 0 0 20px;
  color: var(--accent);
  font: 11px var(--font-mono);
  letter-spacing: .12em;
  line-height: 1.6;
}
.story-copy h1 {
  margin: 0;
  font-size: clamp(48px, 5vw, 72px);
  font-weight: 600;
  letter-spacing: -.045em;
  line-height: 1.2;
}
.story-copy h1 span { color: var(--accent); }
.story-copy > p:last-child {
  margin: 24px 0 0;
  color: var(--text-secondary);
  font-size: 15px;
  line-height: 1.9;
}
.learning-trace {
  width: min(490px, 100%);
  margin-top: auto;
  overflow: hidden;
  background: var(--bg-surface);
  border: 1px solid var(--accent-border);
  border-radius: var(--radius-panel);
}
.trace-head {
  padding: 16px 20px;
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 600;
}
.trace-status { color: var(--text-muted); font-size: 11px; font-weight: 400; }
.learning-trace ol { margin: 0; padding: 0 20px; list-style: none; }
.learning-trace li {
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr) 32px;
  align-items: center;
  gap: 12px;
  min-height: 76px;
  padding: 14px 0;
  border-bottom: 1px solid var(--border-subtle);
}
.learning-trace li:last-child { border-bottom: 0; }
.trace-index { font: 11px var(--font-mono); color: var(--text-muted); }
.learning-trace li div { display: grid; gap: 6px; }
.learning-trace strong { font-size: 13px; font-weight: 600; line-height: 1.5; }
.learning-trace small { font-size: 11px; color: var(--text-secondary); line-height: 1.6; }
.learning-trace li > .el-icon { width: 32px; height: 36px; background: var(--accent-soft); border-radius: 6px; font-size: 18px; color: var(--accent); }
.trace-current .trace-index { color: var(--accent); }
.story-footnote { display: flex; align-items: center; gap: 8px; margin: 18px 0 0; font-size: 11px; line-height: 1.8; color: var(--text-secondary); }
.auth-panel { display: grid; place-items: center; padding: 48px clamp(32px, 4.5vw, 72px); }
.auth-card { width: min(400px, 100%); min-width: 0; }
.auth-card-head > p { margin-bottom: 14px; }
.auth-card-head h2 { margin: 0; font-size: 32px; font-weight: 600; letter-spacing: -.035em; }
.auth-card-head > span { display: block; margin-top: 12px; color: var(--text-secondary); font-size: 13px; line-height: 1.8; }
.auth-switch { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; padding: 4px; margin: 28px 0; background: var(--bg-base); border: 1px solid var(--border-subtle); border-radius: var(--radius-control); }
.auth-switch a { display: grid; place-items: center; min-height: 44px; color: var(--text-secondary); border: 1px solid transparent; border-radius: 7px; font-size: 14px; font-weight: 500; text-decoration: none; }
.auth-switch a:hover { color: var(--accent); }
.auth-switch a[aria-current=page] { color: var(--accent); border-color: var(--accent-border); background: var(--bg-reading); font-weight: 600; }
.field-group { margin-bottom: 18px; }
.field-group > label,
.field-label-row label { color: var(--text-primary); font-size: 13px; font-weight: 500; }
.field-label-row { display: flex; justify-content: space-between; align-items: center; min-height: 30px; margin-top: -8px; }
.field-control { display: grid; grid-template-columns: 20px minmax(0, 1fr) auto; align-items: center; gap: 10px; margin-top: 9px; padding: 0 12px; min-height: 52px; border: 1px solid var(--border-strong); border-radius: var(--radius-control); background: white; transition: border-color var(--motion-fast); }
.field-control:focus-within { border-color: var(--accent); outline: 2px solid var(--accent); outline-offset: 2px; }
.field-control.invalid { border-color: var(--danger); }
.field-control > .el-icon { color: var(--text-muted); font-size: 18px; }
.field-control input { width: 100%; min-width: 0; height: 50px; padding: 0; border: 0; outline: 0; color: var(--text-primary); background: transparent; font-size: 14px; }
.field-control input::placeholder { color: var(--text-muted); font-size: 13px; }
.field-error { margin: 7px 0 0; color: var(--danger); font-size: 12px; line-height: 1.6; }
.agreement-error { margin: -6px 0 12px; }
.reveal-button,
.text-button { display: inline-grid; place-items: center; min-height: 44px; border: 0; background: transparent; color: var(--text-secondary); }
.reveal-button { width: 44px; margin-right: -8px; font-size: 18px; }
.text-button { padding: 0; font-size: 12px; }
.text-button:hover,
.reveal-button:hover { color: var(--accent); }
.check-row { min-height: 44px; margin: -4px 0 12px; display: flex; align-items: center; gap: 10px; color: var(--text-secondary); font-size: 12px; line-height: 1.7; cursor: pointer; }
.check-row input { width: 16px; height: 16px; flex-shrink: 0; margin: 0; accent-color: var(--accent); }
.check-row.invalid { color: var(--danger); }
.primary-action,
.guest-action { display: flex; align-items: center; justify-content: center; gap: 12px; width: 100%; min-height: 50px; border-radius: var(--radius-control); font-size: 14px; font-weight: 600; text-decoration: none; transition: background var(--motion-fast), border-color var(--motion-fast); }
.primary-action { color: white; background: var(--accent); border: 1px solid var(--accent); }
.primary-action:hover { background: var(--accent-hover); border-color: var(--accent-hover); }
.guest-divider { display: flex; align-items: center; gap: 16px; margin: 22px 0 16px; color: var(--text-muted); font-size: 11px; }
.guest-divider::before,
.guest-divider::after { content: ''; flex: 1; height: 1px; background: var(--border-subtle); }
.guest-action { border: 1px solid var(--border-strong); color: var(--text-primary); background: white; }
.guest-action:hover { background: var(--accent-soft); border-color: var(--accent-border); color: var(--accent); }
.auth-boundary { display: flex; align-items: flex-start; gap: 8px; margin: 20px 0 0; padding: 12px; border-radius: var(--radius-control); background: var(--bg-base); color: var(--text-secondary); font-size: 11px; line-height: 1.8; }
.auth-boundary .el-icon { flex-shrink: 0; margin-top: 3px; font-size: 14px; }
@media (max-width: 1000px) {
  .auth-page { grid-template-columns: minmax(0, 1fr) minmax(400px, 1fr); }
  .auth-story { padding-inline: 32px; }
  .story-copy h1 { font-size: 52px; }
  .auth-panel { padding-inline: 32px; }
}
@media (max-width: 760px) {
  .auth-page { display: block; }
  .auth-story { min-height: auto; padding: 24px; border-right: 0; border-bottom: 1px solid var(--border-subtle); }
  .story-copy { margin: 28px 0 0; }
  .story-copy .eyebrow,
  .story-footnote,
  .learning-trace { display: none; }
  .story-copy h1 { font-size: clamp(30px, 7.5vw, 42px); line-height: 1.4; letter-spacing: -.04em; }
  .story-copy h1 br { display: none; }
  .story-copy > p:last-child { margin-top: 10px; font-size: 12px; }
  .story-copy > p:last-child br { display: none; }
  .auth-panel { padding: 32px 24px 48px; }
  .auth-card-head h2 { font-size: 28px; }
  .auth-card-head > p { font-size: 10px; }
}
@media (max-width: 380px) {
  .auth-story { padding: 20px; }
  .auth-panel { padding-inline: 20px; }
}
.auth-card-head > span, .field-group > label, .field-label-row label, .check-row { font-size:16px; }
.field-control input, .auth-switch a, .primary-action, .guest-action { font-size:17px; }
.field-control input::placeholder, .text-button, .auth-boundary { font-size:14px; }
.auth-fields { border:0; padding:0; margin:0; min-width:0; }
.primary-action:disabled, .guest-action:disabled { opacity:.6; cursor:wait; }
.recovery-result { margin-top:28px; font-size:16px; line-height:1.8; }
.recovery-result textarea { width:100%; box-sizing:border-box; margin:12px 0; padding:14px; border:1px solid var(--accent-border); border-radius:10px; font:16px var(--font-mono); background:var(--panel-tint); color:var(--text-primary); resize:none; }
.recovery-actions { display:flex; gap:12px; margin-bottom:16px; }
.text-button { text-decoration:none; }
</style>
