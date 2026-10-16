<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/http'

interface ApiKnowledgeDocument {
  id: string
  filename: string
  title: string
  version: string
  status: string
  content_length: number
  imported_at: string
  source: string
}

interface CsvImportResponse {
  success: boolean
  filename: string | null
  total_rows: number
  accepted_rows: number
  rejected_rows: number
  errors: string[]
}

interface KnowledgeRow {
  id: string
  title: string
  filename: string
  version: string
  status: string
  date: string
  contentLength: number
  source: string
}

const localDocuments: KnowledgeRow[] = [
  { id: 'local-1', title: '二泵站运行规程', filename: 'pump-02-operation.md', version: 'v1.2', status: '现行', date: '2026-08-12', contentLength: 1840, source: '本地示例' },
  { id: 'local-2', title: '泵组异常处理预案', filename: 'pump-alarm-plan.md', version: 'v0.9', status: '待审', date: '2026-10-01', contentLength: 1260, source: '本地示例' },
  { id: 'local-3', title: '四泵站 2 号泵维修手册', filename: 'pump-04-maintenance.pdf', version: 'v2.1', status: '废止', date: '2025-12-18', contentLength: 3520, source: '本地示例' },
]
const statusNames: Record<string, string> = { valid: '现行', pending: '待审', revoked: '废止' }
const rows = ref<KnowledgeRow[]>(localDocuments.map(document => ({ ...document })))
const query = ref('')
const statusFilter = ref('')
const loading = ref(false)
const sourceLabel = ref('本地示例')
const importVisible = ref(false)
const importing = ref(false)
const importForm = reactive({ filename: '', title: '', version: '1.0', content: '' })
const csvVisible = ref(false)
const csvLoading = ref(false)
const csvResult = ref<CsvImportResponse | null>(null)
const csvForm = reactive({ filename: 'telemetry.csv', content: 'station_id,observed_at,metric,value,unit\npump-02,2026-10-16T10:00:00Z,flow,1080,m³/h' })

const filteredRows = computed(() => rows.value.filter(row => {
  const matchesQuery = !query.value || `${row.title} ${row.filename}`.toLowerCase().includes(query.value.toLowerCase())
  const matchesStatus = !statusFilter.value || row.status === statusFilter.value
  return matchesQuery && matchesStatus
}))

const formatDocument = (document: ApiKnowledgeDocument): KnowledgeRow => ({
  id: document.id,
  title: document.title,
  filename: document.filename,
  version: document.version,
  status: statusNames[document.status] || document.status,
  date: document.imported_at.slice(0, 10),
  contentLength: document.content_length,
  source: document.source === 'mock' ? '后端 Mock' : document.source,
})

const loadKnowledge = async () => {
  loading.value = true
  try {
    const result = await api<ApiKnowledgeDocument[]>('/api/v1/knowledge')
    if (result.length) {
      rows.value = result.map(formatDocument)
      sourceLabel.value = result[0].source === 'mock' ? '后端 Mock 数据' : result[0].source
    } else {
      sourceLabel.value = '接口暂无记录 · 本地示例'
      ElMessage.info('知识库接口当前没有文档，页面暂显示本地示例')
    }
  } catch {
    sourceLabel.value = '本地示例'
    ElMessage.warning('知识库接口暂不可用，当前显示本地示例')
  } finally {
    loading.value = false
  }
}

const openImport = () => {
  importForm.filename = ''
  importForm.title = ''
  importForm.version = '1.0'
  importForm.content = ''
  importVisible.value = true
}

const importDocument = async () => {
  if (!importForm.filename || !importForm.title || !importForm.content) {
    ElMessage.warning('请填写文件名、资料名称和正文内容')
    return
  }
  importing.value = true
  try {
    const result = await api<ApiKnowledgeDocument>('/api/v1/knowledge/import', {
      method: 'POST',
      body: JSON.stringify(importForm),
    })
    rows.value.unshift(formatDocument(result))
    sourceLabel.value = result.source === 'mock' ? '后端 Mock 数据' : result.source
    importVisible.value = false
    ElMessage.success('资料导入成功')
  } catch {
    ElMessage.error('资料导入失败，请检查接口和提交内容')
  } finally {
    importing.value = false
  }
}

const preview = (row: KnowledgeRow) => {
  ElMessage.info(`${row.title} · ${row.version} · 当前仅展示文档元数据`)
}

const validateCsv = async () => {
  if (!csvForm.content.trim()) {
    ElMessage.warning('请输入 CSV 内容')
    return
  }
  csvLoading.value = true
  try {
    csvResult.value = await api<CsvImportResponse>('/api/v1/imports/telemetry-csv', {
      method: 'POST',
      headers: { 'Content-Type': 'text/csv', 'X-Filename': csvForm.filename },
      body: csvForm.content,
    })
    if (csvResult.value.success) ElMessage.success('CSV 校验通过')
    else ElMessage.warning('CSV 校验发现问题，请查看错误明细')
  } catch {
    ElMessage.error('CSV 校验接口暂不可用')
  } finally {
    csvLoading.value = false
  }
}

onMounted(loadKnowledge)
</script>

<template>
  <div class="page-title">
    <div>
      <h2>知识库与设备资料</h2>
      <p>检索现行规程、设备台账、应急预案和维修记录 · {{ sourceLabel }}</p>
    </div>
    <div><el-button type="primary" plain @click="openImport">导入资料</el-button><el-button plain @click="csvVisible = true">校验遥测 CSV</el-button></div>
  </div>

  <div class="panel">
    <div class="filterbar" style="padding:16px 18px 0">
      <el-input v-model="query" placeholder="搜索规程、设备或异常处理方法" style="max-width:430px" clearable />
      <el-select v-model="statusFilter" placeholder="资料状态" clearable style="width:130px">
        <el-option label="现行" value="现行" />
        <el-option label="待审" value="待审" />
        <el-option label="废止" value="废止" />
      </el-select>
      <el-button type="primary" :loading="loading">检索</el-button>
    </div>
    <div class="table-wrap">
      <el-table :data="filteredRows">
        <el-table-column prop="title" label="资料名称" min-width="190" />
        <el-table-column prop="filename" label="文件名" min-width="190" />
        <el-table-column prop="version" label="版本" width="90" />
        <el-table-column prop="contentLength" label="正文长度" width="100" />
        <el-table-column prop="date" label="导入时间" width="120" />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="s"><span :class="['tag',s.row.status==='现行'?'tag-green':s.row.status==='待审'?'tag-amber':'tag-red']">{{s.row.status}}</span></template>
        </el-table-column>
        <el-table-column label="操作" width="110">
          <template #default="s"><el-button link type="primary" @click="preview(s.row)">预览引用</el-button></template>
        </el-table-column>
      </el-table>
    </div>
  </div>

  <el-dialog v-model="importVisible" title="导入知识资料" width="520px">
    <el-form label-width="90px">
      <el-form-item label="文件名"><el-input v-model="importForm.filename" placeholder="例如 pump-02-operation.md" /></el-form-item>
      <el-form-item label="资料名称"><el-input v-model="importForm.title" placeholder="例如二泵站运行规程" /></el-form-item>
      <el-form-item label="版本"><el-input v-model="importForm.version" /></el-form-item>
      <el-form-item label="正文内容"><el-input v-model="importForm.content" type="textarea" :rows="6" placeholder="输入需要保存的资料正文" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="importVisible = false">取消</el-button>
      <el-button type="primary" :loading="importing" @click="importDocument">确认导入</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="csvVisible" title="校验遥测 CSV" width="620px">
    <el-form label-width="90px">
      <el-form-item label="文件名"><el-input v-model="csvForm.filename" /></el-form-item>
      <el-form-item label="CSV 内容"><el-input v-model="csvForm.content" type="textarea" :rows="8" /></el-form-item>
    </el-form>
    <div v-if="csvResult" class="muted" style="margin-top:10px">总行数 {{ csvResult.total_rows }} · 通过 {{ csvResult.accepted_rows }} · 拒绝 {{ csvResult.rejected_rows }}<div v-for="error in csvResult.errors" :key="error">{{ error }}</div></div>
    <template #footer><el-button @click="csvVisible = false">关闭</el-button><el-button type="primary" :loading="csvLoading" @click="validateCsv">开始校验</el-button></template>
  </el-dialog>
</template>
