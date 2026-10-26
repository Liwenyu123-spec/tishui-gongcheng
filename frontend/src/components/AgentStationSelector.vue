<script setup lang="ts">
defineProps<{ stations: Array<{ id: string; name: string; status: string }> }>()
const selected = defineModel<string>({ default: '' })
</script>

<template>
  <div style="padding:12px 18px 0;display:flex;gap:8px;align-items:center">
    <span class="muted" style="font-size:13px;white-space:nowrap">分析站点</span>
    <el-select v-model="selected" clearable filterable placeholder="按问题内容识别" style="width:210px">
      <el-option v-for="station in stations" :key="station.id" :label="`${station.name} · ${station.status}`" :value="station.id" />
    </el-select>
  </div>
</template>
