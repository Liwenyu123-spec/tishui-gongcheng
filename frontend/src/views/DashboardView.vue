<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/http'
import { alarmRows as localAlarmRows, stations as localStations } from '../mock'

interface HealthResponse {
  status: string
  service: string
  environment: string
  timestamp: string
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
  } else {
    healthStatus.value = '后端不可用'
    refresh.value = '失败'
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

onMounted(loadDashboard)
</script>

<template>
  <div class="page-title">
    <div>
      <h2>运行总览</h2>
      <p>全链路运行状态 · 最近刷新 {{ refresh }} · 数据源：{{ sourceLabel }} · {{ healthStatus }}</p>
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
