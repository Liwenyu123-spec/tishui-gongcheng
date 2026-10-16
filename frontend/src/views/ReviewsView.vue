<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/http'

interface ApiReview {
  id: string
  subject: string
  recommendation: string
  comment: string
  status: string
  created_at: string
  updated_at: string
  source: string
}

interface ReviewRow {
  id: string
  title: string
  recommendation: string
  comment: string
  time: string
  status: string
  source: string
}

const localReviews: ReviewRow[] = [
  { id: 'local-1', title: '二泵站流量下降核查建议', recommendation: '建议优先核查二泵站出水流量和进水阀状态。', comment: '', time: '10:45', status: '待审核', source: '本地示例' },
  { id: 'local-2', title: '西部片区供需平衡方案 A', recommendation: '建议优先复核方案 A 的供水能力和风险边界。', comment: '', time: '09:30', status: '待补充', source: '本地示例' },
]
const statusNames: Record<string, string> = {
  pending: '待审核',
  approved: '已通过',
  rejected: '已驳回',
  supplement: '待补充',
}
const rows = ref<ReviewRow[]>(localReviews.map(row => ({ ...row })))
const loading = ref(false)
const sourceLabel = ref('本地示例')
const pendingCount = computed(() => rows.value.filter(row => row.status === '待审核' || row.status === '待补充').length)

const formatReview = (review: ApiReview): ReviewRow => ({
  id: review.id,
  title: review.subject,
  recommendation: review.recommendation,
  comment: review.comment,
  time: review.created_at.slice(11, 16),
  status: statusNames[review.status] || review.status,
  source: review.source === 'mock' ? '后端 Mock' : review.source,
})

const loadReviews = async () => {
  loading.value = true
  try {
    const result = await api<ApiReview[]>('/api/v1/reviews')
    if (result.length) {
      rows.value = result.map(formatReview)
      sourceLabel.value = result[0].source === 'mock' ? '后端 Mock 数据' : result[0].source
    } else {
      sourceLabel.value = '接口暂无记录 · 本地示例'
      ElMessage.info('审核接口当前没有记录，页面暂显示本地示例')
    }
  } catch {
    sourceLabel.value = '本地示例'
    ElMessage.warning('审核接口暂不可用，当前显示本地示例')
  } finally {
    loading.value = false
  }
}

const updateLocalStatus = (row: ReviewRow, status: string) => {
  row.status = status
  ElMessage.info('当前仅更新页面显示，审核状态接口将在后续阶段接入')
}

const viewBasis = (row: ReviewRow) => {
  ElMessage.info(row.recommendation || '暂无审核依据')
}

onMounted(loadReviews)
</script>

<template>
  <div class="page-title">
    <div>
      <h2>建议审核</h2>
      <p>审批只改变业务状态并写入审计记录，不触发设备控制 · {{ sourceLabel }}</p>
    </div>
    <span class="tag tag-amber">{{ loading ? '正在加载' : `待审核 ${pendingCount}` }}</span>
  </div>

  <div class="panel">
    <div class="table-wrap">
      <el-table :data="rows">
        <el-table-column prop="title" label="审核主题" min-width="210" />
        <el-table-column prop="recommendation" label="建议结论" min-width="300" />
        <el-table-column prop="time" label="提交时间" width="100" />
        <el-table-column prop="source" label="数据来源" width="120" />
        <el-table-column prop="status" label="状态" width="100" />
        <el-table-column label="操作" width="190">
          <template #default="s">
            <el-button link type="primary" @click="viewBasis(s.row)">查看依据</el-button>
            <el-button link type="success" @click="updateLocalStatus(s.row, '已通过')">通过</el-button>
            <el-button link type="danger" @click="updateLocalStatus(s.row, '已驳回')">驳回</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>
