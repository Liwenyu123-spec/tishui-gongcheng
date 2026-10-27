<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login as loginApi } from '../api/auth'

const router = useRouter()
const route = useRoute()
const form = reactive({ account: '', password: '' })
const loading = ref(false)

const highlights = [
  { title: '运行可查', text: '泵站、流量、告警' },
  { title: '独立账号', text: '团队协作' },
  { title: '即问即答', text: '中文问答' },
]

const login = async () => {
  if (!form.account.trim() || !form.password) {
    ElMessage.warning('请输入账号和密码')
    return
  }
  loading.value = true
  try {
    const result = await loginApi(form.account.trim(), form.password)
    localStorage.setItem('access_token', result.access_token)
    localStorage.setItem('current_user', JSON.stringify(result.user))
    ElMessage.success('登录成功')
    const redirect = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/') && route.query.redirect !== '/login'
      ? route.query.redirect
      : '/dashboard'
    await router.push(redirect)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <section class="intro">
      <p class="kicker">WATER DISPATCH · OPERATIONS WORKSPACE</p>
      <h1>让每一次供水调度，<br>都有数据可循。</h1>
      <p class="lead">泵站、流量、告警分析，汇聚在一个调度工作空间。</p>
      <ul class="highlights">
        <li v-for="item in highlights" :key="item.title">
          <strong>{{ item.title }}</strong>
          <span>{{ item.text }}</span>
        </li>
      </ul>
    </section>
    <section class="login-side">
      <form class="login-card" @submit.prevent="login">
        <p class="welcome">WELCOME BACK</p>
        <h2>登录调度工作空间</h2>
        <p class="hint">使用账号与密码进入你的团队账号。</p>
        <label>
          账号
          <input v-model="form.account" autocomplete="username" placeholder="请输入账号" />
        </label>
        <label>
          密码
          <input v-model="form.password" type="password" autocomplete="current-password" placeholder="请输入密码" />
        </label>
        <button type="submit" :disabled="loading">{{ loading ? '正在登录' : '登录工作空间' }}</button>
        <p class="foot">演示环境请使用已有账号登录。</p>
      </form>
    </section>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(320px, 1fr) minmax(360px, 1fr);
  background:
    radial-gradient(ellipse at 18% 0%, rgba(122, 223, 242, .22), transparent 36%),
    linear-gradient(180deg, #0d4a62 0%, #083246 48%, #06202c 100%);
  color: #f4fcff;
}
.intro {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 72px 72px 64px;
  background: transparent;
  color: #f4fcff;
}
.kicker {
  margin: 0 0 36px;
  color: #9fd4e4;
  font-size: 12px;
  letter-spacing: .16em;
}
.intro h1 {
  margin: 0;
  max-width: 560px;
  font-size: 48px;
  font-weight: 650;
  line-height: 1.25;
  letter-spacing: .02em;
}
.lead {
  margin: 28px 0 0;
  max-width: 460px;
  color: #b7dbe6;
  font-size: 16px;
  line-height: 1.7;
}
.highlights {
  display: grid;
  grid-template-columns: repeat(3, max-content);
  gap: 48px;
  margin: 72px 0 0;
  padding: 0;
  list-style: none;
}
.highlights strong,
.highlights span {
  display: block;
}
.highlights strong {
  font-size: 16px;
  font-weight: 650;
}
.highlights span {
  margin-top: 8px;
  color: #8fbed0;
  font-size: 13px;
}
.login-side {
  display: grid;
  place-items: center;
  padding: 32px 24px;
  background: transparent;
}
.login-card {
  width: min(420px, 100%);
  display: grid;
  gap: 8px;
  padding: 36px 36px 28px;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 18px 50px rgba(6, 32, 44, .12);
}
.welcome {
  margin: 0;
  color: #5b879b;
  font-size: 12px;
  letter-spacing: .14em;
}
.login-card h2 {
  margin: 8px 0 0;
  color: #06384a;
  font-size: 28px;
  font-weight: 650;
}
.hint {
  margin: 8px 0 16px;
  color: #5b879b;
  font-size: 14px;
}
label {
  display: grid;
  gap: 8px;
  margin-top: 10px;
  color: #0a4c66;
  font-size: 14px;
}
input {
  height: 46px;
  padding: 0 14px;
  border: 0;
  border-radius: 8px;
  background: #e8f4f8;
  color: #06384a;
  font-size: 15px;
}
input:focus {
  outline: 2px solid rgba(20, 152, 184, .35);
}
input::placeholder { color: #7f9eac; }
button {
  height: 48px;
  margin-top: 18px;
  border: 0;
  border-radius: 8px;
  background: linear-gradient(180deg, #3ec4de, #128eac);
  color: #fff;
  cursor: pointer;
  font-size: 16px;
  box-shadow: 0 8px 18px rgba(18, 142, 172, .28);
}
button:hover { filter: brightness(1.05); }
button:disabled { opacity: .7; cursor: default; }
.foot {
  margin: 14px 0 0;
  color: #7f9aab;
  font-size: 12px;
  text-align: center;
}
@media (max-width: 900px) {
  .login-page { grid-template-columns: 1fr; }
  .intro { padding: 48px 28px 36px; }
  .intro h1 { font-size: 34px; }
  .highlights { gap: 24px; margin-top: 36px; }
}
</style>
