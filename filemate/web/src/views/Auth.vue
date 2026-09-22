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
          <p>{{ isRegister ? 'YOUR NEXT CHAPTER' : 'WELCOME TO FILEMATE' }}</p>
          <h2 id="auth-form-title">{{ isRegister ? '注册 FileMate' : '登录 FileMate' }}</h2>
          <span>{{ isRegister ? '让每一份努力，都有自己的归处。' : '留一点时间，给今天想学的东西。' }}</span>
        </header>
        <nav class="auth-switch" aria-label="账号操作">
          <router-link to="/login" :aria-current="!isRegister ? 'page' : undefined">登录</router-link>
          <router-link to="/register" :aria-current="isRegister ? 'page' : undefined">注册</router-link>
        </nav>
        <form novalidate @submit.prevent="handleSubmit">
          <div v-if="isRegister" class="field-group">
            <label for="display-name">姓名或昵称</label>
            <div class="field-control" :class="{ invalid: errors.displayName }"><el-icon><User /></el-icon><input id="display-name" v-model.trim="displayName" name="displayName" autocomplete="name" maxlength="30" placeholder="例如：林同学" :aria-invalid="Boolean(errors.displayName)" :aria-describedby="errors.displayName ? 'display-name-error' : undefined" /></div>
            <p v-if="errors.displayName" id="display-name-error" class="field-error" role="alert">{{ errors.displayName }}</p>
          </div>
          <div class="field-group">
            <label for="account">手机号或邮箱</label>
            <div class="field-control" :class="{ invalid: errors.account }"><el-icon><Message /></el-icon><input id="account" v-model.trim="account" name="account" autocomplete="username" inputmode="email" placeholder="请输入手机号或邮箱" :aria-invalid="Boolean(errors.account)" :aria-describedby="errors.account ? 'account-error' : undefined" /></div>
            <p v-if="errors.account" id="account-error" class="field-error" role="alert">{{ errors.account }}</p>
          </div>
          <div class="field-group">
            <div class="field-label-row"><label for="password">密码</label><button v-if="!isRegister" class="text-button" type="button" @click="showUnavailableNotice">忘记密码？</button></div>
            <div class="field-control" :class="{ invalid: errors.password }"><el-icon><Key /></el-icon><input id="password" v-model="password" name="password" :type="showPassword ? 'text' : 'password'" :autocomplete="isRegister ? 'new-password' : 'current-password'" :placeholder="isRegister ? '至少 8 位，包含字母和数字' : '请输入密码'" :aria-invalid="Boolean(errors.password)" :aria-describedby="errors.password ? 'password-error' : undefined" /><button class="reveal-button" type="button" :aria-label="showPassword ? '隐藏密码' : '显示密码'" @click="showPassword = !showPassword"><el-icon><View v-if="!showPassword" /><Hide v-else /></el-icon></button></div>
            <p v-if="errors.password" id="password-error" class="field-error" role="alert">{{ errors.password }}</p>
          </div>
          <div v-if="isRegister" class="field-group">
            <label for="confirm-password">确认密码</label>
            <div class="field-control" :class="{ invalid: errors.confirmPassword }"><el-icon><Key /></el-icon><input id="confirm-password" v-model="confirmPassword" name="confirmPassword" :type="showPassword ? 'text' : 'password'" autocomplete="new-password" placeholder="请再次输入密码" :aria-invalid="Boolean(errors.confirmPassword)" :aria-describedby="errors.confirmPassword ? 'confirm-password-error' : undefined" /></div>
            <p v-if="errors.confirmPassword" id="confirm-password-error" class="field-error" role="alert">{{ errors.confirmPassword }}</p>
          </div>
          <label v-if="isRegister" class="check-row" :class="{ invalid: errors.accepted }"><input v-model="accepted" type="checkbox" /><span>我已了解这是界面预览，不会创建真实账号</span></label>
          <label v-else class="check-row"><input v-model="rememberMe" type="checkbox" /><span>在这台设备上保持登录</span></label>
          <p v-if="errors.accepted" class="field-error agreement-error" role="alert">{{ errors.accepted }}</p>
          <button class="primary-action" type="submit" :aria-label="isRegister ? '创建账号' : '登录'">{{ isRegister ? '创建账号' : '登录' }}<el-icon><Right /></el-icon></button>
        </form>
        <div class="guest-divider"><span>暂时不使用账号</span></div>
        <router-link class="guest-action" to="/">以游客身份继续</router-link>
        <p class="auth-boundary"><el-icon><Lock /></el-icon>账号功能即将开放。当前为界面预览，可先以游客身份体验。</p>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { DocumentAdd, Hide, Key, Lock, Message, Notebook, Reading, Right, User, View } from '@element-plus/icons-vue'
import Logo from '../components/Logo.vue'

interface FormErrors { displayName?: string; account?: string; password?: string; confirmPassword?: string; accepted?: string }
const route = useRoute()
const isRegister = computed(() => route.name === 'Register')
const displayName = ref('')
const account = ref('')
const password = ref('')
const confirmPassword = ref('')
const accepted = ref(false)
const rememberMe = ref(true)
const showPassword = ref(false)
const errors = reactive<FormErrors>({})

function clearErrors(): void { Object.keys(errors).forEach(key => delete errors[key as keyof FormErrors]) }
watch(isRegister, () => { clearErrors(); password.value = ''; confirmPassword.value = ''; showPassword.value = false })

function validate(): boolean {
  clearErrors()
  const phonePattern = /^1\d{10}$/
  const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  if (isRegister.value && displayName.value.length < 2) errors.displayName = '请输入至少 2 个字的姓名或昵称'
  if (!phonePattern.test(account.value) && !emailPattern.test(account.value)) errors.account = '请输入有效的手机号或邮箱'
  if (!password.value) errors.password = '请输入密码'
  else if (isRegister.value && (password.value.length < 8 || !/[A-Za-z]/.test(password.value) || !/\d/.test(password.value))) errors.password = '密码至少 8 位，并同时包含字母和数字'
  if (isRegister.value && !confirmPassword.value) errors.confirmPassword = '请再次输入密码'
  else if (isRegister.value && confirmPassword.value !== password.value) errors.confirmPassword = '两次输入的密码不一致'
  if (isRegister.value && !accepted.value) errors.accepted = '请确认已了解当前为界面预览'
  return Object.keys(errors).length === 0
}

function handleSubmit(): void { if (validate()) ElMessage.info('账号服务尚未接入，本次未保存任何账号或密码') }
function showUnavailableNotice(): void { ElMessage.info('找回密码功能将在账号服务接入后开放') }
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
  background: #edf4ee;
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
.auth-switch a[aria-current=page] { color: var(--accent); border-color: var(--accent-border); background: white; font-weight: 600; }
.field-group { margin-bottom: 18px; }
.field-group > label,
.field-label-row label { color: var(--text-primary); font-size: 13px; font-weight: 500; }
.field-label-row { display: flex; justify-content: space-between; align-items: center; min-height: 30px; margin-top: -8px; }
.field-control { display: grid; grid-template-columns: 20px minmax(0, 1fr) auto; align-items: center; gap: 10px; margin-top: 9px; padding: 0 12px; min-height: 52px; border: 1px solid var(--border-strong); border-radius: var(--radius-control); background: white; transition: border-color var(--motion-fast); }
.field-control:focus-within { border-color: var(--accent); outline: 2px solid var(--accent-soft); outline-offset: 1px; }
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
</style>
