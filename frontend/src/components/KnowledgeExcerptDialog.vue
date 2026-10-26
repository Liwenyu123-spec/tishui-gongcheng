<script setup lang="ts">
defineProps<{
  loading: boolean
  result: { title: string; version: string; location: string; chunk_index: number; excerpt: string } | null
}>()

const visible = defineModel<boolean>({ default: false })
</script>

<template>
  <el-dialog v-model="visible" title="引用原文片段" width="720px">
    <div v-loading="loading">
      <template v-if="result">
        <p class="muted">{{ result.title }} · {{ result.version }} · {{ result.location }} · 分片 {{ result.chunk_index + 1 }}</p>
        <pre class="diff-preview">{{ result.excerpt }}</pre>
      </template>
    </div>
    <template #footer><el-button @click="visible = false">关闭</el-button></template>
  </el-dialog>
</template>
