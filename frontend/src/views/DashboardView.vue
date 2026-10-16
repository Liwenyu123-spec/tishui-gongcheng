<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../api/http'
import { alarmRows, stations } from '../mock'

interface HealthResponse {
  status: string
  service: string
  environment: string
  timestamp: string
}

const router = useRouter()
const refresh = ref('未检查')
const healthStatus = ref('检查中')
const healthLoading = ref(false)
const metrics = [['总供水量','24,860','m³/d','较昨日 +4.2%'],['当前输水压力','0.72','MPa','六站平均'],['在线泵组','18 / 20','台','2 台待检修'],['供需缺口','1,400','m³','西部片区']]

const checkHealth = async () => {
  healthLoading.value = true
  try {
    const result = await api<HealthResponse>('/api/v1/health')
    healthStatus.value = result.status === 'ok' ? '后端正常' : result.status
    refresh.value = result.timestamp.slice(11, 19)
  } catch {
    healthStatus.value = '后端不可用'
    refresh.value = '失败'
    ElMessage.warning('健康检查接口暂不可用')
  } finally {
    healthLoading.value = false
  }
}

onMounted(checkHealth)
</script>

<template>
  <div class="page-title"><div><h2>运行总览</h2><p>全链路运行状态 · 最近刷新 {{ refresh }} · 数据源：Mock · {{ healthStatus }}</p></div><el-button type="primary" plain :loading="healthLoading" @click="checkHealth">刷新数据</el-button></div>
  <div class="grid grid-4"><div v-for="m in metrics" :key="m[0]" class="panel metric"><span class="metric-label">{{m[0]}}</span><div class="metric-value">{{m[1]}} <small>{{m[2]}}</small></div><span class="metric-foot">{{m[3]}}</span></div></div>
  <div class="panel" style="margin-top:18px"><div class="panel-head"><h3>全链路健康度</h3><span>节点状态：4 正常 · 1 关注 · 1 缺数</span></div><div class="flow"><template v-for="(station,i) in ['娘子关取水','集泉一站',...stations,'渠道自流']" :key="station"><div class="flow-node" @click="router.push('/station')"><strong>{{station}}</strong><span :style="{color:i===4?'#f3b664':'#74d8b5'}">{{i===4?'关注':'运行正常'}}</span></div><span v-if="i<7" class="flow-arrow">→</span></template></div></div>
  <div class="grid grid-2" style="margin-top:18px"><div class="panel"><div class="panel-head"><h3>未确认告警</h3><el-button link type="primary" @click="router.push('/alarms')">查看全部</el-button></div><div class="table-wrap"><el-table :data="alarmRows.slice(0,2)" size="small"><el-table-column prop="level" label="级别" width="70"><template #default="s"><span :class="['tag',s.row.level==='高'?'tag-red':'tag-amber']">{{s.row.level}}</span></template></el-table-column><el-table-column prop="station" label="站点"/><el-table-column prop="metric" label="指标"/><el-table-column prop="time" label="时间" width="80"/></el-table></div></div><div class="panel"><div class="panel-head"><h3>待办事项</h3><span>需要人工确认</span></div><div class="table-wrap"><div class="warning">二泵站流量下降与西部片区压力下降可能关联</div><p class="muted" style="font-size:12px;margin:15px 0 0">建议先核查二泵站 2 号泵入口压力和渠道前段水位。</p></div></div></div>
</template>
