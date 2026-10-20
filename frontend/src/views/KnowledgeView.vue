<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/http'

interface ApiKnowledgeDocument {
  id: string
  filename: string
  title: string
  version: string
  category: string
  status: string
  content_length: number
  imported_at: string
  station_ids: string[]
  effective_from: string | null
  effective_to: string | null
  approved_at: string | null
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

interface SearchHit {
  source_id: string
  title: string
  version: string
  detail: string
  score: number
  source: string
  filename: string
  station_ids: string[]
  chunk_index: number | null
  location: string
  category: string
  confidence: string
}

interface KnowledgeRow {
  id: string
  title: string
  filename: string
  version: string
  category: string
  status: string
  date: string
  contentLength: number
  applicability: string
  source: string
}

const localDocuments: KnowledgeRow[] = [
  { id: 'local-1', title: '二泵站运行规程', filename: 'pump-02-operation.md', version: 'v1.2', category: '规程', status: '现行', date: '2026-08-12', contentLength: 1840, applicability: '二泵站', source: '本地示例' },
  { id: 'local-2', title: '泵组异常处理预案', filename: 'pump-alarm-plan.md', version: 'v0.9', category: '应急预案', status: '待审', date: '2026-10-01', contentLength: 1260, applicability: '全局', source: '本地示例' },
  { id: 'local-3', title: '四泵站 2 号泵维修手册', filename: 'pump-04-maintenance.pdf', version: 'v2.1', category: '手册', status: '废止', date: '2025-12-18', contentLength: 3520, applicability: '四泵站', source: '本地示例' },
]
const statusNames: Record<string, string> = { valid: '现行', pending: '待审', revoked: '废止' }
const statusCodes: Record<string, string> = { 现行: 'valid', 待审: 'pending', 废止: 'revoked' }
const rows = ref<KnowledgeRow[]>(localDocuments.map(document => ({ ...document })))
const query = ref('')
const statusFilter = ref('')
const loading = ref(false)
const searchHits = ref<SearchHit[]>([])
const searchMessage = ref('')
const sourceLabel = ref('本地示例')
const importVisible = ref(false)
const importing = ref(false)
const extracting = ref(false)
const askQuestion = ref('')
const askAnswer = ref('')
const askRewritten = ref('')
const askCompression = ref('')
const askSources = ref<SearchHit[]>([])
const askSessionId = ref(localStorage.getItem('knowledge_ask_session') || '')
const askTurns = ref<{ role: string; text: string }[]>([])
const askNeedsClarification = ref(false)
const asking = ref(false)
const importForm = reactive({ filename: '', title: '', version: '1.0', category: '规程', content: '', stationIds: '', effectiveFrom: '', effectiveTo: '' })
const csvVisible = ref(false)
const csvLoading = ref(false)
const csvResult = ref<CsvImportResponse | null>(null)
const csvForm = reactive({ filename: 'telemetry.csv', content: 'station_id,observed_at,metric,value,unit\npump-02,2026-10-16T10:00:00Z,flow,1080,m³/h' })
const statusUpdatingId = ref('')
const isAdmin = computed(() => {
  try {
    return JSON.parse(localStorage.getItem('current_user') || '{}').role === 'admin'
  } catch {
    return false
  }
})

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
  category: document.category || '规程',
  status: statusNames[document.status] || document.status,
  date: document.imported_at.slice(0, 10),
  contentLength: document.content_length,
  applicability: document.station_ids?.length ? document.station_ids.join('、') : '全局',
  source: document.source === 'mock' ? '后端 Mock' : document.source,
})

const searchKnowledge = async () => {
  const keyword = query.value.trim()
  if (!keyword) {
    searchHits.value = []
    searchMessage.value = ''
    await loadKnowledge()
    return
  }
  loading.value = true
  try {
    const result = await api<{ results: SearchHit[] }>(`/api/v1/knowledge/search?q=${encodeURIComponent(keyword)}`)
    searchHits.value = result.results
    searchMessage.value = result.results.length ? `检索到 ${result.results.length} 条来源` : '没有命中现行资料或内置规程'
  } catch {
    searchHits.value = []
    searchMessage.value = '检索接口暂不可用'
    ElMessage.warning('检索接口暂不可用')
  } finally {
    loading.value = false
  }
}

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
  importForm.category = '规程'
  importForm.content = ''
  importForm.stationIds = ''
  importForm.effectiveFrom = ''
  importForm.effectiveTo = ''
  importVisible.value = true
}

const clearAskSession = () => {
  askSessionId.value = ''
  localStorage.removeItem('knowledge_ask_session')
  askTurns.value = []
  askAnswer.value = ''
  askRewritten.value = ''
  askCompression.value = ''
  askSources.value = []
  askNeedsClarification.value = false
  askQuestion.value = ''
}

const askKnowledge = async () => {
  const question = askQuestion.value.trim()
  if (!question) {
    ElMessage.warning('请输入要说明的规程问题')
    return
  }
  asking.value = true
  askTurns.value = [...askTurns.value, { role: '用户', text: question }]
  try {
    const result = await api<{
      answer: string
      rewritten_query?: string
      session_id?: string
      effective_question?: string
      needs_clarification?: boolean
      clarification?: string
      merged?: boolean
      sources: SearchHit[]
      compression?: { chars_before?: number; chars_after?: number; reduced?: number }
    }>('/api/v1/knowledge/rag/ask', {
      method: 'POST',
      body: JSON.stringify({ question, k: 5, session_id: askSessionId.value || null }),
    })
    if (result.session_id) {
      askSessionId.value = result.session_id
      localStorage.setItem('knowledge_ask_session', result.session_id)
    }
    askAnswer.value = result.answer
    askRewritten.value = result.rewritten_query
      || (result.merged && result.effective_question ? `合并问法：${result.effective_question}` : '')
    askNeedsClarification.value = Boolean(result.needs_clarification)
    const compression = result.compression
    askCompression.value = compression && compression.chars_before
      ? `上下文压缩：${compression.chars_before || 0} → ${compression.chars_after || 0} 字（减少 ${compression.reduced || 0}）`
      : ''
    askSources.value = result.sources || []
    askTurns.value = [...askTurns.value, { role: '助手', text: result.answer }]
    askQuestion.value = ''
  } catch (error) {
    askAnswer.value = ''
    askRewritten.value = ''
    askCompression.value = ''
    askSources.value = []
    askNeedsClarification.value = false
    ElMessage.error(error instanceof Error ? error.message : '规程说明生成失败')
  } finally {
    asking.value = false
  }
}

const extractFromFile = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  extracting.value = true
  try {
    const body = new FormData()
    body.append('file', file)
    const token = localStorage.getItem('access_token')
    const response = await fetch('/api/v1/knowledge/extract', {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      body,
    })
    const data = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(data && typeof data.detail === 'string' ? data.detail : `解析失败（${response.status}）`)
    }
    importForm.filename = data.filename
    if (!importForm.title) importForm.title = data.title
    importForm.content = data.content
    ElMessage.success(`已从文件抽出 ${data.content_length} 字，解析器 ${data.parser}`)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '文件解析失败')
  } finally {
    extracting.value = false
  }
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
      body: JSON.stringify({
        filename: importForm.filename,
        title: importForm.title,
        version: importForm.version,
        category: importForm.category,
        content: importForm.content,
        station_ids: importForm.stationIds.split(/[,，\s]+/).map(item => item.trim()).filter(Boolean),
        effective_from: importForm.effectiveFrom ? new Date(importForm.effectiveFrom).toISOString() : null,
        effective_to: importForm.effectiveTo ? new Date(importForm.effectiveTo).toISOString() : null,
      }),
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

const updateStatus = async (row: KnowledgeRow, displayStatus: string) => {
  if (!isAdmin.value || row.id.startsWith('local-')) {
    ElMessage.info('当前示例资料不能修改状态，请先导入后端文档')
    return
  }
  statusUpdatingId.value = row.id
  try {
    const result = await api<ApiKnowledgeDocument>(`/api/v1/knowledge/${encodeURIComponent(row.id)}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status: statusCodes[displayStatus] }),
    })
    row.status = statusNames[result.status] || result.status
    ElMessage.success(`资料状态已更新为${row.status}`)
  } catch {
    ElMessage.error('资料状态更新失败，请稍后重试')
  } finally {
    statusUpdatingId.value = ''
  }
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

  <div class="panel" style="margin-bottom:16px;padding:16px 18px">
    <p class="muted">规程说明：根据现行检索片段生成，不查询实时测点。缺泵站时可多轮补问。</p>
    <div class="filterbar" style="padding:0">
      <el-input
        v-model="askQuestion"
        :placeholder="askNeedsClarification ? '例如直接回复：二泵站' : (askTurns.length ? '可继续追问，例如：那电流呢' : '例如：流量下降后按规程先核查什么')"
        style="max-width:520px"
        clearable
        @keyup.enter="askKnowledge"
      />
      <el-button class="button-stable button-stable--sm" type="primary" :loading="asking" @click="askKnowledge">{{ askNeedsClarification ? '继续' : '生成说明' }}</el-button>
      <el-button class="button-stable button-stable--sm" plain :disabled="asking" @click="clearAskSession">新对话</el-button>
    </div>
    <div v-if="askTurns.length" style="margin-top:12px">
      <p v-for="(turn, index) in askTurns" :key="`${turn.role}-${index}`" class="muted">{{ turn.role }}：{{ turn.text }}</p>
    </div>
    <div v-if="askAnswer && !askNeedsClarification" style="margin-top:12px">
      <p v-if="askRewritten" class="muted">检索问法：{{ askRewritten }}</p>
      <p v-if="askCompression" class="muted">{{ askCompression }}</p>
      <p v-for="source in askSources" :key="source.source_id" class="muted">引用：{{ source.title }} · {{ source.location }}</p>
    </div>
  </div>

  <div class="panel">
    <div class="filterbar" style="padding:16px 18px 0">
      <el-input v-model="query" placeholder="搜索规程、设备或异常处理方法" style="max-width:430px" clearable />
      <el-select v-model="statusFilter" placeholder="资料状态" clearable style="width:130px">
        <el-option label="现行" value="现行" />
        <el-option label="待审" value="待审" />
        <el-option label="废止" value="废止" />
      </el-select>
      <el-button class="button-stable button-stable--sm" type="primary" :loading="loading" @click="searchKnowledge">检索</el-button>
    </div>
    <div v-if="searchMessage" style="padding:12px 18px 0">
      <p class="muted">{{ searchMessage }}</p>
      <div v-for="hit in searchHits" :key="`${hit.source_id}-${hit.chunk_index}`" class="panel" style="margin-top:8px;padding:12px 14px">
        <strong>{{ hit.title }}</strong>
        <p class="muted">{{ hit.category || '规程' }} · {{ hit.filename || '无文件名' }} · {{ hit.version }} · {{ hit.location }} · {{ hit.station_ids.length ? hit.station_ids.join('、') : '全局' }} · 相关度 {{ hit.score }} · {{ hit.confidence === 'low' ? '低置信' : '可引用' }}</p>
        <p>{{ hit.detail }}</p>
      </div>
    </div>
    <div class="table-wrap">
      <el-table :data="filteredRows">
        <el-table-column prop="title" label="资料名称" min-width="190" />
        <el-table-column prop="filename" label="文件名" min-width="190" />
        <el-table-column prop="category" label="类别" width="110" />
        <el-table-column prop="version" label="版本" width="90" />
        <el-table-column prop="applicability" label="适用范围" width="120" />
        <el-table-column prop="contentLength" label="正文长度" width="100" />
        <el-table-column prop="date" label="导入时间" width="120" />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="s"><span :class="['tag',s.row.status==='现行'?'tag-green':s.row.status==='待审'?'tag-amber':'tag-red']">{{s.row.status}}</span></template>
        </el-table-column>
        <el-table-column label="操作" width="220">
          <template #default="s">
            <el-button link type="primary" @click="preview(s.row)">预览引用</el-button>
            <template v-if="isAdmin && !s.row.id.startsWith('local-')">
              <el-button link type="success" :disabled="statusUpdatingId === s.row.id" @click="updateStatus(s.row, '现行')">现行</el-button>
              <el-button link type="warning" :disabled="statusUpdatingId === s.row.id" @click="updateStatus(s.row, '待审')">待审</el-button>
              <el-button link type="danger" :disabled="statusUpdatingId === s.row.id" @click="updateStatus(s.row, '废止')">废止</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>

  <el-dialog v-model="importVisible" title="导入知识资料" width="520px">
    <el-form label-width="90px">
      <el-form-item label="上传文件">
        <input type="file" accept=".txt,.md,.html,.htm,.pdf,.docx" :disabled="extracting" @change="extractFromFile" />
        <p class="muted">支持 PDF、Word、Markdown 和文本；抽出正文后仍需确认导入，新资料默认为待审。</p>
      </el-form-item>
      <el-form-item label="文件名"><el-input v-model="importForm.filename" placeholder="例如 pump-02-operation.md" /></el-form-item>
      <el-form-item label="资料名称"><el-input v-model="importForm.title" placeholder="例如二泵站运行规程" /></el-form-item>
      <el-form-item label="版本"><el-input v-model="importForm.version" /></el-form-item>
      <el-form-item label="类别">
        <el-select v-model="importForm.category" style="width:100%">
          <el-option label="规程" value="规程" />
          <el-option label="手册" value="手册" />
          <el-option label="台账" value="台账" />
          <el-option label="维修记录" value="维修记录" />
          <el-option label="应急预案" value="应急预案" />
        </el-select>
      </el-form-item>
      <el-form-item label="适用站点"><el-input v-model="importForm.stationIds" placeholder="例如 pump-02；留空表示全局" /></el-form-item>
      <el-form-item label="生效时间"><el-input v-model="importForm.effectiveFrom" type="datetime-local" /></el-form-item>
      <el-form-item label="失效时间"><el-input v-model="importForm.effectiveTo" type="datetime-local" /></el-form-item>
      <el-form-item label="正文内容"><el-input v-model="importForm.content" type="textarea" :rows="6" placeholder="输入需要保存的资料正文" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="importVisible = false">取消</el-button>
      <el-button class="button-stable button-stable--md" type="primary" :loading="importing" @click="importDocument">确认导入</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="csvVisible" title="校验遥测 CSV" width="620px">
    <el-form label-width="90px">
      <el-form-item label="文件名"><el-input v-model="csvForm.filename" /></el-form-item>
      <el-form-item label="CSV 内容"><el-input v-model="csvForm.content" type="textarea" :rows="8" /></el-form-item>
    </el-form>
    <div v-if="csvResult" class="muted" style="margin-top:10px">总行数 {{ csvResult.total_rows }} · 通过 {{ csvResult.accepted_rows }} · 拒绝 {{ csvResult.rejected_rows }}<div v-for="error in csvResult.errors" :key="error">{{ error }}</div></div>
    <template #footer><el-button @click="csvVisible = false">关闭</el-button><el-button class="button-stable button-stable--md" type="primary" :loading="csvLoading" @click="validateCsv">开始校验</el-button></template>
  </el-dialog>
</template>
