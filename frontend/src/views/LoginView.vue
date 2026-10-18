<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login as loginApi } from '../api/auth'
const router = useRouter()
const route = useRoute()
// 登录身份只由账号和密码决定，避免在登录页展示其他角色并造成权限误解。
const form = reactive({ account: 'admin', password: 'admin123' })
const loading = ref(false)
const roleNames: Record<string, string> = { admin: '系统管理员', operator: '值班调度员', reviewer: '审批负责人', 'station-operator': '站点值班员（二泵站）' }
// 根据已输入的测试账号显示当前角色；未知账号交由后端登录接口校验。
const recognizedRole = computed(() => {
  const account = form.account.trim()
  if (account === 'admin') return roleNames.admin
  if (account === 'operator') return roleNames.operator
  if (account === 'station-operator') return roleNames['station-operator']
  if (account === 'reviewer') return roleNames.reviewer
  return '登录后由后端识别'
})
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
    // 路由守卫可能保存了用户原本要访问的页面，登录后优先返回该页面。
    const redirect = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/') ? route.query.redirect : '/dashboard'
    await router.push(redirect)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '登录失败')
  } finally {
    loading.value = false
  }
}
</script>
<template><div class="login-page"><div class="login-glow"></div><div class="login-card"><div class="brand"><div class="brand-mark">水</div><div><strong>提水工程</strong><span>供水调度平台</span></div></div><p class="eyebrow">WATER DISPATCH / SIGN IN</p><h1>进入调度工作台</h1><p class="muted">测试环境 · 后端 Mock 数据 · 只读分析模式</p><el-form :model="form" label-position="top" style="margin-top:28px"><el-form-item label="账号"><el-input v-model="form.account" placeholder="请输入账号"/></el-form-item><el-form-item label="密码"><el-input v-model="form.password" type="password" show-password placeholder="请输入密码"/></el-form-item><div class="recognized-role">当前账号角色：<strong>{{ recognizedRole }}</strong></div><el-button type="primary" :loading="loading" style="width:100%;height:42px;margin-top:18px" @click="login">登录测试环境</el-button></el-form><p class="login-note">角色由后端根据账号识别，登录页不会展示其他角色。</p></div></div></template>
<style scoped>.login-page{min-height:100vh;display:grid;place-items:center;background:radial-gradient(circle at 50% 0%,#16445d 0,#07131f 52%);position:relative;overflow:hidden}.login-glow{position:absolute;width:650px;height:650px;border:1px solid rgba(91,224,202,.16);border-radius:50%;box-shadow:0 0 0 70px rgba(91,224,202,.03),0 0 0 140px rgba(91,224,202,.02)}.login-card{position:relative;width:410px;padding:38px 40px;border:1px solid #285064;border-radius:14px;background:rgba(7,24,37,.92);box-shadow:0 24px 70px rgba(0,0,0,.35)}.login-card h1{margin:8px 0 6px;color:#eefbff;font-size:25px}.recognized-role{margin:4px 0 0;padding:10px 12px;border:1px solid #285064;border-radius:7px;color:#8da5b3;font-size:12px;background:rgba(18,49,65,.35)}.recognized-role strong{color:#74d8b5}.login-note{text-align:center;color:#607e8c;font-size:11px;margin:22px 0 0}</style>
