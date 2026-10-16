<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/http'
import { areas as mockAreas } from '../mock'

interface ApiSupplyArea {
  area: string
  station_id: string
  supply: number
  demand: number
  balance: number
  unit: string
  pressure: number
  risk: string
  source: string
}

interface SupplyAreaRow {
  name: string
  station: string
  supply: number
  demand: number
  balance: number
  pressure: number
  risk: string
}

interface SupplyBalanceResponse {
  areas: ApiSupplyArea[]
  total_supply: number
  total_demand: number
  total_balance: number
  bottleneck_summary: string
  source: string
}

const stationNames: Record<string, string> = {
  'pump-02': '二泵站',
  'pump-03': '三泵站',
  'pump-04': '四泵站',
}
const riskNames: Record<string, string> = { high: '高', medium: '中', low: '低' }

const displayAreas = ref<SupplyAreaRow[]>(mockAreas.map(area => ({
  name: area.name,
  station: area.station,
  supply: area.supply,
  demand: area.demand,
  balance: area.supply - area.demand,
  pressure: area.pressure,
  risk: area.risk,
})))
const totalSupply = ref(displayAreas.value.reduce((sum, area) => sum + area.supply, 0))
const totalDemand = ref(displayAreas.value.reduce((sum, area) => sum + area.demand, 0))
const bottleneckSummary = ref('当前显示本地 Mock 数据')
const loading = ref(false)
const sourceLabel = ref('本地 Mock 数据')
const totalBalance = computed(() => totalSupply.value - totalDemand.value)

const loadSupplyBalance = async () => {
  loading.value = true
  try {
    const result = await api<SupplyBalanceResponse>('/api/v1/supply/balance')
    displayAreas.value = result.areas.map(area => ({
      name: area.area,
      station: stationNames[area.station_id] || area.station_id,
      supply: area.supply,
      demand: area.demand,
      balance: area.balance,
      pressure: area.pressure,
      risk: riskNames[area.risk] || area.risk,
    }))
    totalSupply.value = result.total_supply
    totalDemand.value = result.total_demand
    bottleneckSummary.value = result.bottleneck_summary
    sourceLabel.value = result.source === 'mock' ? '后端 Mock 数据' : result.source
  } catch {
    sourceLabel.value = '本地 Mock 数据'
    ElMessage.warning('供需接口暂不可用，当前显示本地 Mock 数据')
  } finally {
    loading.value = false
  }
}

onMounted(loadSupplyBalance)
</script>

<template>
  <div class="page-title">
    <div>
      <h2>片区供需平衡</h2>
      <p>平定侧供水片区供需、压力和供需差额 · {{ sourceLabel }}</p>
    </div>
    <span class="tag tag-amber">结论仅供参考</span>
  </div>

  <div class="grid grid-3">
    <div v-for="a in displayAreas" :key="a.name" class="panel metric">
      <span class="metric-label">{{ a.name }} · {{ a.station }}</span>
      <div class="metric-value">{{ a.supply.toLocaleString() }} <small>m³/d</small></div>
      <div class="kpi-row">
        <div>需求<strong>{{ a.demand.toLocaleString() }}</strong></div>
        <div>压力<strong>{{ a.pressure.toFixed(2) }} MPa</strong></div>
        <div>差额<strong>{{ a.balance.toLocaleString() }} m³/d</strong></div>
      </div>
      <div class="status-line" style="margin-top:15px">
        <i :style="{ background: a.risk === '高' ? '#f37878' : a.risk === '中' ? '#f3b664' : '#43d7a0' }" />
        风险：{{ a.risk }}
      </div>
    </div>
  </div>

  <div class="panel" style="margin-top:18px">
    <div class="panel-head">
      <h3>供水与需求对比</h3>
      <span>{{ loading ? '正在加载 · ' : '' }}总供需差额：{{ totalBalance.toLocaleString() }} m³/d</span>
    </div>
    <p class="metric-foot" style="margin:0 0 14px">{{ bottleneckSummary }}</p>
    <div class="table-wrap">
      <el-table :data="displayAreas">
        <el-table-column prop="name" label="片区" />
        <el-table-column prop="station" label="对应泵站" />
        <el-table-column prop="supply" label="供水量" />
        <el-table-column prop="demand" label="需求量" />
        <el-table-column prop="balance" label="供需差额" />
        <el-table-column prop="risk" label="风险等级" />
      </el-table>
    </div>
  </div>
</template>
