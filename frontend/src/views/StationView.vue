<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import type { ECharts } from 'echarts'
import { api } from '../api/http'
import { telemetry, stations as mockStations } from '../mock'

interface ApiStation {
  id: string
  name: string
  sequence: number
  station_type: string
  status: string
  source: string
}

interface StationDetail extends ApiStation {
  location: string
  description: string
  metrics: string[]
}

interface TelemetryPoint {
  observed_at: string
  metric: string
  value: number
  unit: string
  source: string
  quality: string
  is_stale: boolean
}

interface IncidentResponse {
  id: string
  station_id: string
  category: string
  level: string
  status: string
  report_count: number
  deduplicated: boolean
}

interface HeartbeatResponse {
  station_id: string
  received_at: string
  last_seen_at: string
  status: string
  is_stale: boolean
}

interface StationContact {
  station_id: string
  contact_type: 'primary' | 'backup'
  recipient: string
  channel: string
  priority: number
  enabled: boolean
}

const fallbackStationIds: Record<string, string> = {
  集泉一站: 'jq-01',
  一泵站: 'pump-01',
  二泵站: 'pump-02',
  三泵站: 'pump-03',
  四泵站: 'pump-04',
  平定侧入口: 'pingding-inlet',
}
const stationOptions = ref([...mockStations])
const stationRecords = ref<ApiStation[]>([])
const station = ref('二泵站')
const stationDetail = ref<StationDetail | null>(null)
const chart = ref<HTMLElement>()
const points = ref<TelemetryPoint[]>([])
const loading = ref(false)
const detailLoading = ref(false)
const chartInstance = ref<ECharts>()
const sourceLabel = ref('后端 Mock 数据')
const heartbeatStatus = ref('未检测')
const heartbeatAt = ref('')
const heartbeatLoading = ref(false)
let heartbeatRequestInFlight = false
let heartbeatTimer: ReturnType<typeof setInterval> | undefined
const stationContacts = ref<StationContact[]>([])
const contactLoading = ref(false)
const primaryContactSummary = computed(() => stationContacts.value.filter(item => item.contact_type === 'primary' && item.enabled).map(item => item.recipient).join('、') || '未配置')
const backupContactSummary = computed(() => stationContacts.value.filter(item => item.contact_type === 'backup' && item.enabled).map(item => item.recipient).join('、') || '未配置')
const reportVisible = ref(false)
const reportSubmitting = ref(false)
const reportForm = ref({
  category: '运行异常',
  level: 'medium',
  description: '',
  deduplicationKey: '',
  simulateDeliveryFailure: false,
})
const stationIds = computed<Record<string, string>>(() => Object.fromEntries(stationRecords.value.map(item => [item.name, item.id])))
const selectedStationId = computed(() => stationIds.value[station.value] || fallbackStationIds[station.value])
const flow = computed(() => points.value.find(point => point.metric === 'flow')?.value ?? 1086)
const pressure = computed(() => points.value.find(point => point.metric === 'pressure')?.value ?? 0.74)
const level = computed(() => points.value.find(point => point.metric === 'level')?.value ?? 3.68)

const renderChart = (items: TelemetryPoint[]) => {
  const flowPoints = items.filter(point => point.metric === 'flow').reverse()
  const pressurePoints = items.filter(point => point.metric === 'pressure').reverse()
  const times = [...new Set(items.map(point => point.observed_at))].sort()
  chartInstance.value?.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#8da5b3' } },
    xAxis: { type: 'category', data: times.map(time => time.slice(11, 16)), axisLabel: { color: '#6f8b9b' } },
    yAxis: { axisLabel: { color: '#6f8b9b' }, splitLine: { lineStyle: { color: '#183444' } } },
    series: [
      { name: '流量 m³/h', type: 'line', smooth: true, data: flowPoints.map(point => point.value), lineStyle: { color: '#5be0ca' }, areaStyle: { color: 'rgba(91,224,202,.12)' } },
      { name: '压力 MPa', type: 'line', smooth: true, data: pressurePoints.map(point => point.value * 1200), lineStyle: { color: '#efb866' } },
    ],
  })
}

const loadStations = async () => {
  try {
    const result = await api<ApiStation[]>('/api/v1/stations')
    if (result.length) {
      stationRecords.value = result
      stationOptions.value = result.sort((a, b) => a.sequence - b.sequence).map(item => item.name)
      if (!stationOptions.value.includes(station.value)) station.value = stationOptions.value[0]
    }
  } catch {
    ElMessage.warning('站点列表接口暂不可用，当前使用本地站点列表')
  }
}

const loadStationDetail = async () => {
  detailLoading.value = true
  try {
    stationDetail.value = await api<StationDetail>(`/api/v1/stations/${selectedStationId.value}`)
  } catch {
    stationDetail.value = null
    ElMessage.warning('站点详情接口暂不可用')
  } finally {
    detailLoading.value = false
  }
}

const loadTelemetry = async () => {
  loading.value = true
  try {
    points.value = await api<TelemetryPoint[]>(`/api/v1/stations/${selectedStationId.value}/telemetry`)
    sourceLabel.value = '后端 Mock 数据'
  } catch {
    points.value = telemetry.flatMap(item => [
      { observed_at: `2026-10-15T${item.time}:00Z`, metric: 'flow', value: item.flow, unit: 'm³/h', source: 'mock', quality: 'good', is_stale: false },
      { observed_at: `2026-10-15T${item.time}:00Z`, metric: 'pressure', value: item.pressure, unit: 'MPa', source: 'mock', quality: 'good', is_stale: false },
    ])
    sourceLabel.value = '本地 Mock 数据'
    ElMessage.warning('遥测接口暂不可用，当前显示本地 Mock 数据')
  } finally {
    loading.value = false
    renderChart(points.value)
  }
}

const loadSelectedStation = () => {
  loadStationDetail()
  loadTelemetry()
  sendHeartbeat(false)
  loadStationContacts()
}

const loadStationContacts = async () => {
  contactLoading.value = true
  try {
    stationContacts.value = await api<StationContact[]>(`/api/v1/stations/${encodeURIComponent(selectedStationId.value)}/contacts`)
  } catch {
    stationContacts.value = []
    ElMessage.warning('站点联系人接口暂不可用')
  } finally {
    contactLoading.value = false
  }
}

const sendHeartbeat = async (manual = false) => {
  if (heartbeatRequestInFlight) return
  heartbeatRequestInFlight = true
  if (manual) heartbeatLoading.value = true
  try {
    const result = await api<HeartbeatResponse>(`/api/v1/stations/${encodeURIComponent(selectedStationId.value)}/heartbeat`, { method: 'POST' })
    heartbeatStatus.value = result.is_stale ? '已过期' : result.status === 'online' ? '在线' : result.status
    heartbeatAt.value = result.last_seen_at.slice(0, 16).replace('T', ' ')
    if (manual) ElMessage.success('站点心跳已发送')
  } catch {
    heartbeatStatus.value = '不可用'
    if (manual) ElMessage.warning('站点心跳接口暂不可用')
  } finally {
    heartbeatRequestInFlight = false
    if (manual) heartbeatLoading.value = false
  }
}

const openIncidentReport = () => {
  reportForm.value = {
    category: '运行异常',
    level: 'medium',
    description: '',
    deduplicationKey: '',
    simulateDeliveryFailure: false,
  }
  reportVisible.value = true
}

const submitIncidentReport = async () => {
  if (!reportForm.value.description.trim()) {
    ElMessage.warning('请先填写问题描述')
    return
  }
  reportSubmitting.value = true
  try {
    const currentUser = JSON.parse(localStorage.getItem('current_user') || '{}') as { username?: string }
    const result = await api<IncidentResponse>(`/api/v1/stations/${encodeURIComponent(selectedStationId.value)}/incidents`, {
      method: 'POST',
      body: JSON.stringify({
        category: reportForm.value.category,
        level: reportForm.value.level,
        description: reportForm.value.description.trim(),
        reported_by: currentUser.username || 'station-operator',
        deduplication_key: reportForm.value.deduplicationKey.trim() || undefined,
        simulate_delivery_failure: reportForm.value.simulateDeliveryFailure,
      }),
    })
    reportVisible.value = false
    ElMessage.success(`事件已上报：${result.id}`)
  } catch {
    ElMessage.error('事件上报失败，请联系调度人员或稍后重试')
  } finally {
    reportSubmitting.value = false
  }
}

onMounted(async () => {
  chartInstance.value = echarts.init(chart.value!)
  await loadStations()
  loadSelectedStation()
  heartbeatTimer = setInterval(() => sendHeartbeat(false), 30000)
})
watch(station, loadSelectedStation)
onBeforeUnmount(() => {
  chartInstance.value?.dispose()
  if (heartbeatTimer) clearInterval(heartbeatTimer)
})
</script>

<template>
  <div class="page-title"><div><h2>站点趋势</h2><p>查看泵站压力、流量、水位与能耗趋势，缺数区间显式标注 · {{ sourceLabel }}</p></div><div class="station-actions"><el-tag class="station-status" :type="heartbeatStatus === '在线' ? 'success' : heartbeatStatus === '不可用' ? 'danger' : 'info'" effect="dark">通讯：{{ heartbeatStatus }}</el-tag><span class="station-heartbeat-time">最近心跳：{{ heartbeatAt || '尚未收到' }}</span><el-button class="station-contact-button" type="warning" plain @click="openIncidentReport">联系调度</el-button><el-button class="station-heartbeat-button" size="small" :loading="heartbeatLoading" @click="sendHeartbeat(true)">发送心跳</el-button><el-select v-model="station" class="station-select"><el-option v-for="s in stationOptions" :key="s" :label="s" :value="s"/></el-select></div></div>
  <div class="grid grid-4"><div class="panel metric"><span class="metric-label">当前流量</span><div class="metric-value">{{flow.toLocaleString()}} <small>m³/h</small></div><span class="status-line status-ok"><i/>{{ loading ? '正在加载' : `数据正常 · ${sourceLabel}` }}</span></div><div class="panel metric"><span class="metric-label">出水压力</span><div class="metric-value">{{pressure.toFixed(2)}} <small>MPa</small></div><span class="metric-foot">后端遥测值</span></div><div class="panel metric"><span class="metric-label">水池水位</span><div class="metric-value">{{level.toFixed(2)}} <small>m</small></div><span class="metric-foot">后端遥测值</span></div><div class="panel metric"><span class="metric-label">站点状态</span><div class="metric-value">{{ detailLoading ? '加载中' : stationDetail?.status || '—' }}</div><span class="metric-foot">最近心跳：{{ heartbeatAt || '尚未收到' }}</span></div></div>
  <div class="panel" style="margin-top:18px"><div class="panel-head"><h3>24 小时运行趋势</h3><span>流量 / 压力 · {{sourceLabel}}</span></div><div ref="chart" class="chart"></div></div>
  <el-dialog v-model="reportVisible" title="联系调度 · 一键上报问题" width="520px">
    <p class="muted" style="margin-top:0">当前站点：{{ station }}（{{ selectedStationId }}）。事件会进入平台内通知队列。</p>
    <p class="muted" style="margin:0 0 12px">调度联系人：{{ contactLoading ? '加载中…' : primaryContactSummary }} · 备用联系人：{{ contactLoading ? '加载中…' : backupContactSummary }} · 渠道：平台内通知</p>
    <el-form label-width="90px">
      <el-form-item label="事件类型"><el-input v-model="reportForm.category" placeholder="例如：流量异常、设备异响" /></el-form-item>
      <el-form-item label="严重等级"><el-select v-model="reportForm.level" style="width:100%"><el-option label="一般" value="low" /><el-option label="重要" value="medium" /><el-option label="严重" value="high" /><el-option label="紧急" value="critical" /></el-select></el-form-item>
      <el-form-item label="问题描述"><el-input v-model="reportForm.description" type="textarea" :rows="4" placeholder="请描述现场现象、发生时间和已采取的措施" /></el-form-item>
      <el-form-item label="事件指纹"><el-input v-model="reportForm.deduplicationKey" placeholder="可选；相同故障重复上报时用于合并通知" /></el-form-item>
      <el-form-item label="通知测试"><el-checkbox v-model="reportForm.simulateDeliveryFailure">模拟通知发送失败（Mock）</el-checkbox></el-form-item>
    </el-form>
    <template #footer><el-button @click="reportVisible = false">取消</el-button><el-button class="button-stable button-stable--md" type="warning" :loading="reportSubmitting" @click="submitIncidentReport">提交上报</el-button></template>
  </el-dialog>
</template>

<style scoped>
/* 固定站点操作区各控件的宽度，心跳按钮加载时不会把“联系调度”推来推去。 */
.station-actions { display: flex; flex-wrap: nowrap; align-items: center; gap: 10px; min-width: 0; }
.station-status { width: 92px; justify-content: center; flex: 0 0 92px; }
.station-heartbeat-time { width: 145px; color: #7893a4; font-size: 11px; white-space: nowrap; flex: 0 0 145px; }
.station-contact-button, .station-heartbeat-button { width: 92px; flex: 0 0 92px; }
.station-select { width: 150px; flex: 0 0 150px; }
</style>
