<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Menu as MenuIcon, Bell, UserFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { currentUser as currentUserApi, logout as logoutApi } from './api/auth'

const route = useRoute()
const router = useRouter()
const groups = [
  { label: '运行监控', items: [{ path:'/dashboard', label:'运行总览' }, { path:'/topology', label:'工程拓扑' }, { path:'/station', label:'站点趋势' }, { path:'/alarms', label:'告警中心' }, { path:'/areas', label:'片区供需' }] },
  { label: '智能调度', items: [{ path:'/agent', label:'Agent 助手' }, { path:'/schemes', label:'方案比较' }, { path:'/reviews', label:'建议审核' }] },
  { label: '资料与管理', items: [{ path:'/knowledge', label:'知识库' }, { path:'/reports', label:'报告中心' }, { path:'/users', label:'用户权限' }] },
]
const title = computed(() => groups.flatMap(g => g.items).find(i => i.path === route.path)?.label || '运行总览')
const userName = ref('值班调度员')
const signingOut = ref(false)

const syncCurrentUser = async () => {
  if (!localStorage.getItem('access_token')) return
  try {
    const user = await currentUserApi()
    userName.value = user.display_name
    localStorage.setItem('current_user', JSON.stringify(user))
  } catch {
    localStorage.removeItem('access_token')
    localStorage.removeItem('current_user')
  }
}

const signOut = async () => {
  signingOut.value = true
  try {
    await logoutApi()
  } catch {
    ElMessage.warning('退出接口暂不可用，已清除本地登录状态')
  } finally {
    localStorage.removeItem('access_token')
    localStorage.removeItem('current_user')
    signingOut.value = false
    await router.push('/login')
  }
}

onMounted(syncCurrentUser)
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand"><div class="brand-mark">水</div><div><strong>提水工程</strong><span>供水调度平台</span></div></div>
      <div class="env-tag">测试环境 · Mock 数据</div>
      <nav><div v-for="group in groups" :key="group.label" class="nav-group"><p>{{ group.label }}</p><button v-for="item in group.items" :key="item.path" :class="['nav-item', {active: route.path === item.path}]" @click="router.push(item.path)"><MenuIcon/><span>{{ item.label }}</span></button></div></nav>
      <div class="sidebar-foot"><span class="dot online"></span>只读分析模式</div>
    </aside>
    <main class="main-area">
      <header class="topbar"><div><span class="eyebrow">WATER DISPATCH / OPERATIONS</span><h1>{{ title }}</h1></div><div class="top-actions"><span class="connection"><i></i> Mock 数据已连接</span><el-button text :icon="Bell">告警 <b class="alarm-count">3</b></el-button><el-avatar :size="32" :icon="UserFilled"/><span class="user-name">{{ userName }}</span><el-button text :loading="signingOut" @click="signOut">退出</el-button></div></header>
      <section class="page-body"><router-view/></section>
    </main>
  </div>
</template>
