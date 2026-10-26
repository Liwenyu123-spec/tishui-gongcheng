<script setup lang="ts">
defineProps<{
  title: string
  loading: boolean
  result: { version: string; compared_version?: string; changed: boolean; diff: string[] } | null
}>()

const visible = defineModel<boolean>({ default: false })
</script>

<template>
  <el-dialog v-model="visible" :title="`版本对比：${title}`" width="720px">
    <div v-loading="loading">
      <p v-if="result && !result.compared_version" class="muted">没有找到同标题的其他版本。</p>
      <template v-else-if="result">
        <p class="muted">当前版本 {{ result.version }} · 对比版本 {{ result.compared_version }} · {{ result.changed ? '正文有变化' : '正文无变化' }}</p>
        <pre v-if="result.diff.length" class="diff-preview">{{ result.diff.join('\n') }}</pre>
      </template>
    </div>
    <template #footer><el-button @click="visible = false">关闭</el-button></template>
  </el-dialog>
</template>
