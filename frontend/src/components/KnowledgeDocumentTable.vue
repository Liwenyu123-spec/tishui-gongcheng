<script setup lang="ts">
import KnowledgeStatusTag from './KnowledgeStatusTag.vue'
import KnowledgeDocumentActions from './KnowledgeDocumentActions.vue'

defineProps<{
  rows: Array<{ id: string; title: string; filename: string; category: string; version: string; applicability: string; contentLength: number; date: string; status: string }>
  admin: boolean
  updatingId: string
}>()
const emit = defineEmits<{ preview: [id: string]; history: [id: string]; compare: [id: string]; status: [id: string, status: string]; remove: [id: string] }>()
</script>

<template>
  <div class="table-wrap">
    <el-table :data="rows">
      <el-table-column prop="title" label="资料名称" min-width="190" />
      <el-table-column prop="filename" label="文件名" min-width="190" />
      <el-table-column prop="category" label="类别" width="110" />
      <el-table-column prop="version" label="版本" width="90" />
      <el-table-column prop="applicability" label="适用范围" width="120" />
      <el-table-column prop="contentLength" label="正文长度" width="100" />
      <el-table-column prop="date" label="导入时间" width="120" />
      <el-table-column prop="status" label="状态" width="90">
        <template #default="s"><KnowledgeStatusTag :status="s.row.status" /></template>
      </el-table-column>
      <el-table-column label="操作" width="290">
        <template #default="s">
          <KnowledgeDocumentActions :id="s.row.id" :admin="admin" :updating="updatingId === s.row.id" @preview="emit('preview', s.row.id)" @history="emit('history', s.row.id)" @compare="emit('compare', s.row.id)" @status="emit('status', s.row.id, $event)" @remove="emit('remove', s.row.id)" />
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>
