<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login as loginApi } from '../api/auth'
const router = useRouter()
const form = reactive({ account: 'admin', password: 'admin123', role: '值班调度员' })
const loading = ref(false)
const login = async () => {
  if (!form.account || !form.password) {
    ElMessage.warning('请输入账号和密码')
    return
  }
  loading.value = true
  try {
    const result = await loginApi(form.account, form.password)
    localStorage.setItem('access_token', result.access_token)
    localStorage.setItem('current_user', JSON.stringify(result.user))
    ElMessage.success('登录成功')
    await router.push('/dashboard')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '登录失败')
  } finally {
    loading.value = false
  }
}
</script>
<template><div class="login-page"><div class="login-glow"></div><div class="login-card"><div class="brand"><div class="brand-mark">水</div><div><strong>提水工程</strong><span>供水调度平台</span></div></div><p class="eyebrow">WATER DISPATCH / SIGN IN</p><h1>进入调度工作台</h1><p class="muted">测试环境 · 后端 Mock 数据 · 只读分析模式</p><el-form :model="form" label-position="top" style="margin-top:28px"><el-form-item label="账号"><el-input v-model="form.account" placeholder="请输入账号"/></el-form-item><el-form-item label="密码"><el-input v-model="form.password" type="password" show-password placeholder="请输入密码"/></el-form-item><el-form-item label="角色"><el-select v-model="form.role" style="width:100%"><el-option label="值班调度员" value="值班调度员"/><el-option label="工程/设备" value="工程/设备"/><el-option label="审批负责人" value="审批负责人"/></el-select></el-form-item><el-button type="primary" :loading="loading" style="width:100%;height:42px;margin-top:8px" @click="login">登录测试环境</el-button></el-form><p class="login-note">当前登录已连接后端 Mock 认证接口。</p></div></div></template>
<style scoped>.login-page{min-height:100vh;display:grid;place-items:center;background:radial-gradient(circle at 50% 0%,#16445d 0,#07131f 52%);position:relative;overflow:hidden}.login-glow{position:absolute;width:650px;height:650px;border:1px solid rgba(91,224,202,.16);border-radius:50%;box-shadow:0 0 0 70px rgba(91,224,202,.03),0 0 0 140px rgba(91,224,202,.02)}.login-card{position:relative;width:410px;padding:38px 40px;border:1px solid #285064;border-radius:14px;background:rgba(7,24,37,.92);box-shadow:0 24px 70px rgba(0,0,0,.35)}.login-card h1{margin:8px 0 6px;color:#eefbff;font-size:25px}.login-note{text-align:center;color:#607e8c;font-size:11px;margin:22px 0 0}</style>
