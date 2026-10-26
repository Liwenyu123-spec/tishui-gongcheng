<script setup lang="ts">
defineProps<{
  order: { title: string; created_at: string; issue: string; suggested_action: string; status: string; source: string } | null
  statusNames: Record<string, string>
  formatTime: (value: string) => string
}>()
</script>

<template>
  <div v-if="order" class="panel" style="margin-top:14px;padding:12px">
    <div class="panel-head"><h3>工单草稿</h3><span>{{ statusNames[order.status] || order.status }} · {{ order.source === 'mock' || !order.source ? '数据库' : order.source }}</span></div>
    <p class="muted">{{ order.title }} · {{ formatTime(order.created_at) }}</p>
    <p>{{ order.issue }}</p>
    <p>建议动作：{{ order.suggested_action }}</p>
  </div>
</template>
