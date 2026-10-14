import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './styles.css'
import App from './App.vue'

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', component: () => import('./views/DashboardView.vue') },
  { path: '/topology', component: () => import('./views/TopologyView.vue') },
  { path: '/station', component: () => import('./views/StationView.vue') },
  { path: '/alarms', component: () => import('./views/AlarmsView.vue') },
  { path: '/areas', component: () => import('./views/AreasView.vue') },
  { path: '/agent', component: () => import('./views/AgentView.vue') },
  { path: '/schemes', component: () => import('./views/SchemesView.vue') },
  { path: '/reviews', component: () => import('./views/ReviewsView.vue') },
  { path: '/knowledge', component: () => import('./views/KnowledgeView.vue') },
  { path: '/reports', component: () => import('./views/ReportsView.vue') },
  { path: '/users', component: () => import('./views/UsersView.vue') },
]
const router = createRouter({ history: createWebHistory(), routes })
createApp(App).use(router).use(ElementPlus).mount('#app')
