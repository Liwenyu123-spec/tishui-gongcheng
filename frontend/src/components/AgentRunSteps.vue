<script setup lang="ts">
import WorkflowStatusTag from './WorkflowStatusTag.vue'

defineProps<{
  steps?: string[]
  workflowStatus?: string
  runId?: string
  planningSource?: string
  limits?: { max_tool_calls?: number; max_model_calls?: number; max_concurrency?: number }
}>()
</script>

<template>
  <div v-if="steps?.length || workflowStatus" class="analysis-steps">
    <span class="analysis-steps__title">运行步骤</span>
    <WorkflowStatusTag v-if="workflowStatus" :status="workflowStatus" />
    <span v-if="runId" class="analysis-step">运行 {{ runId }}</span>
    <span v-if="planningSource" class="analysis-step">计划 {{ planningSource }}</span>
    <span v-if="limits" class="analysis-step">限额 工具 {{ limits.max_tool_calls ?? '—' }} / 模型 {{ limits.max_model_calls ?? '—' }}</span>
    <span v-for="(step, index) in steps" :key="index" class="analysis-step">{{ index + 1 }}. {{ step }}</span>
  </div>
</template>
