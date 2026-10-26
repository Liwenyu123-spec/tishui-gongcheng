<script setup lang="ts">
defineProps<{
  title: string
  loading: boolean
  rows: Array<{ action?: string; detail?: string; created_at?: string; actor?: string }>
}>()

const visible = defineModel<boolean>({ default: false })
</script>

<template>
  <el-dialog v-model="visible" :title="title" width="720px">
    <el-skeleton v-if="loading" :rows="4" animated />
    <el-empty v-else-if="!rows.length" description="暂无审核历史" />
    <el-timeline v-else>
      <el-timeline-item v-for="(item, index) in rows" :key="`${item.created_at || 'event'}-${index}`" :timestamp="item.created_at || '时间未知'">
        <strong>{{ item.action || '生命周期变更' }}</strong>
        <p class="muted">{{ item.detail || '无详细说明' }}<template v-if="item.actor"> · 操作人：{{ item.actor }}</template></p>
      </el-timeline-item>
    </el-timeline>
    <template #footer><el-button @click="visible = false">关闭</el-button></template>
  </el-dialog>
</template>
