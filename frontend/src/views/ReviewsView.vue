<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { fetchReviewDetail, fetchReviews, updateReview } from '../api/reviews'
import { registerPageRefresh } from '../composables/pageRefresh'
import { backendSourceLabel, remoteListMessage } from '../composables/dataSource'

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
const detailVisible = ref(false)
const detailLoading = ref(false)
const selectedDetail = ref<ApiReview | null>(null)
const updatingReviewId = ref('')
const commentVisible = ref(false)
const commentSaving = ref(false)
const commentText = ref('')
const commentTarget = ref<ReviewRow | null>(null)
const pendingCount = computed(() => rows.value.filter(row => row.status === '待审核' || row.status === '待补充').length)
// 待审核和待补充记录都可以继续给出审核结论；已通过或已驳回记录保持只读。
const canReviewRow = (row: ReviewRow) => row.status === '待审核' || row.status === '待补充'

// 后端审核时间统一保存为带时区的 UTC，列表和详情统一转换为浏览器本地时间。
const formatLocalDateTime = (value: string) => {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (part: number) => String(part).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

const formatReview = (review: ApiReview): ReviewRow => ({
  id: review.id,
  title: review.subject,
  recommendation: review.recommendation,
  comment: review.comment,
  time: formatLocalDateTime(review.created_at),
  status: statusNames[review.status] || review.status,
  source: backendSourceLabel(review.source),
})

const loadReviews = async () => {
  loading.value = true
  try {
    const result = await fetchReviews<ApiReview>()
    if (result.length) {
      rows.value = result.map(formatReview)
      sourceLabel.value = backendSourceLabel(result[0].source)
    } else {
      sourceLabel.value = '接口暂无记录 · 本地示例'
      ElMessage.info(remoteListMessage('empty', '审核'))
    }
  } catch {
    sourceLabel.value = '本地示例'
    ElMessage.warning(remoteListMessage('failed', '审核接口'))
  } finally {
    loading.value = false
  }
}

// 审核结论由后端限制为通过、驳回或退回补充，页面只提交当前行的状态变化。
const updateReviewStatus = async (row: ReviewRow, status: 'approved' | 'rejected' | 'supplement', comment = '') => {
  if (row.id.startsWith('local-')) {
    ElMessage.warning('本地示例审核记录无法写入后端，请选择后端记录')
    return
  }
  updatingReviewId.value = row.id
  try {
    const result = await updateReview<ApiReview>(row.id, { status, ...(comment ? { comment } : {}) })
    Object.assign(row, formatReview(result))
    ElMessage.success(status === 'approved' ? '审核已通过' : status === 'rejected' ? '审核已驳回' : '已退回补充材料')
  } catch {
    ElMessage.error('审核状态更新失败，请刷新后重试')
  } finally {
    updatingReviewId.value = ''
  }
}

// 打开退回补充对话框，先把当前审核主题带入，避免提交意见时选错记录。
const openSupplement = (row: ReviewRow) => {
  commentTarget.value = row
  commentText.value = row.comment
  commentVisible.value = true
}

// 提交退回补充结论和审核意见，意见为空时提醒审核人补充原因。
const submitSupplement = async () => {
  if (!commentTarget.value) return
  if (!commentText.value.trim()) {
    ElMessage.warning('请填写退回补充的原因')
    return
  }
  commentSaving.value = true
  await updateReviewStatus(commentTarget.value, 'supplement', commentText.value.trim())
  commentSaving.value = false
  commentVisible.value = false
}

const viewBasis = (row: ReviewRow) => {
  ElMessage.info(row.recommendation || '暂无审核依据')
}

const viewDetail = async (row: ReviewRow) => {
  detailVisible.value = true
  if (row.id.startsWith('local-')) {
    selectedDetail.value = { id: row.id, subject: row.title, recommendation: row.recommendation, comment: row.comment, status: row.status, created_at: row.time, updated_at: row.time, source: 'local' }
    return
  }
  detailLoading.value = true
  try {
    selectedDetail.value = await fetchReviewDetail<ApiReview>(row.id)
  } catch {
    selectedDetail.value = null
    ElMessage.warning('审核详情接口暂不可用')
  } finally {
    detailLoading.value = false
  }
}

registerPageRefresh(loadReviews)
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
        <el-table-column prop="time" label="提交时间" width="180" />
        <el-table-column prop="source" label="数据来源" width="120" />
        <el-table-column prop="status" label="状态" width="100" />
        <el-table-column label="操作" width="330">
          <template #default="s">
            <el-button link type="primary" @click="viewDetail(s.row as ReviewRow)">详情</el-button>
            <el-button link type="primary" @click="viewBasis(s.row as ReviewRow)">查看依据</el-button>
            <el-button class="button-stable button-stable--xs" link type="success" :disabled="!canReviewRow(s.row as ReviewRow)" :loading="updatingReviewId===s.row.id" @click="updateReviewStatus(s.row as ReviewRow, 'approved')">通过</el-button>
            <el-button class="button-stable button-stable--xs" link type="danger" :disabled="!canReviewRow(s.row as ReviewRow)" :loading="updatingReviewId===s.row.id" @click="updateReviewStatus(s.row as ReviewRow, 'rejected')">驳回</el-button>
            <el-button class="button-stable button-stable--sm" link type="warning" :disabled="s.row.status!=='待审核'" :loading="updatingReviewId===s.row.id" @click="openSupplement(s.row as ReviewRow)">退回补充</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>

  <el-dialog v-model="detailVisible" title="审核详情" width="560px">
    <div v-loading="detailLoading" v-if="selectedDetail">
      <p><strong>{{ selectedDetail.subject }}</strong></p>
      <p>状态：{{ statusNames[selectedDetail.status] || selectedDetail.status }}</p>
      <p>创建时间：{{ formatLocalDateTime(selectedDetail.created_at) }}</p>
      <p>更新时间：{{ formatLocalDateTime(selectedDetail.updated_at) }}</p>
      <p>建议结论：{{ selectedDetail.recommendation }}</p>
      <p>补充说明：{{ selectedDetail.comment || '暂无' }}</p>
      <p class="muted">记录编号：{{ selectedDetail.id }}</p>
    </div>
    <el-empty v-else description="正在加载审核详情" />
  </el-dialog>

  <el-dialog v-model="commentVisible" title="退回补充材料" width="520px">
    <p class="muted">审核主题：{{ commentTarget?.title || '—' }}</p>
    <el-input v-model="commentText" type="textarea" :rows="5" placeholder="请说明需要补充的数据、依据或风险说明" />
    <template #footer>
      <el-button @click="commentVisible = false">取消</el-button>
      <el-button class="button-stable button-stable--md" type="warning" :loading="commentSaving" @click="submitSupplement">确认退回</el-button>
    </template>
  </el-dialog>
</template>
