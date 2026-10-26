<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login as loginApi } from '../api/auth'

const router = useRouter()
const route = useRoute()
const form = reactive({ account: '', password: '' })
const loading = ref(false)

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
    <div class="login-glow"></div>
    <form class="login-card" @submit.prevent="login">
      <div class="brand">
        <div class="brand-mark">水</div>
        <div><strong>提水工程</strong><span>供水调度平台</span></div>
      </div>
      <p class="eyebrow">WATER DISPATCH / SIGN IN</p>
      <h1>进入调度工作台</h1>
      <p class="muted">测试环境 · 数据库测试数据 · 只读分析模式</p>
      <label>
        账号
        <input v-model="form.account" autocomplete="username" placeholder="请输入账号" />
      </label>
      <label>
        密码
        <input v-model="form.password" type="password" autocomplete="current-password" placeholder="请输入密码" />
      </label>
      <button type="submit" :disabled="loading">{{ loading ? '正在登录' : '登录' }}</button>
    </form>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(ellipse at 50% 18%, rgba(186, 236, 248, .28), transparent 34%),
    linear-gradient(180deg, #0e6e8c 0%, #0a4c66 28%, #073044 62%, #06202c 100%);
}
.login-glow {
  position: absolute;
  width: 680px;
  height: 680px;
  border: 1px solid rgba(214, 246, 255, .28);
  border-radius: 50%;
  box-shadow:
    0 0 0 54px rgba(186, 230, 242, .08),
    0 0 0 120px rgba(150, 214, 230, .06),
    0 0 0 190px rgba(120, 196, 214, .04);
}
.login-page::after {
  content: "";
  position: absolute;
  left: -10%;
  right: -10%;
  bottom: -40px;
  height: 180px;
  background:
    radial-gradient(120% 80px at 20% 0%, transparent 40%, rgba(255, 255, 255, .16) 41%, transparent 42%),
    radial-gradient(120% 90px at 70% 10%, transparent 42%, rgba(255, 255, 255, .12) 43%, transparent 44%);
  pointer-events: none;
}
.login-card {
  position: relative;
  z-index: 1;
  width: min(440px, calc(100vw - 32px));
  display: grid;
  gap: 14px;
  padding: 36px 40px 32px;
  border: 1px solid rgba(190, 236, 246, .28);
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(10, 48, 66, .9), rgba(6, 28, 40, .92));
  box-shadow: 0 24px 70px rgba(2, 16, 24, .4);
}
.login-card h1 { margin: 8px 0 0; color: #f4fcff; font-size: 28px; }
.muted { margin: 0; color: #b7d5e1; font-size: 13px; }
.eyebrow { margin: 18px 0 0; color: #9fd4e4; font-size: 12px; letter-spacing: .08em; }
label { display: grid; gap: 8px; margin-top: 6px; color: #d5ebf3; font-size: 14px; }
input {
  height: 44px;
  padding: 0 14px;
  border: 1px solid rgba(150, 210, 224, .35);
  border-radius: 8px;
  background: rgba(8, 36, 50, .85);
  color: #f4fcff;
  font-size: 15px;
}
input::placeholder { color: #7f9eac; }
button {
  height: 46px;
  margin-top: 10px;
  border: 0;
  border-radius: 8px;
  background: linear-gradient(180deg, #3ec4de, #128eac);
  color: white;
  cursor: pointer;
  font-size: 16px;
  box-shadow: 0 8px 18px rgba(18, 142, 172, .28);
}
button:disabled { opacity: .7; cursor: default; }
</style>
