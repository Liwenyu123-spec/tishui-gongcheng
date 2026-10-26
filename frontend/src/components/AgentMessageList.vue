<script setup lang="ts">
import AgentRunSteps from './AgentRunSteps.vue'

interface MessageCitation {
  source_type: string
  source_id: string
  title: string
  detail: string
  location?: string | null
  chunk_index?: number | null
  rerank?: number | null
  rank?: number | null
}

defineProps<{
  messages: Array<{ id: string; role: 'user' | 'ai'; text: string; evidence?: string; steps?: string[]; workflowStatus?: string; runId?: string; planningSource?: string; limits?: { max_tool_calls?: number; max_model_calls?: number; max_concurrency?: number } }>
  citations: MessageCitation[]
}>()
const emit = defineEmits<{ viewCitation: [citation: MessageCitation] }>()
</script>

<template>
  <div v-for="message in messages" :key="message.id" :class="['message', message.role === 'user' ? 'user' : 'ai']">
    <b>{{ message.role === 'user' ? '你' : 'Agent' }}</b>
    <div>{{ message.text }}</div>
    <AgentRunSteps v-if="message.role === 'ai'" :steps="message.steps" :workflow-status="message.workflowStatus" :run-id="message.runId" :planning-source="message.planningSource" :limits="message.limits" />
    <div v-if="message.role === 'ai' && message.evidence" class="evidence" style="white-space:pre-line">{{ message.evidence }}</div>
    <div v-if="message.role === 'ai' && citations.length" class="evidence">
      <el-button v-for="citation in citations" :key="citation.source_id" link type="primary" size="small" @click="emit('viewCitation', citation)">查看 {{ citation.title }} 原文</el-button>
    </div>
  </div>
</template>
