<script setup lang="ts">
defineProps<{
  loading: boolean
  citation: { title: string; version: string; location: string; chunk_index: number; excerpt: string } | null
}>()

const visible = defineModel<boolean>({ default: false })
</script>

<template>
  <el-dialog v-model="visible" title="Agent 引用原文片段" width="720px">
    <div v-loading="loading">
      <template v-if="citation">
        <p class="muted">{{ citation.title }} · {{ citation.version }} · {{ citation.location }} · 分片 {{ citation.chunk_index + 1 }}</p>
        <pre class="evidence">{{ citation.excerpt }}</pre>
      </template>
    </div>
    <template #footer><el-button @click="visible = false">关闭</el-button></template>
  </el-dialog>
</template>
