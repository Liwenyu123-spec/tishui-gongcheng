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
}

onMounted(async () => {
  chartInstance.value = echarts.init(chart.value!)
  await loadStations()
  loadSelectedStation()
})
watch(station, loadSelectedStation)
onBeforeUnmount(() => chartInstance.value?.dispose())
</script>

<template>
  <div class="page-title"><div><h2>站点趋势</h2><p>查看泵站压力、流量、水位与能耗趋势，缺数区间显式标注 · {{ sourceLabel }}</p></div><el-select v-model="station" style="width:150px"><el-option v-for="s in stationOptions" :key="s" :label="s" :value="s"/></el-select></div>
  <div class="grid grid-4"><div class="panel metric"><span class="metric-label">当前流量</span><div class="metric-value">{{flow.toLocaleString()}} <small>m³/h</small></div><span class="status-line status-ok"><i/>{{ loading ? '正在加载' : `数据正常 · ${sourceLabel}` }}</span></div><div class="panel metric"><span class="metric-label">出水压力</span><div class="metric-value">{{pressure.toFixed(2)}} <small>MPa</small></div><span class="metric-foot">后端遥测值</span></div><div class="panel metric"><span class="metric-label">水池水位</span><div class="metric-value">{{level.toFixed(2)}} <small>m</small></div><span class="metric-foot">后端遥测值</span></div><div class="panel metric"><span class="metric-label">站点状态</span><div class="metric-value">{{ detailLoading ? '加载中' : stationDetail?.status || '—' }}</div><span class="metric-foot">{{ stationDetail?.location || '站点详情接口' }}</span></div></div>
  <div class="panel" style="margin-top:18px"><div class="panel-head"><h3>24 小时运行趋势</h3><span>流量 / 压力 · {{sourceLabel}}</span></div><div ref="chart" class="chart"></div></div>
</template>
