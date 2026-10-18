<script setup lang="ts">
import { onMounted, ref } from 'vue'
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

const input = ref('')
const messages = ref([{ role: 'ai', text: '您好，我是调度辅助 Agent。当前使用 Mock 数据，只提供只读分析和建议草稿。请描述您要查询的运行问题。' }])
const workOrder = ref<WorkOrderDraft | null>(null)
const workOrderLoading = ref(false)
const workOrders = ref<WorkOrderDraft[]>([])
const workOrderListLoading = ref(false)
const workOrderStatusLoading = ref<string | null>(null)
const assignmentVisible = ref(false)
const assignmentSaving = ref(false)
const assignmentOrder = ref<WorkOrderDraft | null>(null)
const assignmentForm = ref({ owner: '', due_at: '' })
const workOrderStatusNames: Record<string, string> = { draft: '草稿', assigned: '已分派', in_progress: '处理中', completed: '已完成', cancelled: '已取消' }

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
const ask = (q = input.value) => {
  if (!q) return
  messages.value.push({ role: 'user', text: q })
  messages.value.push({ role: 'ai', text: '基于当前模拟数据，二泵站过去 2 小时压力波动最大。建议先核查 2 号泵入口压力、泵组电流以及渠道前段水位。该结论需要接入真实测点后复核。' })
  input.value = ''
}

const createWorkOrder = async () => {
  workOrderLoading.value = true
  try {
    workOrder.value = await api<WorkOrderDraft>('/api/v1/work-orders/draft', {
      method: 'POST',
      body: JSON.stringify({
        title: '二泵站流量下降核查',
        station_id: 'pump-02',
        issue: '二泵站过去 2 小时压力波动较大，出水流量存在下降风险。',
        suggested_action: '核查 2 号泵入口压力、泵组电流和渠道前段水位。',
        priority: 'medium',
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
onMounted(loadWorkOrders)

const formatTime = (value: string) => value.slice(11, 16)
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
        <span class="muted" style="font-size:11px;margin-left:10px">8 个专业 Agent 可协作</span>
      </div>
      <div v-for="m in messages" :key="m.text+m.role" :class="['message',m.role==='user'?'user':'ai']">
        <b>{{m.role==='user'?'你':'Agent'}}</b>
        <div>{{m.text}}</div>
        <div v-if="m.role==='ai'" class="evidence">证据：telemetry_mock · 二泵站 · 过去 2 小时<br>规程：二泵站运行规程 v1.2 · 第三章（现行）</div>
      </div>
      <div style="padding:12px 18px;display:flex;gap:8px">
        <el-input v-model="input" placeholder="例如：过去 2 小时哪个泵站压力波动最大？" @keyup.enter="ask()" />
        <el-button type="primary" @click="ask()">发送</el-button>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head"><h3>示例问题</h3></div>
      <div class="table-wrap">
        <el-button v-for="q in ['现在四泵站出水流量是多少？','过去 2 小时哪个泵站压力波动最大？','二泵站流量下降后先核查什么？']" :key="q" style="width:100%;margin-bottom:9px;text-align:left" @click="ask(q)">{{q}}</el-button>
        <div class="warning" style="margin-top:8px">控制边界：涉及启动/停止泵、切阀或压力设定的请求将被拒绝，不生成控制命令。</div>
        <el-button class="button-stable button-stable--block" type="primary" plain :loading="workOrderLoading" style="width:100%;margin-top:12px" @click="createWorkOrder">生成核查工单草稿</el-button>
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
</style>
