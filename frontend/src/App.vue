<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Menu as MenuIcon, Bell, UserFilled, Refresh } from '@element-plus/icons-vue'
import { currentUser as currentUserApi, logout as logoutApi } from './api/auth'
import { acknowledgeNotification as acknowledgeNotificationApi, escalateNotification as escalateNotificationApi, fetchNotifications, retryNotification as retryNotificationApi } from './api/notifications'
import { resolveIncident } from './api/incidents'
import { runPageRefresh, usePageRefresh } from './composables/pageRefresh'
import { readCurrentUser } from './composables/currentUser'

interface NotificationItem {
  id: string
  incident_id: string
  recipient: string
  channel: string
  status: string
  sent_at: string
  acknowledged_at: string | null
  retry_count: number
  failure_reason: string | null
  incident_status: string
  escalation_level: number
  escalated_at: string | null
  data_source: string
}

interface SessionUser {
  display_name: string
  role: string
  permissions: string[]
}

interface NavigationItem {
  path: string
  label: string
  permission?: string
  role?: string
  roles?: string[]
}

interface NavigationGroup {
  label: string
  items: NavigationItem[]
}

const route = useRoute()
const router = useRouter()
const routerReady = ref(false)
router.isReady().finally(() => { routerReady.value = true })
const groups: NavigationGroup[] = [
  { label: '运行监控', items: [{ path:'/dashboard', label:'运行总览' }, { path:'/topology', label:'工程拓扑', roles:['admin', 'operator'] }, { path:'/station', label:'站点趋势', roles:['admin', 'operator'] }, { path:'/alarms', label:'告警中心', roles:['admin', 'operator'] }, { path:'/areas', label:'片区供需', roles:['admin', 'operator'] }] },
  { label: '智能调度', items: [{ path:'/agent', label:'Agent 助手', permission:'ask' }, { path:'/schemes', label:'方案比较', permission:'submit_scheme' }, { path:'/reviews', label:'建议审核', permission:'review' }] },
  { label: '资料与管理', items: [{ path:'/knowledge', label:'知识库', permission:'knowledge' }, { path:'/reports', label:'报告中心' }, { path:'/users', label:'用户权限', role:'admin' }] },
]

// 从本地会话读取角色和权限，页面刷新后菜单可以立即保持一致。
const readSessionUser = (): SessionUser => {
  const user = readCurrentUser()
  return { display_name: user.display_name || '值班调度员', role: user.role || '', permissions: user.permissions || [] }
}

const sessionUser = ref<SessionUser>(readSessionUser())
const loggedIn = ref(Boolean(localStorage.getItem('access_token')))
const canAccessNavigation = (item: NavigationItem) => {
  if (sessionUser.value.role === 'admin') return true
  if (item.role && item.role !== sessionUser.value.role) return false
  if (item.roles && !item.roles.includes(sessionUser.value.role)) return false
  return !item.permission || sessionUser.value.permissions.includes(item.permission)
}

// 只显示当前账号有权进入的导航项；接口权限仍由后端再次强制校验。
const visibleGroups = computed(() => {
  if (!loggedIn.value) return []
  return groups
    .map(group => ({ ...group, items: group.items.filter(canAccessNavigation) }))
    .filter(group => group.items.length)
})
const title = computed(() => visibleGroups.value.flatMap(g => g.items).find(i => i.path === route.path)?.label || '调度工作台')
const userName = ref(sessionUser.value.display_name)
const signingOut = ref(false)
const notificationVisible = ref(false)
const notificationLoading = ref(false)
// 保存当前正在处理的通知动作，避免同一按钮被重复提交。
const notificationActionKey = ref('')
const notifications = ref<NotificationItem[]>([])
const unreadNotificationCount = computed(() => notifications.value.filter(item => item.status === 'sent').length)
// 审批负责人可以查看通知，但确认、升级和关闭事件属于调度处置权限。
const canManageNotifications = computed(() => ['admin', 'operator'].includes(sessionUser.value.role))
let notificationTimer: ReturnType<typeof setInterval> | undefined

const notificationStatusName: Record<string, string> = {
  sent: '待确认',
  acknowledged: '已确认',
  failed: '发送失败',
}

const incidentStatusName: Record<string, string> = {
  open: '待处理',
  acknowledged: '已接管',
  in_progress: '处理中',
  resolved: '已解决',
  false_positive: '误报关闭',
}

const formatNotificationTime = (value: string) => value ? value.slice(0, 16).replace('T', ' ') : '—'

const refreshSession = () => {
  loggedIn.value = Boolean(localStorage.getItem('access_token'))
  sessionUser.value = readSessionUser()
  userName.value = sessionUser.value.display_name
}

const syncCurrentUser = async () => {
  refreshSession()
  if (!loggedIn.value) return
  try {
    const user = await currentUserApi()
    sessionUser.value = { display_name: user.display_name, role: user.role, permissions: user.permissions }
    userName.value = user.display_name
    loggedIn.value = true
    localStorage.setItem('current_user', JSON.stringify(user))
  } catch {
    localStorage.removeItem('access_token')
    localStorage.removeItem('current_user')
    loggedIn.value = false
    sessionUser.value = readSessionUser()
    userName.value = sessionUser.value.display_name
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
    loggedIn.value = false
    sessionUser.value = readSessionUser()
    userName.value = sessionUser.value.display_name
    signingOut.value = false
    await router.push('/login')
  }
}

const loadNotifications = async () => {
  // 登录页和未登录状态不请求受保护的通知接口，避免产生误导性的 401 提示。
  if (!localStorage.getItem('access_token')) {
    notifications.value = []
    return
  }
  notificationLoading.value = true
  try {
    notifications.value = await fetchNotifications<NotificationItem>()
  } catch (error) {
    // 只有已登录状态才提示通知接口异常，未登录时保持安静等待下一次登录。
    const detail = error instanceof Error ? error.message : '未知错误'
    ElMessage.warning(`通知接口暂不可用：${detail}`)
  } finally {
    notificationLoading.value = false
  }
}

const openNotifications = async () => {
  notificationVisible.value = true
  await loadNotifications()
}

const acknowledgeNotification = async (item: NotificationItem) => {
  notificationActionKey.value = `ack:${item.id}`
  try {
    const updated = await acknowledgeNotificationApi<NotificationItem>(item.id)
    item.status = updated.status
    item.acknowledged_at = updated.acknowledged_at
    ElMessage.success('通知已确认')
  } catch {
    ElMessage.error('通知确认失败，请稍后重试')
  } finally {
    notificationActionKey.value = ''
  }
}

const escalateNotification = async (item: NotificationItem) => {
  notificationActionKey.value = `escalate:${item.id}`
  try {
    await escalateNotificationApi<NotificationItem>(item.id)
    await loadNotifications()
    ElMessage.success('通知已升级给备用调度联系人')
  } catch {
    ElMessage.error('通知升级失败，可能已经升级或状态已变化')
  } finally {
    notificationActionKey.value = ''
  }
}

const retryNotification = async (item: NotificationItem) => {
  notificationActionKey.value = `retry:${item.id}`
  try {
    const updated = await retryNotificationApi<NotificationItem>(item.id)
    Object.assign(item, updated)
    ElMessage.success('失败通知已重新发送')
  } catch {
    ElMessage.error('通知重试失败，请确认通知仍处于发送失败状态')
  } finally {
    notificationActionKey.value = ''
  }
}

const resolveNotificationIncident = async (item: NotificationItem) => {
  notificationActionKey.value = `resolve:${item.id}`
  try {
    await resolveIncident(item.incident_id)
    await loadNotifications()
    ElMessage.success('事件已关闭')
  } catch {
    ElMessage.error('事件关闭失败，请稍后重试')
  } finally {
    notificationActionKey.value = ''
  }
}

// 登录页与业务页切换时重新读取当前账号，避免退出后菜单和通知操作权限沿用旧账号。
watch(() => route.path, async () => {
  await syncCurrentUser()
  await loadNotifications()
})

// 顶栏「刷新本页」按钮：触发当前页面注册的刷新动作。
// 按钮只在页面注册了刷新动作时可用，登录页会自动置灰。
const { handler: pageRefreshHandler, refreshing: pageRefreshing } = usePageRefresh()
const refreshCurrentPage = async () => {
  const done = await runPageRefresh()
  if (done) ElMessage.success('本页数据已刷新')
}

onMounted(() => {
  syncCurrentUser()
  loadNotifications()
  notificationTimer = setInterval(loadNotifications, 15000)
})

onBeforeUnmount(() => {
  if (notificationTimer) clearInterval(notificationTimer)
})
</script>

<template>
  <div v-if="!routerReady" class="boot-screen"></div>
  <router-view v-else-if="route.path === '/login'" />
  <div v-else class="app-shell">
    <aside class="sidebar">
      <div class="brand"><div class="brand-mark">水</div><div><strong>提水工程</strong><span>供水调度平台</span></div></div>
      <div class="env-tag">测试环境 · 数据库</div>
      <nav><div v-for="group in visibleGroups" :key="group.label" class="nav-group"><p>{{ group.label }}</p><button v-for="item in group.items" :key="item.path" :class="['nav-item', {active: route.path === item.path}]" @click="router.push(item.path)"><MenuIcon/><span>{{ item.label }}</span></button></div></nav>
      <div class="sidebar-foot"><span class="dot online"></span>只读分析模式</div>
    </aside>
    <main class="main-area">
      <header class="topbar"><div><span class="eyebrow">WATER DISPATCH / OPERATIONS</span><h1>{{ title }}</h1></div><div class="top-actions"><span class="connection"><i></i> 数据库已连接</span><el-button class="refresh-page-button" text :icon="Refresh" :loading="pageRefreshing" :disabled="!pageRefreshHandler" @click="refreshCurrentPage">刷新本页</el-button><el-button text :icon="Bell" @click="openNotifications">通知 <b class="alarm-count">{{ unreadNotificationCount }}</b></el-button><el-avatar :size="32" :icon="UserFilled"/><span class="user-name">{{ userName }}</span><el-button class="button-stable button-stable--xs" text :loading="signingOut" @click="signOut">退出</el-button></div></header>
      <section class="page-body"><router-view/></section>
    </main>
  </div>
  <el-dialog v-model="notificationVisible" title="站点事件通知" width="620px">
    <div style="display:flex;justify-content:flex-end;margin-bottom:12px"><el-button class="button-stable button-stable--md" size="small" :loading="notificationLoading" @click="loadNotifications">刷新通知</el-button></div>
    <div v-if="!notifications.length" class="empty">暂无平台内通知</div>
    <div v-for="item in notifications" :key="item.id" class="panel" style="padding:14px;margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px"><strong>{{ item.incident_id }}</strong><span :class="['tag', item.status === 'sent' ? 'tag-amber' : item.status === 'failed' ? 'tag-red' : 'tag-green']">{{ notificationStatusName[item.status] || item.status }}</span></div>
      <p class="muted" style="margin:8px 0 0">事件状态：{{ incidentStatusName[item.incident_status] || item.incident_status }} · 渠道：{{ item.channel }} · 接收人：{{ item.recipient }} · {{ formatNotificationTime(item.sent_at) }}</p>
       <p v-if="item.status === 'failed'" class="muted" style="margin:8px 0 0">失败原因：{{ item.failure_reason || '未提供' }} · 已重试 {{ item.retry_count }} 次</p>
      <p v-if="item.escalated_at" class="muted" style="margin:8px 0 0">已升级给备用联系人</p>
       <div v-if="canManageNotifications" style="display:flex;justify-content:flex-end;gap:8px;margin-top:10px"><el-button v-if="item.status === 'failed'" class="button-stable button-stable--sm" size="small" type="warning" :loading="notificationActionKey === `retry:${item.id}`" :disabled="Boolean(notificationActionKey)" @click="retryNotification(item)">重试发送</el-button><el-button v-if="item.status === 'sent' && !item.escalated_at" class="button-stable button-stable--sm" size="small" :loading="notificationActionKey === `escalate:${item.id}`" :disabled="Boolean(notificationActionKey)" @click="escalateNotification(item)">升级通知</el-button><el-button v-if="item.status === 'sent'" class="button-stable button-stable--sm" size="small" type="primary" :loading="notificationActionKey === `ack:${item.id}`" :disabled="Boolean(notificationActionKey)" @click="acknowledgeNotification(item)">确认通知</el-button><el-button v-if="item.incident_status !== 'resolved'" class="button-stable button-stable--sm" size="small" type="success" plain :loading="notificationActionKey === `resolve:${item.id}`" :disabled="Boolean(notificationActionKey)" @click="resolveNotificationIncident(item)">关闭事件</el-button></div>
    </div>
  </el-dialog>
</template>
