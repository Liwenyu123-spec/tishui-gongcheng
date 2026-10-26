<script setup lang="ts">
defineProps<{ visible: boolean; loading: boolean }>()
const emit = defineEmits<{ create: [] }>()
</script>

<template>
  <template v-if="visible">
    <el-button class="button-stable button-stable--block" type="primary" plain :loading="loading" style="width:100%;margin-top:12px" @click="emit('create')">生成核查工单草稿</el-button>
    <p class="muted work-order-hint">当前按钮使用最近一次诊断建议填充工单。</p>
  </template>
</template>
