<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/http'

interface TopologyNode {
  station_id: string
  name: string
  sequence: number
}

interface TopologyEdge {
  source: string
  target: string
  direction: string
}

interface StationDetail {
  id: string
  name: string
  sequence: number
  station_type: string
  status: string
  location: string
  description: string
  metrics: string[]
  source: string
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

const selectedId = ref('pump-02')
const loading = ref(false)
const detailLoading = ref(false)
const sourceLabel = ref('本地 Mock 数据')
const nodes = ref<TopologyNode[]>([
  { station_id: 'jq-01', name: '集泉一站', sequence: 1 },
  { station_id: 'pump-01', name: '一泵站', sequence: 2 },
  { station_id: 'pump-02', name: '二泵站', sequence: 3 },
  { station_id: 'pump-03', name: '三泵站', sequence: 4 },
  { station_id: 'pump-04', name: '四泵站', sequence: 5 },
  { station_id: 'pingding-inlet', name: '平定侧入口', sequence: 6 },
])
const edges = ref<TopologyEdge[]>([])
const stationDetail = ref<StationDetail | null>(null)
const telemetryPoints = ref<TelemetryPoint[]>([])
const selectedNode = computed(() => nodes.value.find(node => node.station_id === selectedId.value) || nodes.value[0])
const flow = computed(() => telemetryPoints.value.find(point => point.metric === 'flow')?.value)
const pressure = computed(() => telemetryPoints.value.find(point => point.metric === 'pressure')?.value)
const level = computed(() => telemetryPoints.value.find(point => point.metric === 'level')?.value)
const updatedAt = computed(() => telemetryPoints.value[0]?.observed_at ? telemetryPoints.value[0].observed_at.slice(11, 16) : '—')

const loadSelected = async () => {
  if (!selectedId.value) return
  detailLoading.value = true
  const detailTask = api<StationDetail>(`/api/v1/stations/${selectedId.value}`)
  const telemetryTask = api<TelemetryPoint[]>(`/api/v1/stations/${selectedId.value}/telemetry`)
  const [detailResult, telemetryResult] = await Promise.allSettled([detailTask, telemetryTask])
  if (detailResult.status === 'fulfilled') stationDetail.value = detailResult.value
  else stationDetail.value = null
  if (telemetryResult.status === 'fulfilled') {
    telemetryPoints.value = telemetryResult.value
    sourceLabel.value = '后端 Mock 数据'
  } else {
    telemetryPoints.value = []
    sourceLabel.value = '本地数据不可用'
    ElMessage.warning('站点详情或遥测接口暂不可用')
  }
  detailLoading.value = false
}

const loadTopology = async () => {
  loading.value = true
  try {
    const result = await api<{ nodes: TopologyNode[]; edges: TopologyEdge[] }>('/api/v1/topology')
    nodes.value = result.nodes
    edges.value = result.edges
    if (!nodes.value.some(node => node.station_id === selectedId.value)) selectedId.value = nodes.value[0]?.station_id || ''
    sourceLabel.value = '后端 Mock 数据'
    await loadSelected()
  } catch {
    sourceLabel.value = '本地 Mock 数据'
    ElMessage.warning('拓扑接口暂不可用，当前显示本地节点')
  } finally {
    loading.value = false
  }
}

const selectNode = (id: string) => {
  selectedId.value = id
  loadSelected()
}

const statusName: Record<string, string> = { running: '运行正常', attention: '关注', offline: '离线' }

onMounted(loadTopology)
</script>

<template>
  <div class="page-title"><div><h2>工程拓扑</h2><p>按确认拓扑展示供水链路上下游关系 · {{ sourceLabel }}</p></div><span class="tag tag-green">{{ loading ? '正在加载' : `链路在线 ${nodes.length} / ${nodes.length}` }}</span></div>
  <div class="grid grid-2">
    <div class="panel">
      <div class="panel-head"><h3>供水链路</h3><span>简化示意 · 非 GIS 地图 · {{ edges.length }} 段连接</span></div>
      <div class="flow" style="display:grid;grid-template-columns:repeat(3,1fr);gap:22px;padding:30px 22px">
        <div v-for="node in nodes" :key="node.station_id" :class="['flow-node', {selected:node.station_id===selectedId}]" @click="selectNode(node.station_id)">
          <strong>{{node.name}}</strong>
          <span>{{ node.sequence }}</span>
        </div>
      </div>
      <div class="muted" style="padding:0 22px 18px">{{ nodes.map(node => node.name).join(' → ') }}</div>
    </div>
    <div class="panel">
      <div class="panel-head">
        <h3>{{selectedNode?.name || '节点'}} · 节点详情</h3>
        <span class="tag tag-green">{{ detailLoading ? '加载中' : statusName[stationDetail?.status || ''] || stationDetail?.status || '—' }}</span>
      </div>
      <div class="table-wrap">
        <div class="grid grid-2">
          <div class="metric"><span class="metric-label">流量</span><div class="metric-value">{{ flow ?? '—' }} <small>{{ telemetryPoints.find(point => point.metric==='flow')?.unit || '' }}</small></div></div>
          <div class="metric"><span class="metric-label">压力</span><div class="metric-value">{{ pressure ?? '—' }} <small>{{ telemetryPoints.find(point => point.metric==='pressure')?.unit || '' }}</small></div></div>
          <div class="metric"><span class="metric-label">水位</span><div class="metric-value">{{ level ?? '—' }} <small>{{ telemetryPoints.find(point => point.metric==='level')?.unit || '' }}</small></div></div>
          <div class="metric"><span class="metric-label">更新时间</span><div class="metric-value" style="font-size:18px">{{updatedAt}}</div></div>
        </div>
        <p>{{ stationDetail?.description || '当前没有可用站点详情' }}</p>
        <div class="warning" style="margin-top:10px">位置：{{ stationDetail?.location || '—' }} · 来源：{{ sourceLabel }}</div>
      </div>
    </div>
  </div>
</template>
