<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { compareKnowledgeDocument, deleteKnowledgeDocument, extractKnowledgeFile, fetchKnowledgeDocuments, fetchKnowledgeExcerpt, fetchKnowledgeHistory, importKnowledgeDocument, searchKnowledgeDocuments, updateKnowledgeStatus, validateTelemetryCsv, type KnowledgeAuditEvent } from '../api/knowledge'
import { registerPageRefresh } from '../composables/pageRefresh'
import { currentUserRole } from '../composables/currentUser'
import KnowledgeCsvDialog from '../components/KnowledgeCsvDialog.vue'
import KnowledgeCompareDialog from '../components/KnowledgeCompareDialog.vue'
import KnowledgeExcerptDialog from '../components/KnowledgeExcerptDialog.vue'
import KnowledgeHistoryDialog from '../components/KnowledgeHistoryDialog.vue'
import KnowledgeImportDialog from '../components/KnowledgeImportDialog.vue'
import KnowledgeFilterBar from '../components/KnowledgeFilterBar.vue'
import KnowledgeHeaderActions from '../components/KnowledgeHeaderActions.vue'
import KnowledgeDiagnosePanel from '../components/KnowledgeDiagnosePanel.vue'
import KnowledgeAskPanel from '../components/KnowledgeAskPanel.vue'
import KnowledgeSearchResults from '../components/KnowledgeSearchResults.vue'
import KnowledgeDocumentTable from '../components/KnowledgeDocumentTable.vue'
import { diagnoseRag, fetchRagStatus, askRag } from '../api/rag'
import { backendSourceLabel, classifyRemoteList, remoteListLabel } from '../composables/dataSource'

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
  // 检索接口会带重排概率；rag/ask 的 sources 目前不带，故声明为可选。
  rerank?: number | null
  rank?: number
  matched_terms?: string[]
  context_excerpt?: string
}
interface SearchConflict {
  source_ids: string[]
  reason: string
  details: string[]
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

// 诊断接口返回的分项得分；字段可能缺失（例如未启用重排时没有 rerank_*）。
interface DiagnoseComponents {
  lexical?: number
  vector_similarity?: number
  vector_bonus?: number
  bm25_raw?: number
  bm25_bonus?: number
  score_before_rerank?: number
  rerank_probability?: number
  rerank_bonus?: number
  candidate_from?: string
}

interface DiagnoseHit {
  document_id: string
  title: string
  version: string
  category: string
  location: string
  chunk_index: number | null
  score: number
  rerank: number | null
  confidence: string
  passed: boolean
  components: DiagnoseComponents
  excerpt: string
}

interface DiagnoseResult {
  question: string
  reason: string
  reason_text: string
  verdict: string
  notes: string[]
  environment: {
    engine_mode?: string
    embedding?: string
    rerank?: string
    rerank_error?: string | null
    degraded?: boolean
    chunks?: number
    warmup?: { ok?: boolean; elapsed_seconds?: number | null; error?: string | null }
  }
  environment_notes: string[]
  gate: {
    passed?: boolean
    min_score?: number
    min_rerank?: number | null
    top_score?: number
    top_rerank?: number | null
    kept?: number
    total?: number
  } | null
  hits: DiagnoseHit[]
  elapsed_ms: number
}

const localDocuments: KnowledgeRow[] = [
  { id: 'local-1', title: '二泵站运行规程', filename: 'pump-02-operation.md', version: 'v1.2', category: '规程', status: '现行', date: '2026-08-12', contentLength: 1840, applicability: '二泵站', source: '本地示例' },
  { id: 'local-2', title: '泵组异常处理预案', filename: 'pump-alarm-plan.md', version: 'v0.9', category: '应急预案', status: '待审', date: '2026-10-01', contentLength: 1260, applicability: '全局', source: '本地示例' },
  { id: 'local-3', title: '四泵站 2 号泵维修手册', filename: 'pump-04-maintenance.pdf', version: 'v2.1', category: '手册', status: '废止', date: '2025-12-18', contentLength: 3520, applicability: '四泵站', source: '本地示例' },
]
const statusNames: Record<string, string> = { valid: '现行', pending: '待审', revoked: '废止', archived: '已归档' }
const statusCodes: Record<string, string> = { 现行: 'valid', 待审: 'pending', 废止: 'revoked', 已归档: 'archived' }
const rows = ref<KnowledgeRow[]>(localDocuments.map(document => ({ ...document })))
const query = ref('')
const statusFilter = ref('')
const loading = ref(false)
const searchHits = ref<SearchHit[]>([])
const searchConflicts = ref<SearchConflict[]>([])
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
const askGroundedness = ref('')
const askRetrievalGate = ref('')
const asking = ref(false)
const importForm = reactive({ filename: '', title: '', version: '1.0', category: '规程', content: '', stationIds: '', effectiveFrom: '', effectiveTo: '' })
const csvVisible = ref(false)
const csvLoading = ref(false)
const csvResult = ref<CsvImportResponse | null>(null)
const csvForm = reactive({ filename: 'telemetry.csv', content: 'station_id,observed_at,metric,value,unit\npump-02,2026-10-16T10:00:00Z,flow,1080,m3/h' })
const statusUpdatingId = ref('')
const compareVisible = ref(false)
const compareLoading = ref(false)
const compareTitle = ref('')
const compareResult = ref<{ version: string; compared_version?: string; changed: boolean; diff: string[] } | null>(null)
const excerptVisible = ref(false)
const excerptLoading = ref(false)
const excerptResult = ref<{ title: string; version: string; location: string; chunk_index: number; excerpt: string } | null>(null)
const historyVisible = ref(false)
const historyLoading = ref(false)
const historyTitle = ref('')
const historyRows = ref<KnowledgeAuditEvent[]>([])
const isAdmin = computed(() => {
  return currentUserRole() === 'admin'
})

// 引擎状态只取页面要用的字段，其余忽略，避免把后端结构整体搬进类型。
interface EngineStatus {
  engine_mode?: string
  embedding?: string
  rerank?: string
  rerank_error?: string | null
  chunks?: number
  warmup?: { ok?: boolean; elapsed_seconds?: number | null; error?: string | null }
  index?: { consistent?: boolean; indexed_documents?: number }
}

// 检索诊断面板：只在管理员下显示，用于定位「为什么没命中 / 为什么被拦」。
const debugQuestion = ref('')
const debugging = ref(false)
const debugResult = ref<DiagnoseResult | null>(null)
const engineStatus = ref<EngineStatus | null>(null)
const engineError = ref('')

// 引擎健康度是排查的第一步：退化时其余分数解释都不可信，所以单独给结论。
const engineHealth = computed(() => {
  const status = engineStatus.value
  if (!status) return { level: 'unknown', text: '引擎状态未知' }
  if (status.engine_mode === 'local-hash') {
    return { level: 'bad', text: '哈希向量兜底，检索质量明显下降' }
  }
  if (status.warmup && status.warmup.ok === false) {
    return { level: 'bad', text: `模型未就绪：${status.warmup.error || '未知原因'}` }
  }
  if (status.rerank === 'disabled' || status.rerank === 'pending') {
    return { level: 'warn', text: `重排未生效（${status.rerank}）` }
  }
  if (status.index && status.index.consistent === false) {
    return { level: 'warn', text: '索引与磁盘资料不一致，建议重建' }
  }
  return { level: 'good', text: '向量与重排均已就绪' }
})

// 结论代码决定颜色：ok 绿、门槛拦截琥珀、无候选和空库红。
const loadEngineStatus = async () => {
  if (!isAdmin.value) return
  try {
    engineStatus.value = await fetchRagStatus<EngineStatus>()
    engineError.value = ''
  } catch (error) {
    engineStatus.value = null
    engineError.value = error instanceof Error ? error.message : '引擎状态读取失败'
  }
}

const runDiagnose = async () => {
  const question = debugQuestion.value.trim()
  if (!question) {
    ElMessage.warning('请输入要诊断的问题')
    return
  }
  debugging.value = true
  try {
    debugResult.value = await diagnoseRag<DiagnoseResult>({ question, k: 5 })
  } catch (error) {
    debugResult.value = null
    ElMessage.error(error instanceof Error ? error.message : '诊断接口暂不可用')
  } finally {
    debugging.value = false
    // 每次诊断顺带刷新引擎状态，避免看到过期的「已就绪」。
    await loadEngineStatus()
  }
}

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
  source: backendSourceLabel(document.source),
})

const searchKnowledge = async () => {
  const keyword = query.value.trim()
  if (!keyword) {
    searchHits.value = []
    searchConflicts.value = []
    searchMessage.value = ''
    await loadKnowledge()
    return
  }
  loading.value = true
  try {
    const result = await searchKnowledgeDocuments<{ results: SearchHit[]; conflicts?: SearchConflict[] }>(keyword)
    searchHits.value = result.results
    searchConflicts.value = result.conflicts || []
    searchMessage.value = result.results.length ? `检索到 ${result.results.length} 条来源` : '没有命中现行资料或内置规程'
  } catch {
    searchHits.value = []
    searchConflicts.value = []
    searchMessage.value = '检索接口暂不可用'
    ElMessage.warning('检索接口暂不可用')
  } finally {
    loading.value = false
  }
}

const loadKnowledge = async () => {
  loading.value = true
  try {
    const result = await fetchKnowledgeDocuments<ApiKnowledgeDocument>()
    const kind = classifyRemoteList(result)
    sourceLabel.value = remoteListLabel(kind, result[0]?.source)
    if (kind === 'backend') rows.value = result.map(formatDocument)
    else ElMessage.info('知识库接口当前没有文档，页面暂显示本地示例')
  } catch {
    sourceLabel.value = remoteListLabel('failed')
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
  askGroundedness.value = ''
  askRetrievalGate.value = ''
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
    const result = await askRag<{
      answer: string
      rewritten_query?: string
      session_id?: string
      effective_question?: string
      needs_clarification?: boolean
      clarification?: string
      merged?: boolean
      sources: SearchHit[]
      compression?: { chars_before?: number; chars_after?: number; reduced?: number }
      groundedness?: { grounded?: boolean; overlap?: number; status?: string; warnings?: string[] }
      retrieval_gate?: { passed?: boolean; min_score?: number; top_score?: number }
    }>({ question, k: 5, session_id: askSessionId.value || null })
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
    const groundedness = result.groundedness
    if (groundedness && !result.needs_clarification) {
      const overlapPct = Math.round((groundedness.overlap || 0) * 100)
      askGroundedness.value = groundedness.grounded
        ? `忠实度：通过（重合 ${overlapPct}%）`
        : `忠实度：未通过（重合 ${overlapPct}%）${groundedness.warnings?.length ? `；${groundedness.warnings.join('；')}` : ''}`
    } else {
      askGroundedness.value = ''
    }
    const gate = result.retrieval_gate
    askRetrievalGate.value = gate
      ? (gate.passed
        ? `检索门槛：通过（最高 ${gate.top_score} / 门槛 ${gate.min_score}）`
        : `检索门槛：未通过（最高 ${gate.top_score} / 门槛 ${gate.min_score}）`)
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
    askGroundedness.value = ''
    askRetrievalGate.value = ''
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
    const data = await extractKnowledgeFile<{ filename: string; title: string; content: string; content_length: number; parser: string }>(file)
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
    const result = await importKnowledgeDocument<ApiKnowledgeDocument>({
        filename: importForm.filename,
        title: importForm.title,
        version: importForm.version,
        category: importForm.category,
        content: importForm.content,
        station_ids: importForm.stationIds.split(/[,，\s]+/).map(item => item.trim()).filter(Boolean),
        effective_from: importForm.effectiveFrom ? new Date(importForm.effectiveFrom).toISOString() : null,
        effective_to: importForm.effectiveTo ? new Date(importForm.effectiveTo).toISOString() : null,
    })
    rows.value.unshift(formatDocument(result))
    sourceLabel.value = backendSourceLabel(result.source)
    importVisible.value = false
    ElMessage.success('资料导入成功')
  } catch {
    ElMessage.error('资料导入失败，请检查接口和提交内容')
  } finally {
    importing.value = false
  }
}

const findRow = (id: string) => filteredRows.value.find(row => row.id) || rows.value.find(row => row.id)!

const preview = (row: KnowledgeRow) => {
  ElMessage.info(`${row.title} · ${row.version} · 当前仅展示文档元数据`)
}

const compareVersion = async (row: KnowledgeRow) => {
  if (row.id.startsWith('local-')) {
    ElMessage.info('示例资料没有后端版本记录，请先导入同标题的多版本文档')
    return
  }
  compareTitle.value = `${row.title} · ${row.version}`
  compareVisible.value = true
  compareLoading.value = true
  compareResult.value = null
  try {
    compareResult.value = await compareKnowledgeDocument(row.id)
  } catch {
    ElMessage.error('版本对比失败，请稍后重试')
  } finally {
    compareLoading.value = false
  }
}

const viewExcerpt = async (source: SearchHit) => {
  if (source.chunk_index === null || source.chunk_index === undefined || source.source.startsWith('mock')) {
    ElMessage.info('该引用没有可定位的后端分片')
    return
  }
  excerptVisible.value = true
  excerptLoading.value = true
  excerptResult.value = null
  try {
    excerptResult.value = await fetchKnowledgeExcerpt(source.source_id, source.chunk_index)
  } catch {
    ElMessage.error('原文片段读取失败，请稍后重试')
  } finally {
    excerptLoading.value = false
  }
}

const updateStatus = async (row: KnowledgeRow, displayStatus: string) => {
  if (!isAdmin.value || row.id.startsWith('local-')) {
    ElMessage.info('当前示例资料不能修改状态，请先导入后端文档')
    return
  }
  statusUpdatingId.value = row.id
  try {
    const result = await updateKnowledgeStatus(row.id, statusCodes[displayStatus])
    row.status = statusNames[result.status] || result.status
    ElMessage.success(`资料状态已更新为${row.status}`)
  } catch {
    ElMessage.error('资料状态更新失败，请稍后重试')
  } finally {
    statusUpdatingId.value = ''
  }
}

const viewHistory = async (row: KnowledgeRow) => {
  if (row.id.startsWith('local-')) {
    ElMessage.info('示例资料没有后端审核历史，请先导入后端文档')
    return
  }
  historyTitle.value = `${row.title} · 审核历史`
  historyVisible.value = true
  historyLoading.value = true
  historyRows.value = []
  try {
    historyRows.value = await fetchKnowledgeHistory(row.id)
  } catch {
    ElMessage.error('审核历史读取失败，请稍后重试')
  } finally {
    historyLoading.value = false
  }
}

// 硬删除只对后端文档开放：先二次确认，再调用 DELETE，成功后把行从表格移除。
const removeDocument = async (row: KnowledgeRow) => {
  if (!isAdmin.value || row.id.startsWith('local-')) {
    ElMessage.info('当前示例资料不能删除，请先导入后端文档')
    return
  }
  try {
    await ElMessageBox.confirm(
      `删除《${row.title}》后，向量索引分片和磁盘正文会一并清除，且不可恢复。`,
      '确认删除资料',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  statusUpdatingId.value = row.id
  try {
    await deleteKnowledgeDocument(row.id)
    const index = rows.value.findIndex((item) => item.id === row.id)
    if (index >= 0) rows.value.splice(index, 1)
    ElMessage.success('资料已删除')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '资料删除失败，请稍后重试')
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
    csvResult.value = await validateTelemetryCsv<CsvImportResponse>(csvForm.filename, csvForm.content)
    if (csvResult.value.success) ElMessage.success('CSV 校验通过')
    else ElMessage.warning('CSV 校验发现问题，请查看错误明细')
  } catch {
    ElMessage.error('CSV 校验接口暂不可用')
  } finally {
    csvLoading.value = false
  }
}

// 顶栏刷新同时拉取文档列表和 RAG 引擎状态，避免只刷新一半。
registerPageRefresh(async () => {
  await loadKnowledge()
  await loadEngineStatus()
})

onMounted(() => {
  loadKnowledge()
  // 管理员额外拉一次引擎状态，进入页面即可看到是否退化。
  loadEngineStatus()
})
</script>

<template>
  <div class="page-title">
    <div>
      <h2>知识库与设备资料</h2>
      <p>检索现行规程、设备台账、应急预案和维修记录 · {{ sourceLabel }}</p>
    </div>
    <KnowledgeHeaderActions @import="openImport" @csv="csvVisible = true" />
  </div>

  <KnowledgeDiagnosePanel v-if="isAdmin" v-model:question="debugQuestion" :engine-health="engineHealth" :engine-status="engineStatus" :engine-error="engineError" :debugging="debugging" :debug-result="debugResult" @refresh="loadEngineStatus" @diagnose="runDiagnose" />

  <KnowledgeAskPanel v-model:question="askQuestion" :asking="asking" :needs-clarification="askNeedsClarification" :turns="askTurns" :answer="askAnswer" :rewritten="askRewritten" :retrieval-gate="askRetrievalGate" :compression="askCompression" :groundedness="askGroundedness" :sources="askSources" @ask="askKnowledge" @clear="clearAskSession" @excerpt="viewExcerpt($event as SearchHit)" />

  <div class="panel">
    <KnowledgeFilterBar v-model:query="query" v-model:status="statusFilter" :loading="loading" @search="searchKnowledge" />
    <KnowledgeSearchResults :message="searchMessage" :conflicts="searchConflicts" :hits="searchHits" />
    <KnowledgeDocumentTable :rows="filteredRows" :admin="isAdmin" :updating-id="statusUpdatingId" @preview="preview(findRow($event))" @history="viewHistory(findRow($event))" @compare="compareVersion(findRow($event))" @status="(id, status) => updateStatus(findRow(id), status)" @remove="removeDocument(findRow($event))" />
  </div>

  <KnowledgeCompareDialog
    v-model="compareVisible"
    :title="compareTitle"
    :loading="compareLoading"
    :result="compareResult"
  />

  <KnowledgeExcerptDialog v-model="excerptVisible" :loading="excerptLoading" :result="excerptResult" />

  <KnowledgeImportDialog v-model="importVisible" v-model:form="importForm" :extracting="extracting" :importing="importing" @extract="extractFromFile" @submit="importDocument" />

  <KnowledgeCsvDialog
    v-model="csvVisible"
    v-model:filename="csvForm.filename"
    v-model:content="csvForm.content"
    :loading="csvLoading"
    :result="csvResult"
    @validate="validateCsv"
  />

  <KnowledgeHistoryDialog v-model="historyVisible" :title="historyTitle" :loading="historyLoading" :rows="historyRows" />
</template>
