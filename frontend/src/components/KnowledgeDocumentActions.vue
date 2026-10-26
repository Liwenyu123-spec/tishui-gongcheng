<script setup lang="ts">
defineProps<{ id: string; admin: boolean; updating: boolean }>()
const emit = defineEmits<{ preview: []; history: []; compare: []; status: [value: string]; remove: [] }>()
</script>

<template>
  <el-button link type="primary" @click="emit('preview')">预览引用</el-button>
  <el-button v-if="!id.startsWith('local-')" link type="info" @click="emit('history')">审核历史</el-button>
  <el-button v-if="!id.startsWith('local-')" link type="primary" @click="emit('compare')">版本对比</el-button>
  <template v-if="admin && !id.startsWith('local-')">
    <el-button link type="success" :disabled="updating" @click="emit('status', '现行')">现行</el-button>
    <el-button link type="warning" :disabled="updating" @click="emit('status', '待审')">待审</el-button>
    <el-button link type="danger" :disabled="updating" @click="emit('status', '废止')">废止</el-button>
    <el-button link type="info" :disabled="updating" @click="emit('status', '已归档')">归档</el-button>
    <el-button link type="danger" :disabled="updating" @click="emit('remove')">删除</el-button>
  </template>
</template>
