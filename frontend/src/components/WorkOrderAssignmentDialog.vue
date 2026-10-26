<script setup lang="ts">
defineProps<{ saving: boolean }>()
const visible = defineModel<boolean>({ default: false })
const form = defineModel<{ owner: string; due_at: string }>('form', { required: true })
const emit = defineEmits<{ save: [] }>()
</script>

<template>
  <el-dialog v-model="visible" title="补充工单处理信息" width="520px">
    <el-form label-width="90px">
      <el-form-item label="负责人"><el-input v-model="form.owner" placeholder="例如：pump-team-a 或 operator" maxlength="80" /></el-form-item>
      <el-form-item label="截止时间"><el-input v-model="form.due_at" type="datetime-local" /></el-form-item>
    </el-form>
    <p class="muted">只保存负责人和截止时间，不会自动发送提醒。</p>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button class="button-stable button-stable--lg" type="primary" :loading="saving" @click="emit('save')">保存处理信息</el-button>
    </template>
  </el-dialog>
</template>
