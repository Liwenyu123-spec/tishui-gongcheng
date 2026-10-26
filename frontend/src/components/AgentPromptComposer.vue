<script setup lang="ts">
const input = defineModel<string>({ default: '' })
defineProps<{ loading: boolean; cancelling: boolean }>()
const emit = defineEmits<{ ask: []; cancel: [] }>()
</script>

<template>
  <div style="padding:12px 18px;display:flex;gap:8px">
    <el-input v-model="input" :disabled="loading" placeholder="例如：过去 2 小时哪个泵站压力波动最大？" @keyup.enter="emit('ask')" />
    <el-button type="primary" :loading="loading" :disabled="loading" @click="emit('ask')">发送</el-button>
    <el-button v-if="loading" class="button-stable button-stable--md" type="warning" plain :loading="cancelling" :disabled="cancelling" @click="emit('cancel')">停止分析</el-button>
  </div>
</template>
