<script setup lang="ts">
defineProps<{ canTransfer: boolean; loading: boolean; reviewId: string }>()
const emit = defineEmits<{ submit: [] }>()
</script>

<template>
  <template v-if="canTransfer">
    <el-button class="button-stable button-stable--block" type="warning" plain :loading="loading" style="width:100%;margin-top:10px" @click="emit('submit')">提交人工复核</el-button>
    <p class="muted work-order-hint">只创建审核待办，不执行现场控制。</p>
    <p v-if="reviewId" class="muted work-order-hint">审核记录：{{ reviewId }}</p>
  </template>
</template>
