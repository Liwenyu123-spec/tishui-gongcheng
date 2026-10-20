<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/http'

interface WorkOrderDraft {
  id: string
  title: string
  station_id: string | null
  issue: string
  suggested_action: string
  priority: string
  owner: string | null
  due_at: string | null
  status: string
  created_at: string
  source: string
}

interface AgentStation {
  id: string
  name: string
  status: string
}

interface AgentCitation {
  source_type: string
  source_id: string
  title: string
  detail: string
}

interface AgentAnswer {
  request_id: string
  intent: string
  answer: string
  facts: string[]
  recommendations: string[]
  citations: AgentCitation[]
  source: string
  generated_at: string
  data_quality?: 'mock' | 'partial' | 'live' | 'stale'
  limitations?: string[]
  confidence?: 'low' | 'medium' | 'high'
  pending_items?: string[]
  time_range?: string
  observed_at?: string | null
  freshness?: 'fresh' | 'stale' | 'unknown'
  work_order_suggestion?: {
    station_id: string
    title: string
    issue: string
    suggested_action: string
    priority: 'low' | 'medium' | 'high'
  } | null
}

interface AgentMessage {
  id: string
  role: 'user' | 'ai'
  text: string
  evidence?: string
  steps?: string[]
  pending?: boolean
}

const input = ref('')
const messages = ref<AgentMessage[]>([
  {
    id: 'welcome',
    role: 'ai',
    text: '您好，我是调度辅助 Agent。当前使用规则驱动的 Mock 数据，只提供只读分析和建议草稿。请描述您要查询的运行问题。',
    evidence: '当前模式：rule-mock · 不调用大模型 · 不生成现场控制指令',
  },
])
const agentLoading = ref(false)
let agentAbortController: AbortController | null = null
const reviewId = ref('')
// 保存最近一次完整的 Agent 答案，工单草稿会从其中读取结构化诊断建议。
const latestAgentAnswer = ref<AgentAnswer | null>(null)
// 只有诊断答案带有结构化建议时，页面才显示生成工单入口。
const canCreateWorkOrder = computed(() => Boolean(latestAgentAnswer.value?.work_order_suggestion))
// 只有管理员和值班调度员可以创建待人工审核记录，审批负责人负责后续处理。
const currentUserRole = (() => {
  try {
    return (JSON.parse(localStorage.getItem('current_user') || '{}') as { role?: string }).role || ''
  } catch {
    return ''
  }
})()
const canTransferToReview = computed(() =>
  ['admin', 'operator'].includes(currentUserRole) && Boolean(latestAgentAnswer.value?.pending_items?.length) && !reviewId.value,
)
const stations = ref<AgentStation[]>([])
const selectedStationId = ref('')
const workOrder = ref<WorkOrderDraft | null>(null)
const workOrderLoading = ref(false)
const reviewLoading = ref(false)
const workOrders = ref<WorkOrderDraft[]>([])
const workOrderListLoading = ref(false)
const workOrderStatusLoading = ref<string | null>(null)
const assignmentVisible = ref(false)
const assignmentSaving = ref(false)
const assignmentOrder = ref<WorkOrderDraft | null>(null)
const assignmentForm = ref({ owner: '', due_at: '' })
const workOrderStatusNames: Record<string, string> = { draft: '草稿', assigned: '已分派', in_progress: '处理中', completed: '已完成', cancelled: '已取消' }
const confidenceNames: Record<string, string> = { low: '低', medium: '中', high: '高' }
const freshnessNames: Record<string, string> = { fresh: '新鲜', stale: '已过期', unknown: '未知' }

// 加载当前账号可见的工单，站点范围由后端再次校验。
const loadWorkOrders = async () => {
  workOrderListLoading.value = true
  try {
    workOrders.value = await api<WorkOrderDraft[]>('/api/v1/work-orders')
  } catch {
    ElMessage.warning('工单列表接口暂不可用')
  } finally {
    workOrderListLoading.value = false
  }
}
// 加载当前账号可见站点，后端会再次校验站点范围，前端选择只用于提供查询上下文。
const loadStations = async () => {
  try {
    stations.value = await api<AgentStation[]>('/api/v1/stations')
  } catch {
    ElMessage.warning('站点列表接口暂不可用，Agent 将按问题内容识别站点')
  }
}
const ask = async (q = input.value) => {
  const question = q.trim()
  // 正在请求时不允许重复提交，避免多个 SSE 流同时修改同一段对话。
  if (!question || agentLoading.value) return
  const token = localStorage.getItem('access_token')
  if (!token) {
    ElMessage.warning('请先登录后再使用 Agent 问答')
    return
  }

  const userMessage: AgentMessage = { id: `user-${Date.now()}`, role: 'user', text: question }
  const aiMessage = reactive<AgentMessage>({
    id: `ai-${Date.now()}`,
    role: 'ai',
    text: '正在读取 Mock 数据并进行规则分析…',
    pending: true,
  })
  messages.value.push(userMessage, aiMessage)
  input.value = ''
  // 新问题开始后清空旧答案，避免在新请求期间误用上一条诊断建议生成工单。
  latestAgentAnswer.value = null
  reviewId.value = ''
  // 清空当前预览；已生成的历史工单仍保留在下面的工单列表中。
  workOrder.value = null
  agentLoading.value = true
  agentAbortController = new AbortController()

  const handleEvent = (rawEvent: string) => {
    const lines = rawEvent.split(/\r?\n/)
    const eventName = lines.find(line => line.startsWith('event:'))?.slice(6).trim() || 'message'
    const data = lines.filter(line => line.startsWith('data:')).map(line => line.slice(5).trim()).join('\n')
    if (!data) return
    if (eventName === 'start') {
      aiMessage.text = '已定位问题，正在整理事实和引用依据…'
      return
    }
    if (eventName === 'tool') {
      const tool = JSON.parse(data) as { label?: string; summary?: string; status?: string }
      if (tool.label && tool.status === 'completed') {
        const step = tool.summary ? `${tool.label}：${tool.summary}` : tool.label
        aiMessage.steps = [...(aiMessage.steps || []), step]
        aiMessage.evidence = `分析步骤：${aiMessage.steps.join(' → ')}`
      }
      return
    }
    if (eventName !== 'result') return
    const answer = JSON.parse(data) as AgentAnswer
    latestAgentAnswer.value = answer
    const evidence = [
      ...(aiMessage.steps?.length ? [`分析步骤：${aiMessage.steps.join(' → ')}`] : []),
      ...answer.facts.map(fact => `事实：${fact}`),
      ...answer.recommendations.map(item => `建议：${item}`),
      ...answer.citations.filter(citation => ['telemetry', 'alarm', 'supply', 'incident', 'notification'].includes(citation.source_type)).map(citation => `数据引用：${citation.title} · ${citation.detail}`),
      ...answer.citations.filter(citation => ['knowledge', 'policy'].includes(citation.source_type)).map(citation => `规程引用：${citation.title} · ${citation.detail}`),
      `数据质量：${answer.data_quality || 'mock'}`,
      ...(answer.limitations || []).map(item => `限制：${item}`),
      `置信度：${confidenceNames[answer.confidence || 'medium'] || answer.confidence || '中'}`,
      ...(answer.pending_items || []).map(item => `待确认项：${item}`),
      `时间范围：${answer.time_range || '当前 Mock 样本'}`,
      ...(answer.observed_at ? [`数据观测时间：${formatLocalDateTime(answer.observed_at)}`] : []),
      `数据新鲜度：${freshnessNames[answer.freshness || 'unknown'] || answer.freshness || '未知'}`,
      `来源：${answer.source} · 意图：${answer.intent}`,
    ].join('\n')
    aiMessage.text = answer.answer
    aiMessage.evidence = evidence
    aiMessage.pending = false
  }

  try {
    const response = await fetch('/api/v1/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ message: question, station_id: selectedStationId.value || null }),
      signal: agentAbortController.signal,
    })
    if (!response.ok) {
      const payload = await response.json().catch(() => null)
      throw new Error(payload && typeof payload.detail === 'string' ? payload.detail : `请求失败（${response.status}）`)
    }
    if (!response.body) throw new Error('浏览器不支持 SSE 响应流')

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
      const events = buffer.split('\n\n')
      buffer = done ? '' : (events.pop() || '')
      events.filter(Boolean).forEach(handleEvent)
      if (done) break
    }
    if (buffer.trim()) handleEvent(buffer)
    if (aiMessage.pending) throw new Error('Agent 没有返回完整结果')
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      // 用户主动停止时保留这条消息，但明确标记为未完成，避免误认为已得到结论。
      aiMessage.text = '本次分析已停止，未生成完整结论。'
      aiMessage.evidence = '可以补充问题后重新发送。'
      aiMessage.pending = false
      return
    }
    aiMessage.text = error instanceof Error ? `Agent 请求失败：${error.message}` : 'Agent 请求失败，请稍后重试'
    aiMessage.evidence = '请确认后端已启动，并检查浏览器是否保留了当前登录 Token。'
    aiMessage.pending = false
    ElMessage.error('Agent 接口调用失败')
  } finally {
    agentLoading.value = false
    agentAbortController = null
  }
}

// 中止当前 SSE 请求；后端不会把未完成的回答当作有效结论保存。
const cancelAgent = () => {
  agentAbortController?.abort()
}

const createWorkOrder = async () => {
  const suggestion = latestAgentAnswer.value?.work_order_suggestion
  if (!suggestion) {
    ElMessage.warning('请先提问诊断类问题，获取可生成工单的建议')
    return
  }
  workOrderLoading.value = true
  try {
    workOrder.value = await api<WorkOrderDraft>('/api/v1/work-orders/draft', {
      method: 'POST',
      body: JSON.stringify({
        // 这些字段来自最近一次诊断答案，后端仍会再次校验站点权限。
        title: suggestion.title,
        station_id: suggestion.station_id,
        issue: suggestion.issue,
        suggested_action: suggestion.suggested_action,
        priority: suggestion.priority,
      }),
    })
    workOrders.value = [workOrder.value, ...workOrders.value.filter(item => item.id !== workOrder.value?.id)]
    ElMessage.success('工单草稿已生成')
  } catch {
    ElMessage.warning('工单接口暂不可用，请稍后重试')
  } finally {
    workOrderLoading.value = false
  }
}

// 将当前答案和待确认项提交为人工审核记录；接口只创建待审核事项，不执行现场控制。
const transferToReview = async () => {
  const answer = latestAgentAnswer.value
  if (!answer || !answer.pending_items?.length || !canTransferToReview.value) {
    ElMessage.warning('当前回答没有可转交的待确认项')
    return
  }
  reviewLoading.value = true
  try {
    const review = await api<{ id: string }>('/api/v1/reviews', {
      method: 'POST',
      body: JSON.stringify({
        subject: `Agent ${answer.intent} 复核 · ${answer.request_id}`,
        recommendation: [answer.answer, ...answer.pending_items.map(item => `待确认：${item}`)].join('；'),
        comment: '由 Agent 待确认项转交人工复核。',
      }),
    })
    reviewId.value = review.id
    ElMessage.success(`已提交人工复核：${review.id}`)
  } catch {
    ElMessage.error('人工复核提交失败，请确认当前账号具备调度权限')
  } finally {
    reviewLoading.value = false
  }
}

// 按状态流转表推进工单，后端会拒绝越级状态变更。
const updateWorkOrderStatus = async (order: WorkOrderDraft, status: WorkOrderDraft['status']) => {
  workOrderStatusLoading.value = order.id
  try {
    const updated = await api<WorkOrderDraft>(`/api/v1/work-orders/${encodeURIComponent(order.id)}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    })
    workOrders.value = workOrders.value.map(item => item.id === updated.id ? updated : item)
    if (workOrder.value?.id === updated.id) workOrder.value = updated
    ElMessage.success(`工单状态已更新为${workOrderStatusNames[updated.status] || updated.status}`)
  } catch {
    ElMessage.error('工单状态更新失败，请按顺序处理')
  } finally {
    workOrderStatusLoading.value = null
  }
}

// 打开处理信息弹窗时复制当前负责人和截止时间，取消不会修改列表内容。
const openAssignmentDialog = (order: WorkOrderDraft) => {
  assignmentOrder.value = order
  assignmentForm.value = {
    owner: order.owner || '',
    due_at: order.due_at ? order.due_at.slice(0, 16) : '',
  }
  assignmentVisible.value = true
}

const saveAssignment = async () => {
  if (!assignmentOrder.value || (!assignmentForm.value.owner.trim() && !assignmentForm.value.due_at)) {
    ElMessage.warning('请填写负责人或截止时间')
    return
  }
  assignmentSaving.value = true
  try {
    const updated = await api<WorkOrderDraft>(`/api/v1/work-orders/${encodeURIComponent(assignmentOrder.value.id)}`, {
      method: 'PATCH',
      body: JSON.stringify({
        owner: assignmentForm.value.owner.trim() || null,
        due_at: assignmentForm.value.due_at ? new Date(assignmentForm.value.due_at).toISOString() : null,
      }),
    })
    workOrders.value = workOrders.value.map(item => item.id === updated.id ? updated : item)
    if (workOrder.value?.id === updated.id) workOrder.value = updated
    assignmentVisible.value = false
    ElMessage.success('工单处理信息已保存')
  } catch {
    ElMessage.error('工单处理信息保存失败，请确认工单仍可编辑')
  } finally {
    assignmentSaving.value = false
  }
}

// 页面进入时加载已生成的 Mock 工单。
onMounted(() => {
  loadWorkOrders()
  loadStations()
})

const formatTime = (value: string) => value.slice(11, 16)

// Agent 的观测时间来自 UTC Mock 测点，展示时转换为浏览器本地时间。
const formatLocalDateTime = (value: string) => {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (part: number) => String(part).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}
</script>

<template>
  <div class="page-title">
    <div>
      <h2>Agent 智能助手</h2>
      <p>事实 → 分析 → 规程引用 → 建议 → 待确认项</p>
    </div>
    <span class="tag tag-green">只读分析模式</span>
  </div>

  <div class="agent-layout">
    <div class="panel">
      <div style="padding:14px 18px;border-bottom:1px solid #1c3a4c">
        <el-tag size="small" type="success">协调 Agent</el-tag>
        <span class="muted" style="font-size:13px;margin-left:10px">8 个专业 Agent 可协作</span>
      </div>
      <div v-for="m in messages" :key="m.id" :class="['message',m.role==='user'?'user':'ai']">
        <b>{{m.role==='user'?'你':'Agent'}}</b>
        <div>{{m.text}}</div>
        <div v-if="m.role==='ai' && m.steps?.length" class="analysis-steps">
          <span class="analysis-steps__title">分析步骤</span>
          <span v-for="(step, index) in m.steps" :key="`${m.id}-step-${index}`" class="analysis-step">
            {{ index + 1 }}. {{ step }}
          </span>
        </div>
        <div v-if="m.role==='ai' && m.evidence" class="evidence" style="white-space:pre-line">{{m.evidence}}</div>
      </div>
      <div style="padding:12px 18px 0;display:flex;gap:8px;align-items:center">
        <span class="muted" style="font-size:13px;white-space:nowrap">分析站点</span>
        <el-select v-model="selectedStationId" clearable filterable placeholder="按问题内容识别" style="width:210px">
          <el-option v-for="station in stations" :key="station.id" :label="`${station.name} · ${station.status}`" :value="station.id" />
        </el-select>
      </div>
      <div style="padding:12px 18px;display:flex;gap:8px">
        <el-input v-model="input" :disabled="agentLoading" placeholder="例如：过去 2 小时哪个泵站压力波动最大？" @keyup.enter="ask()" />
        <el-button type="primary" :loading="agentLoading" :disabled="agentLoading" @click="ask()">发送</el-button>
        <el-button v-if="agentLoading" type="warning" plain @click="cancelAgent">停止分析</el-button>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head"><h3>示例问题</h3></div>
      <div class="table-wrap">
        <el-button v-for="q in ['现在四泵站出水流量是多少？','过去 2 小时哪个泵站压力波动最大？','二泵站流量下降后先核查什么？']" :key="q" style="width:100%;margin-bottom:9px;text-align:left" @click="ask(q)">{{q}}</el-button>
        <div class="warning" style="margin-top:8px">控制边界：涉及启动/停止泵、切阀或压力设定的请求将被拒绝，不生成控制命令。</div>
        <template v-if="canCreateWorkOrder">
          <el-button class="button-stable button-stable--block" type="primary" plain :loading="workOrderLoading" style="width:100%;margin-top:12px" @click="createWorkOrder">生成核查工单草稿</el-button>
          <p class="muted work-order-hint">当前按钮使用最近一次诊断建议填充工单。</p>
        </template>
        <template v-if="canTransferToReview">
          <el-button class="button-stable button-stable--block" type="warning" plain :loading="reviewLoading" style="width:100%;margin-top:10px" @click="transferToReview">提交人工复核</el-button>
          <p class="muted work-order-hint">只创建审核待办，不执行现场控制。</p>
          <p v-if="reviewId" class="muted work-order-hint">审核记录：{{ reviewId }}</p>
        </template>
        <div v-if="workOrder" class="panel" style="margin-top:14px;padding:12px">
          <div class="panel-head"><h3>工单草稿</h3><span>{{ workOrderStatusNames[workOrder.status] || workOrder.status }} · {{ workOrder.source === 'mock' ? '后端 Mock' : workOrder.source }}</span></div>
          <p class="muted">{{ workOrder.title }} · {{ formatTime(workOrder.created_at) }}</p>
          <p>{{ workOrder.issue }}</p>
          <p>建议动作：{{ workOrder.suggested_action }}</p>
        </div>
        <div class="panel" style="margin-top:14px;padding:12px">
          <div class="panel-head"><h3>工单列表</h3><el-button class="button-stable button-stable--xs" link :loading="workOrderListLoading" @click="loadWorkOrders">刷新</el-button></div>
          <div v-if="!workOrders.length" class="empty">暂无工单</div>
          <div v-for="order in workOrders" :key="order.id" class="work-order-row">
            <div><strong>{{ order.title }}</strong><p class="muted">{{ order.station_id || '通用任务' }} · {{ workOrderStatusNames[order.status] || order.status }} · {{ order.priority }} · {{ order.owner || '未分派' }}</p></div>
            <div class="work-order-actions">
              <el-button v-if="!['completed', 'cancelled'].includes(order.status)" size="small" plain @click="openAssignmentDialog(order)">处理信息</el-button>
              <el-button v-if="order.status === 'draft'" class="button-stable button-stable--sm" size="small" :loading="workOrderStatusLoading === order.id" @click="updateWorkOrderStatus(order, 'assigned')">分派</el-button>
              <el-button v-if="order.status === 'assigned'" class="button-stable button-stable--md" size="small" type="primary" :loading="workOrderStatusLoading === order.id" @click="updateWorkOrderStatus(order, 'in_progress')">开始处理</el-button>
              <el-button v-if="order.status === 'in_progress'" class="button-stable button-stable--md" size="small" type="success" :loading="workOrderStatusLoading === order.id" @click="updateWorkOrderStatus(order, 'completed')">标记完成</el-button>
              <el-button v-if="['draft', 'assigned', 'in_progress'].includes(order.status)" class="button-stable button-stable--sm" size="small" text type="danger" :loading="workOrderStatusLoading === order.id" @click="updateWorkOrderStatus(order, 'cancelled')">取消</el-button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <el-dialog v-model="assignmentVisible" title="补充工单处理信息" width="520px">
    <el-form label-width="90px">
      <el-form-item label="负责人"><el-input v-model="assignmentForm.owner" placeholder="例如：pump-team-a 或 operator" maxlength="80" /></el-form-item>
      <el-form-item label="截止时间"><el-input v-model="assignmentForm.due_at" type="datetime-local" /></el-form-item>
    </el-form>
    <p class="muted">当前 Mock 只保存负责人和截止时间，不会自动发送提醒。</p>
    <template #footer>
      <el-button @click="assignmentVisible = false">取消</el-button>
      <el-button class="button-stable button-stable--lg" type="primary" :loading="assignmentSaving" @click="saveAssignment">保存处理信息</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
/* 使用 flex 保持工单状态按钮在窄屏下也不会挤压标题。 */
.work-order-row { display:flex; justify-content:space-between; gap:12px; padding:10px 0; border-bottom:1px solid #1c3a4c; }
.work-order-row:last-child { border-bottom:0; }
.work-order-row p { margin:4px 0 0; }
.work-order-actions { display:flex; align-items:center; gap:4px; flex-wrap:wrap; justify-content:flex-end; }
.work-order-hint { margin:8px 0 0; font-size:13px; }
.analysis-steps { display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; align-items:center; }
.analysis-steps__title { color:#5be0ca; font-size:13px; }
.analysis-step { padding:3px 7px; border:1px solid #265464; border-radius:999px; color:#9bc5ca; background:#0b2431; font-size:12px; }
</style>
