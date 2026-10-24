<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ status: string }>()
const names: Record<string, string> = { valid: '现行', pending: '待审', revoked: '废止', archived: '已归档', '现行': '现行', '待审': '待审', '废止': '废止', '已归档': '已归档' }
const label = computed(() => names[props.status] || props.status)
const tone = computed(() => label.value === '现行' ? 'tag-green' : label.value === '待审' ? 'tag-amber' : label.value === '已归档' ? 'tag-gray' : 'tag-red')
</script>
<template><span :class="['tag', tone]">{{ label }}</span></template>
