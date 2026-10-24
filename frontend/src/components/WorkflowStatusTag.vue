<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ status: string }>()
const names: Record<string, string> = { running: '执行中', completed: '已完成', degraded: '已降级', timeout: '已超时', blocked: '已阻断', cancelled: '已取消', interrupted: '连接中断', paused: '等待审批', unknown: '未知' }
const types: Record<string, 'success' | 'warning' | 'danger' | 'info'> = { running: 'warning', completed: 'success', degraded: 'warning', timeout: 'danger', blocked: 'danger', cancelled: 'info', interrupted: 'danger', paused: 'warning', unknown: 'info' }
const label = computed(() => names[props.status] || props.status)
const type = computed(() => types[props.status] || 'info')
</script>
<template><el-tag size="small" effect="plain" :type="type">工作流：{{ label }}</el-tag></template>
