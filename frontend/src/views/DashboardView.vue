<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/http'
import { registerPageRefresh } from '../composables/pageRefresh'
import { alarmRows as localAlarmRows, stations as localStations } from '../mock'

interface HealthResponse {
  status: string
  service: string
  environment: string
  timestamp: string
  startup?: StartupStatus | null
}

interface StartupStatus {
  status: 'not_started' | 'starting' | 'ready' | 'degraded' | 'failed' | string
  mode?: string | null
  phase?: string | null
  message?: string | null
  elapsed_seconds?: number | null
  error?: string | null
}

interface StationSummary {
  id: string
  name: string
  status: string
  source: string
}

interface AlarmSummary {
  id: string
  station_name: string
  level: string
  metric: string
  value: number
  unit: string
  status: string
  occurred_at: string
}

interface SupplyBalanceResponse {
  total_supply: number
  total_balance: number
  source: string
}

interface TelemetryPoint {
  observed_at: string
  metric: string
  value: number
  unit: string
  quality: string
  is_stale: boolean
}

const router = useRouter()
const refresh = ref('未检查')
const healthStatus = ref('检查中')
const startupStatus = ref<StartupStatus>({
  status: 'not_started',
  message: '尚未读取单地址启动状态',
})
const healthLoading = ref(false)
const sourceLabel = ref('本地示例')
const stationRows = ref<StationSummary[]>([])
const alarmRows = ref<AlarmSummary[]>([])
const alarmLoaded = ref(false)
const supplyBalance = ref<SupplyBalanceResponse | null>(null)
const telemetryRows = ref<TelemetryPoint[]>([])

// 首页指标优先使用后端汇总数据；接口不可用时保留本地示例，避免总览区域空白。
const metrics = computed(() => {
  const onlineCount = stationRows.value.length ? stationRows.value.filter(item => item.status !== 'offline').length : 18
  const stationTotal = stationRows.value.length || 20
  const pressure = telemetryRows.value.find(item => item.metric === 'pressure')
  const totalSupply = supplyBalance.value?.total_supply ?? 24860
  const totalBalance = supplyBalance.value?.total_balance ?? -1400
  return [
    ['总供水量', totalSupply.toLocaleString(), 'm³/d', supplyBalance.value ? '后端供需接口' : '本地示例'],
    ['当前输水压力', pressure ? pressure.value.toFixed(2) : '0.72', 'MPa', pressure?.is_stale ? '数据已过期' : '遥测 Mock'],
    ['在线泵组', `${onlineCount} / ${stationTotal}`, '台', stationRows.value.length ? '站点状态接口' : '本地示例'],
    ['供需缺口', Math.abs(totalBalance).toLocaleString(), 'm³', totalBalance < 0 ? '当前存在供水缺口' : '供水有结余'],
  ]
})

// 将后端告警字段转换成总览表格使用的简短展示结构。
const alarmRowsView = computed(() => alarmLoaded.value ? alarmRows.value.map(item => ({
  level: item.level === 'high' ? '高' : item.level === 'medium' ? '中' : '低',
  station: item.station_name,
  metric: item.metric,
  value: `${item.value} ${item.unit}`,
  time: item.occurred_at.slice(11, 16),
  status: item.status,
})) : localAlarmRows)

// 拓扑摘要使用站点接口返回的状态；接口失败时回退到本地站点名称。
const flowStations = computed(() => stationRows.value.length
  ? stationRows.value.map(item => ({ name: item.name, status: item.status }))
  : localStations.map(name => ({ name, status: 'running' })))

const startupStatusNames: Record<string, string> = {
  not_started: '未开始',
  starting: '准备中',
  ready: '已就绪',
  degraded: '已降级',
  failed: '准备失败',
}

const startupPhaseNames: Record<string, string> = {
  idle: '等待启动任务',
  initializing: '初始化',
  warmup: '模型预热',
  reindex: '重建知识索引',
  completed: '已完成',
  failed: '失败',
}

const startupLabel = computed(() => startupStatusNames[startupStatus.value.status] || startupStatus.value.status)
const startupPhaseLabel = computed(() => startupPhaseNames[startupStatus.value.phase || ''] || startupStatus.value.phase || '未知阶段')
const startupTagClass = computed(() => {
  if (startupStatus.value.status === 'ready') return 'tag-green'
  if (startupStatus.value.status === 'failed') return 'tag-red'
  if (startupStatus.value.status === 'degraded') return 'tag-amber'
  return 'tag-amber'
})
const startupNeedsAttention = computed(() => ['starting', 'degraded', 'failed'].includes(startupStatus.value.status))

// 一次刷新总览所需的健康检查、站点、告警、供需和代表性遥测数据。
const loadDashboard = async () => {
  healthLoading.value = true
  const results = await Promise.allSettled([
    api<HealthResponse>('/api/v1/health'),
    api<StationSummary[]>('/api/v1/stations'),
    api<AlarmSummary[]>('/api/v1/alarms?status=unconfirmed'),
    api<SupplyBalanceResponse>('/api/v1/supply/balance'),
    api<TelemetryPoint[]>('/api/v1/stations/pump-02/telemetry?metric=pressure'),
  ])
  const health = results[0]
  if (health.status === 'fulfilled') {
    healthStatus.value = health.value.status === 'ok' ? '后端正常' : health.value.status
    refresh.value = health.value.timestamp.slice(11, 19)
    startupStatus.value = health.value.startup || {
      status: 'not_started',
      message: '后端未返回 RAG 启动状态',
    }
  } else {
    healthStatus.value = '后端不可用'
    refresh.value = '失败'
    startupStatus.value = {
      status: 'failed',
      phase: 'failed',
      message: '无法读取后端启动状态',
    }
  }
  if (results[1].status === 'fulfilled') stationRows.value = results[1].value
  if (results[2].status === 'fulfilled') {
    alarmRows.value = results[2].value
    alarmLoaded.value = true
  }
  if (results[3].status === 'fulfilled') supplyBalance.value = results[3].value
  if (results[4].status === 'fulfilled') telemetryRows.value = results[4].value
  sourceLabel.value = results.slice(1).some(item => item.status === 'fulfilled') ? '后端 Mock' : '本地示例'
  healthLoading.value = false
}

// 顶栏「刷新本页」和页面内的「刷新数据」复用同一套加载逻辑，避免两种刷新行为不一致。
registerPageRefresh(loadDashboard)
onMounted(loadDashboard)
</script>

<template>
  <div class="page-title">
    <div>
      <h2>运行总览</h2>
      <p>全链路运行状态 · 最近刷新 {{ refresh }} · 数据源：{{ sourceLabel }} · {{ healthStatus }} · RAG：{{ startupLabel }}</p>
    </div>
    <el-button class="button-stable button-stable--md" type="primary" plain :loading="healthLoading" @click="loadDashboard">刷新数据</el-button>
  </div>

  <div class="grid grid-4">
    <div v-for="m in metrics" :key="m[0]" class="panel metric">
      <span class="metric-label">{{ m[0] }}</span>
      <div class="metric-value">{{ m[1] }} <small>{{ m[2] }}</small></div>
      <span class="metric-foot">{{ m[3] }}</span>
    </div>
  </div>

  <div class="panel" style="margin-top:18px">
    <div class="panel-head"><h3>全链路健康度</h3><span>站点数据：{{ stationRows.length ? '后端 Mock' : '本地示例' }}</span></div>
    <div v-if="startupNeedsAttention" class="warning" style="margin-bottom:14px">
      <strong>RAG 启动状态：{{ startupLabel }}</strong>
      <span> · {{ startupPhaseLabel }} · {{ startupStatus.message || '请稍后刷新状态' }}</span>
      <span v-if="startupStatus.elapsed_seconds != null"> · 已耗时 {{ startupStatus.elapsed_seconds }} 秒</span>
      <span v-if="startupStatus.error"> · 原因：{{ startupStatus.error }}</span>
    </div>
    <div v-else class="muted" style="margin-bottom:14px">
      RAG 启动状态：<span :class="['tag', startupTagClass]">{{ startupLabel }}</span>
      <span> · {{ startupPhaseLabel }}<span v-if="startupStatus.elapsed_seconds != null"> · 耗时 {{ startupStatus.elapsed_seconds }} 秒</span></span>
    </div>
    <div class="flow">
      <template v-for="(station, i) in [{ name: '娘子关取水', status: 'running' }, ...flowStations, { name: '渠道自流', status: 'running' }]" :key="station.name">
        <div class="flow-node" @click="router.push('/station')">
          <strong>{{ station.name }}</strong>
          <span :style="{ color: station.status === 'warning' ? '#f3b664' : '#74d8b5' }">{{ station.status === 'warning' ? '关注' : '运行正常' }}</span>
        </div>
        <span v-if="i < flowStations.length + 1" class="flow-arrow">→</span>
      </template>
    </div>
  </div>

  <div class="grid grid-2" style="margin-top:18px">
    <div class="panel">
      <div class="panel-head"><h3>未确认告警</h3><el-button link type="primary" @click="router.push('/alarms')">查看全部</el-button></div>
      <div class="table-wrap">
        <el-table :data="alarmRowsView.slice(0, 2)" size="small">
          <el-table-column prop="level" label="级别" width="70"><template #default="s"><span :class="['tag', s.row.level === '高' ? 'tag-red' : 'tag-amber']">{{ s.row.level }}</span></template></el-table-column>
          <el-table-column prop="station" label="站点" />
          <el-table-column prop="metric" label="指标" />
          <el-table-column prop="time" label="时间" width="80" />
        </el-table>
      </div>
    </div>
    <div class="panel">
      <div class="panel-head"><h3>待办事项</h3><span>需要人工确认</span></div>
      <div class="table-wrap"><div class="warning">二泵站流量下降与西部片区压力下降可能关联</div><p class="muted" style="font-size:14px;margin:15px 0 0">建议先核查二泵站 2 号泵入口压力和渠道前段水位。</p></div>
    </div>
  </div>
</template>
