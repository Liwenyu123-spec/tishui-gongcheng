<script setup lang="ts">
import WorkflowStatusTag from './WorkflowStatusTag.vue'

defineProps<{ status: string; requestState: string; loading: boolean }>()
const emit = defineEmits<{ reset: [] }>()
</script>

<template>
  <div class="agent-toolbar">
    <span :class="['agent-status', `agent-status--${requestState}`]"><i></i>{{ status }}</span>
    <WorkflowStatusTag v-if="status && status !== '可以开始提问'" :status="status" />
    <el-button class="button-stable button-stable--md" size="small" plain :disabled="loading" @click="emit('reset')">新建会话</el-button>
  </div>
</template>
