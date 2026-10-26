// 页面地图。开发时由 Vite 5173 提供，接口转发到 8000；
// 单地址模式则由 FastAPI 直接返回 frontend/dist，浏览器只打开 8000。
// meta.requiresAuth 只决定要不要先去登录页。角色和权限的真正校验在后端。
import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import './styles.css'
import App from './App.vue'
import { readCurrentUser } from './composables/currentUser'

const routes = [
  // 登录页不需要 Token，其余页面统一要求先完成登录。
  { path: '/login', meta: { guestOnly: true }, component: () => import('./views/LoginView.vue') },
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', meta: { requiresAuth: true }, component: () => import('./views/DashboardView.vue') },
  { path: '/topology', meta: { requiresAuth: true, roles: ['admin', 'operator'] }, component: () => import('./views/TopologyView.vue') },
  { path: '/station', meta: { requiresAuth: true, roles: ['admin', 'operator'] }, component: () => import('./views/StationView.vue') },
  { path: '/alarms', meta: { requiresAuth: true, roles: ['admin', 'operator'] }, component: () => import('./views/AlarmsView.vue') },
  { path: '/areas', meta: { requiresAuth: true, roles: ['admin', 'operator'] }, component: () => import('./views/AreasView.vue') },
  { path: '/agent', meta: { requiresAuth: true, permission: 'ask' }, component: () => import('./views/AgentView.vue') },
  { path: '/schemes', meta: { requiresAuth: true, permission: 'submit_scheme' }, component: () => import('./views/SchemesView.vue') },
  { path: '/reviews', meta: { requiresAuth: true, permission: 'review' }, component: () => import('./views/ReviewsView.vue') },
  { path: '/knowledge', meta: { requiresAuth: true, permission: 'knowledge' }, component: () => import('./views/KnowledgeView.vue') },
  { path: '/reports', meta: { requiresAuth: true }, component: () => import('./views/ReportsView.vue') },
  { path: '/users', meta: { requiresAuth: true, role: 'admin' }, component: () => import('./views/UsersView.vue') },
]
const router = createRouter({ history: createWebHistory(), routes })

// 路由守卫只负责前端体验层拦截，真正的角色和权限校验仍由后端接口执行。
router.beforeEach((to) => {
  const token = localStorage.getItem('access_token')
  const currentUser = readCurrentUser()

  // 已登录用户再次打开登录页时回到工作台，避免重复登录页面覆盖业务页面。
  if (to.meta.guestOnly && token) return '/dashboard'
  // 未登录访问业务页面时保存目标地址，登录后可继续进入原页面。
  if (to.meta.requiresAuth && !token) return { path: '/login', query: { redirect: to.fullPath } }
  // 页面入口按当前用户角色控制；后端仍会对直接请求再次校验。
  if (to.meta.role && currentUser.role !== to.meta.role) return '/dashboard'
  if (Array.isArray(to.meta.roles) && currentUser.role !== 'admin' && !to.meta.roles.includes(currentUser.role || '')) return '/dashboard'
  if (to.meta.permission && currentUser.role !== 'admin' && !currentUser.permissions?.includes(String(to.meta.permission))) return '/dashboard'
  return true
})

createApp(App).use(router).mount('#app')
