<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/http'

interface TopologyNode {
  station_id: string
  name: string
  sequence: number
}

const selectedId = ref('pump-02')
const loading = ref(false)
const nodes = ref<TopologyNode[]>([
  { station_id: 'jq-01', name: '集泉一站', sequence: 1 },
  { station_id: 'pump-01', name: '一泵站', sequence: 2 },
  { station_id: 'pump-02', name: '二泵站', sequence: 3 },
  { station_id: 'pump-03', name: '三泵站', sequence: 4 },
  { station_id: 'pump-04', name: '四泵站', sequence: 5 },
  { station_id: 'pingding-inlet', name: '平定侧入口', sequence: 6 },
])
const selectedNode = computed(() => nodes.value.find(node => node.station_id === selectedId.value) || nodes.value[0])

onMounted(async () => {
  loading.value = true
  try {
    const result = await api<{ nodes: TopologyNode[] }>('/api/v1/topology')
    nodes.value = result.nodes
    if (!nodes.value.some(node => node.station_id === selectedId.value)) {
      selectedId.value = nodes.value[0]?.station_id || ''
    }
  } catch {
    ElMessage.warning('拓扑接口暂不可用，当前显示本地 Mock 数据')
  } finally {
    loading.value = false
  }
})
</script>
<template><div class="page-title"><div><h2>工程拓扑</h2><p>按确认拓扑展示供水链路上下游关系 · 点击节点查看运行状态</p></div><span class="tag tag-green">{{ loading ? '正在加载' : `链路在线 ${nodes.length} / ${nodes.length}` }}</span></div><div class="grid grid-2"><div class="panel"><div class="panel-head"><h3>供水链路</h3><span>简化示意 · 非 GIS 地图</span></div><div class="flow" style="display:grid;grid-template-columns:repeat(4,1fr);gap:22px;padding:30px 22px"><div v-for="(node,i) in nodes" :key="node.station_id" :class="['flow-node', {selected:node.station_id===selectedId}]" @click="selectedId=node.station_id"><strong>{{node.name}}</strong><span :style="{color:node.station_id==='pump-02'?'#f3b664':'#74d8b5'}">{{node.station_id==='pump-02'?'告警':'正常'}}</span></div></div></div><div class="panel"><div class="panel-head"><h3>{{selectedNode?.name || '节点'}} · 节点详情</h3><span class="tag tag-green">数据正常</span></div><div class="table-wrap"><div class="grid grid-2"><div class="metric"><span class="metric-label">进水流量</span><div class="metric-value">1,086 <small>m³/h</small></div></div><div class="metric"><span class="metric-label">出水压力</span><div class="metric-value">0.74 <small>MPa</small></div></div><div class="metric"><span class="metric-label">水位</span><div class="metric-value">3.68 <small>m</small></div></div><div class="metric"><span class="metric-label">更新时间</span><div class="metric-value" style="font-size:18px">10:48</div></div></div><div class="warning" style="margin-top:10px">质量状态：正常 · 来源：后端 Mock · 仅供测试演示</div></div></div></div></template>
