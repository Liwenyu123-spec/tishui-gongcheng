<script setup lang="ts">
interface WorkOrderItem { id: string; title: string; station_id: string | null; status: string; priority: string; owner: string | null; issue: string; suggested_action: string; due_at: string | null; created_at: string; source: string }
defineProps<{
  orders: WorkOrderItem[]
  statusNames: Record<string, string>
  loading: boolean
  actionLoading: string | null
}>()
const emit = defineEmits<{
  refresh: []
  assign: [order: WorkOrderItem]
  status: [order: WorkOrderItem, status: string]
}>()
</script>

<template>
  <div class="panel" style="margin-top:14px;padding:12px">
    <div class="panel-head"><h3>工单列表</h3><el-button class="button-stable button-stable--xs" link :loading="loading" @click="emit('refresh')">刷新</el-button></div>
    <div v-if="!orders.length" class="empty">暂无工单</div>
    <div v-for="order in orders" :key="order.id" class="work-order-row">
      <div><strong>{{ order.title }}</strong><p class="muted">{{ order.station_id || '通用任务' }} · {{ statusNames[order.status] || order.status }} · {{ order.priority }} · {{ order.owner || '未分派' }}</p></div>
      <div class="work-order-actions">
        <el-button v-if="!['completed', 'cancelled'].includes(order.status)" size="small" plain @click="emit('assign', order)">处理信息</el-button>
        <el-button v-if="order.status === 'draft'" size="small" :loading="actionLoading === order.id" @click="emit('status', order, 'assigned')">分派</el-button>
        <el-button v-if="order.status === 'assigned'" size="small" type="primary" :loading="actionLoading === order.id" @click="emit('status', order, 'in_progress')">开始处理</el-button>
        <el-button v-if="order.status === 'in_progress'" size="small" type="success" :loading="actionLoading === order.id" @click="emit('status', order, 'completed')">标记完成</el-button>
        <el-button v-if="['draft', 'assigned', 'in_progress'].includes(order.status)" size="small" text type="danger" :loading="actionLoading === order.id" @click="emit('status', order, 'cancelled')">取消</el-button>
      </div>
    </div>
  </div>
</template>
