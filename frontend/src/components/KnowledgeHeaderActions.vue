<script setup lang="ts">
const emit = defineEmits<{ import: []; csv: [] }>()
</script>

<template>
  <div><el-button type="primary" plain @click="emit('import')">导入资料</el-button><el-button plain @click="emit('csv')">校验遥测 CSV</el-button></div>
</template>
