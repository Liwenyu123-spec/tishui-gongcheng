<script setup lang="ts">
defineProps<{
  loading: boolean
  result: { total_rows: number; accepted_rows: number; rejected_rows: number; errors: string[] } | null
}>()

const visible = defineModel<boolean>({ default: false })
const filename = defineModel<string>('filename', { required: true })
const content = defineModel<string>('content', { required: true })
const emit = defineEmits<{ validate: [] }>()
</script>

<template>
  <el-dialog v-model="visible" title="校验遥测 CSV" width="620px">
    <el-form label-width="90px">
      <el-form-item label="文件名"><el-input v-model="filename" /></el-form-item>
      <el-form-item label="CSV 内容"><el-input v-model="content" type="textarea" :rows="8" /></el-form-item>
    </el-form>
    <div v-if="result" class="muted" style="margin-top:10px">
      总行数 {{ result.total_rows }} · 通过 {{ result.accepted_rows }} · 拒绝 {{ result.rejected_rows }}
      <div v-for="error in result.errors" :key="error">{{ error }}</div>
    </div>
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button class="button-stable button-stable--md" type="primary" :loading="loading" @click="emit('validate')">开始校验</el-button>
    </template>
  </el-dialog>
</template>
