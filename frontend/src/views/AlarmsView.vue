<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/http'
import { alarmRows } from '../mock'

interface ApiAlarm {
  id: string
  station_id: string
  station_name: string
  level: string
  metric: string
  value: number
  unit: string
  threshold: string
  status: string
  occurred_at: string
  relation?: string | null
}

interface ApiAlarmDetail extends ApiAlarm {
  description: string
  suggested_action: string
}

interface AlarmRow {
  id: string
  level: string
  station: string
  stationId: string
  metric: string
  value: string
  threshold: string
  time: string
  status: string
  relation: string
}

const rows = ref<AlarmRow[]>([...alarmRows.map((row, index) => ({ ...row, id: `mock-${index}`, stationId: row.station }))])
const stationFilter = ref('')
const levelFilter = ref('')
const loading = ref(false)
const detailLoading = ref(false)
const detailVisible = ref(false)
const selectedDetail = ref<ApiAlarmDetail | null>(null)
const levelName: Record<string, string> = { high: '高', medium: '中', low: '低' }
const metricName: Record<string, string> = { flow: '出水流量', current: '2号泵电流', level: '水位' }
const stationOptions = computed(() => [...new Set(rows.value.map(row => row.station))])
const filteredRows = computed(() => rows.value.filter(row => (!stationFilter.value || row.station === stationFilter.value) && (!levelFilter.value || row.level === levelFilter.value)))
const unconfirmedCount = computed(() => rows.value.filter(row => row.status === '未确认').length)

onMounted(async () => {
  loading.value = true
  try {
    const result = await api<ApiAlarm[]>('/api/v1/alarms')
    rows.value = result.map(row => ({
      id: row.id,
      level: levelName[row.level] || row.level,
      station: row.station_name,
      stationId: row.station_id,
      metric: metricName[row.metric] || row.metric,
      value: `${row.value} ${row.unit}`,
      threshold: row.threshold,
      time: row.occurred_at.slice(11, 16),
      status: row.status === 'confirmed' ? '已确认' : '未确认',
      relation: row.relation || '',
    }))
  } catch {
    ElMessage.warning('告警接口暂不可用，当前显示本地 Mock 数据')
  } finally {
    loading.value = false
  }
})

const ack = (row: { status: string }) => { row.status = '已确认' }

const openDetail = async (row: AlarmRow) => {
  detailVisible.value = true
  detailLoading.value = true
  try {
    selectedDetail.value = await api<ApiAlarmDetail>(`/api/v1/alarms/${row.id}`)
  } catch {
    selectedDetail.value = null
    ElMessage.warning('告警详情接口暂不可用')
  } finally {
    detailLoading.value = false
  }
}

const resetFilters = () => { stationFilter.value = ''; levelFilter.value = '' }
</script>

<template>
  <div class="page-title"><div><h2>告警中心</h2><p>集中查看、筛选、确认告警；确认不等于控制设备</p></div><span class="tag tag-red">{{ loading ? '正在加载' : `未确认 ${unconfirmedCount}` }}</span></div>
  <div class="panel"><div class="panel-head"><div class="filterbar"><el-select v-model="stationFilter" placeholder="全部站点" size="small" clearable style="width:130px"><el-option v-for="station in stationOptions" :key="station" :label="station" :value="station"/></el-select><el-select v-model="levelFilter" placeholder="全部级别" size="small" clearable style="width:120px"><el-option label="高" value="高"/><el-option label="中" value="中"/><el-option label="低" value="低"/></el-select><el-button size="small" @click="resetFilters">重置</el-button></div></div><div class="table-wrap"><el-table :data="filteredRows" stripe><el-table-column prop="level" label="级别" width="70"><template #default="s"><span :class="['tag',s.row.level==='高'?'tag-red':s.row.level==='中'?'tag-amber':'tag-gray']">{{s.row.level}}</span></template></el-table-column><el-table-column prop="station" label="站点"/><el-table-column prop="metric" label="指标"/><el-table-column prop="value" label="当前值"/><el-table-column prop="threshold" label="阈值"/><el-table-column prop="time" label="最近时间"/><el-table-column prop="status" label="处理状态"><template #default="s"><span :class="['tag',s.row.status==='已确认'?'tag-green':'tag-red']">{{s.row.status}}</span></template></el-table-column><el-table-column label="操作" width="180"><template #default="s"><el-button link type="primary" @click="openDetail(s.row)">查看详情</el-button><el-button link type="primary" @click="ack(s.row)">确认</el-button></template></el-table-column></el-table></div></div>
  <el-dialog v-model="detailVisible" title="告警详情" width="560px">
    <div v-loading="detailLoading" v-if="selectedDetail">
      <p><strong>{{ selectedDetail.station_name }}</strong> · {{ metricName[selectedDetail.metric] || selectedDetail.metric }}</p>
      <p>当前值：{{ selectedDetail.value }} {{ selectedDetail.unit }} · 阈值：{{ selectedDetail.threshold }}</p>
      <p>发生时间：{{ selectedDetail.occurred_at }}</p>
      <p>{{ selectedDetail.description }}</p>
      <p>建议动作：{{ selectedDetail.suggested_action }}</p>
      <p v-if="selectedDetail.relation" class="muted">关联：{{ selectedDetail.relation }}</p>
    </div>
    <el-empty v-else description="正在加载告警详情" />
  </el-dialog>
</template>
