<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Menu as MenuIcon, Bell, UserFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { currentUser as currentUserApi, logout as logoutApi } from './api/auth'
import { api } from './api/http'

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
const notificationVisible = ref(false)
const notificationLoading = ref(false)
const notifications = ref<NotificationItem[]>([])
const unreadNotificationCount = computed(() => notifications.value.filter(item => item.status === 'sent').length)
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

const loadNotifications = async () => {
  notificationLoading.value = true
  try {
    notifications.value = await api<NotificationItem[]>('/api/v1/notifications')
  } catch {
    ElMessage.warning('通知接口暂不可用，请稍后重试')
  } finally {
    notificationLoading.value = false
  }
}

const openNotifications = async () => {
  notificationVisible.value = true
  await loadNotifications()
}

const acknowledgeNotification = async (item: NotificationItem) => {
  try {
    const updated = await api<NotificationItem>(`/api/v1/notifications/${encodeURIComponent(item.id)}/ack`, { method: 'POST' })
    item.status = updated.status
    item.acknowledged_at = updated.acknowledged_at
    ElMessage.success('通知已确认')
  } catch {
    ElMessage.error('通知确认失败，请稍后重试')
  }
}

const escalateNotification = async (item: NotificationItem) => {
  try {
    await api<NotificationItem>(`/api/v1/notifications/${encodeURIComponent(item.id)}/escalate`, { method: 'POST' })
    await loadNotifications()
    ElMessage.success('通知已升级给备用调度联系人')
  } catch {
    ElMessage.error('通知升级失败，可能已经升级或状态已变化')
  }
}

const resolveNotificationIncident = async (item: NotificationItem) => {
  try {
    await api(`/api/v1/incidents/${encodeURIComponent(item.incident_id)}/resolve`, { method: 'POST' })
    await loadNotifications()
    ElMessage.success('事件已关闭')
  } catch {
    ElMessage.error('事件关闭失败，请稍后重试')
  }
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
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand"><div class="brand-mark">水</div><div><strong>提水工程</strong><span>供水调度平台</span></div></div>
      <div class="env-tag">测试环境 · Mock 数据</div>
      <nav><div v-for="group in groups" :key="group.label" class="nav-group"><p>{{ group.label }}</p><button v-for="item in group.items" :key="item.path" :class="['nav-item', {active: route.path === item.path}]" @click="router.push(item.path)"><MenuIcon/><span>{{ item.label }}</span></button></div></nav>
      <div class="sidebar-foot"><span class="dot online"></span>只读分析模式</div>
    </aside>
    <main class="main-area">
      <header class="topbar"><div><span class="eyebrow">WATER DISPATCH / OPERATIONS</span><h1>{{ title }}</h1></div><div class="top-actions"><span class="connection"><i></i> Mock 数据已连接</span><el-button text :icon="Bell" @click="openNotifications">通知 <b class="alarm-count">{{ unreadNotificationCount }}</b></el-button><el-avatar :size="32" :icon="UserFilled"/><span class="user-name">{{ userName }}</span><el-button text :loading="signingOut" @click="signOut">退出</el-button></div></header>
      <section class="page-body"><router-view/></section>
    </main>
  </div>
  <el-dialog v-model="notificationVisible" title="站点事件通知" width="620px">
    <div style="display:flex;justify-content:flex-end;margin-bottom:12px"><el-button size="small" :loading="notificationLoading" @click="loadNotifications">刷新通知</el-button></div>
    <div v-if="!notifications.length" class="empty">暂无平台内通知</div>
    <div v-for="item in notifications" :key="item.id" class="panel" style="padding:14px;margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px"><strong>{{ item.incident_id }}</strong><span :class="['tag', item.status === 'sent' ? 'tag-amber' : item.status === 'failed' ? 'tag-red' : 'tag-green']">{{ notificationStatusName[item.status] || item.status }}</span></div>
      <p class="muted" style="margin:8px 0 0">事件状态：{{ incidentStatusName[item.incident_status] || item.incident_status }} · 渠道：{{ item.channel }} · 接收人：{{ item.recipient }} · {{ formatNotificationTime(item.sent_at) }}</p>
      <p v-if="item.escalated_at" class="muted" style="margin:8px 0 0">已升级给备用联系人</p>
      <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:10px"><el-button v-if="item.status === 'sent' && !item.escalated_at" size="small" @click="escalateNotification(item)">升级通知</el-button><el-button v-if="item.status === 'sent'" size="small" type="primary" @click="acknowledgeNotification(item)">确认通知</el-button><el-button v-if="item.incident_status !== 'resolved'" size="small" type="success" plain @click="resolveNotificationIncident(item)">关闭事件</el-button></div>
    </div>
  </el-dialog>
</template>
