<script setup lang="ts">
const query = defineModel<string>('query', { required: true })
const status = defineModel<string>('status', { required: true })
defineProps<{ loading: boolean }>()
const emit = defineEmits<{ search: [] }>()
</script>

<template>
  <div class="filterbar" style="padding:16px 18px 0">
    <el-input v-model="query" placeholder="搜索规程、设备或异常处理方法" style="max-width:430px" clearable />
    <el-select v-model="status" placeholder="资料状态" clearable style="width:130px">
      <el-option label="现行" value="现行" /><el-option label="待审" value="待审" /><el-option label="废止" value="废止" /><el-option label="已归档" value="已归档" />
    </el-select>
    <el-button class="button-stable button-stable--sm" type="primary" :loading="loading" @click="emit('search')">检索</el-button>
  </div>
</template>
