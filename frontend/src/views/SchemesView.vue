<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/http'

interface Scheme {
  scheme_id: string
  name: string
  supply: number
  delay_minutes: number
  energy: number
  load_percent: number
  risk: string
  supply_gap: number
  feasible: boolean
  constraint_violations: string[]
  score: number
  calculation_basis: string[]
}

interface SchemeCompareResponse {
  comparison_id: string
  results: Scheme[]
  recommendation: string
  recommended_scheme_id: string | null
  target_demand: number
  constraints: { max_delay_minutes: number; max_load_percent: number; max_risk: string }
  assumptions: string[]
  source: string
}

interface ReviewResponse {
  id: string
  subject: string
  recommendation: string
  status: string
}

const mockSchemes: Scheme[] = [
  { scheme_id: 'scheme-a', name: '方案 A · 保守供水', supply: 12000, delay_minutes: 45, energy: 820, risk: 'low' },
  { scheme_id: 'scheme-b', name: '方案 B · 均衡调度', supply: 13400, delay_minutes: 52, energy: 910, risk: 'medium' },
  { scheme_id: 'scheme-c', name: '方案 C · 峰时补水', supply: 14100, delay_minutes: 38, energy: 1080, risk: 'high' },
]
const riskNames: Record<string, string> = { high: '高', medium: '中', low: '低' }
const schemes = ref<Scheme[]>(mockSchemes.map(scheme => ({ ...scheme })))
const selectedSchemeId = ref('')
const recommendation = ref('当前显示本地 Mock 数据')
const loading = ref(false)
const submitting = ref(false)
const sourceLabel = ref('本地 Mock 数据')
const submittedReview = ref<ReviewResponse | null>(null)
const comparisonMeta = ref<Pick<SchemeCompareResponse, 'target_demand' | 'constraints' | 'assumptions' | 'recommended_scheme_id'> | null>(null)

const loadComparison = async () => {
  loading.value = true
  try {
    const result = await api<SchemeCompareResponse>('/api/v1/schemes/compare', {
      method: 'POST',
      body: JSON.stringify({ schemes: mockSchemes }),
    })
    schemes.value = result.results
    recommendation.value = result.recommendation
    comparisonMeta.value = result
    sourceLabel.value = result.source === 'mock' ? '后端 Mock 数据' : result.source
  } catch {
    sourceLabel.value = '本地 Mock 数据'
    ElMessage.warning('方案比较接口暂不可用，当前显示本地 Mock 数据')
  } finally {
    loading.value = false
  }
}

const submitForReview = async () => {
  const scheme = schemes.value.find(item => item.scheme_id === selectedSchemeId.value)
  if (!scheme) {
    ElMessage.warning('请先选择一套方案')
    return
  }
  submitting.value = true
  try {
    submittedReview.value = await api<ReviewResponse>('/api/v1/reviews', {
      method: 'POST',
      body: JSON.stringify({
        subject: scheme.name,
        recommendation: `建议人工复核${scheme.name}：供水量 ${scheme.supply.toLocaleString()} m³/d，供需差额 ${scheme.supply_gap.toLocaleString()} m³/d，时延 ${scheme.delay_minutes} min，能耗 ${scheme.energy.toLocaleString()} kWh，负荷 ${scheme.load_percent}%。${scheme.feasible ? '当前满足 Mock 约束。' : `当前约束问题：${scheme.constraint_violations.join('；')}`}`,
        comment: `方案比较结论：${recommendation.value}`,
      }),
    })
    ElMessage.success('方案已提交人工复核')
  } catch {
    ElMessage.error('提交审核失败，请检查审核接口')
  } finally {
    submitting.value = false
  }
}

onMounted(loadComparison)
</script>

<template>
  <div class="page-title">
    <div>
      <h2>智能调度方案比较</h2>
      <p>对比方案草稿，提交人工复核；不下发控制 · {{ sourceLabel }}</p>
    </div>
    <el-button class="button-stable button-stable--xl" type="primary" :loading="submitting" :disabled="!selectedSchemeId" @click="submitForReview">提交人工复核</el-button>
  </div>

  <div class="grid grid-3">
    <div v-for="s in schemes" :key="s.scheme_id" class="panel metric">
      <span class="metric-label">{{ s.name }}</span>
      <div class="metric-value">{{ s.supply.toLocaleString() }} <small>m³/d</small></div>
      <div class="kpi-row">
        <div>时延<strong>{{ s.delay_minutes }} min</strong></div>
        <div>能耗<strong>{{ s.energy.toLocaleString() }} kWh</strong></div>
        <div>负荷<strong>{{ s.load_percent }}%</strong></div>
      </div>
      <p class="muted" style="font-size:11px;margin:15px 0">供需差额：{{ s.supply_gap.toLocaleString() }} m³/d · 风险等级：{{ riskNames[s.risk] || s.risk }} · 评分：{{ s.score }}</p>
      <p :class="['status-line', s.feasible ? 'status-ok' : 'status-warn']"><i />{{ s.feasible ? '满足当前 Mock 约束' : `存在约束问题：${s.constraint_violations.join('；')}` }}</p>
      <el-radio v-model="selectedSchemeId" :label="s.scheme_id">选择方案</el-radio>
    </div>
  </div>

  <div class="panel" style="margin-top:18px">
    <div class="panel-head">
      <h3>比较结论</h3>
      <span>{{ loading ? '正在加载 · ' : '' }}{{ sourceLabel }}</span>
    </div>
    <p>{{ recommendation }}</p>
    <p v-if="comparisonMeta" class="muted" style="font-size:12px">目标需求：{{ comparisonMeta.target_demand.toLocaleString() }} m³/d · 最大时延：{{ comparisonMeta.constraints.max_delay_minutes }} min · 最大负荷：{{ comparisonMeta.constraints.max_load_percent }}% · 最大风险：{{ riskNames[comparisonMeta.constraints.max_risk] || comparisonMeta.constraints.max_risk }}</p>
    <ul v-if="comparisonMeta?.assumptions?.length" class="muted" style="font-size:12px"><li v-for="item in comparisonMeta.assumptions" :key="item">{{ item }}</li></ul>
    <p v-if="submittedReview" class="status-line status-ok"><i />已创建审核记录：{{ submittedReview.id }}</p>
    <p class="muted" style="font-size:12px">比较结果可选择一套方案提交人工复核，审核只改变业务状态，不触发设备控制。</p>
  </div>

  <div class="warning" style="margin-top:18px">所有方案均为分析草稿，数据和假设需由业务人员确认后才能进入审批。</div>
</template>
