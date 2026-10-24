<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api/http'
import { registerPageRefresh } from '../composables/pageRefresh'

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
const csvForm = reactive({ filename: 'telemetry.csv', content: 'station_id,observed_at,metric,value,unit\npump-02,2026-10-16T10:00:00Z,flow,1080,m³/h' })
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
const historyRows = ref<Array<{ action?: string; detail?: string; created_at?: string; actor?: string }>>([])
const isAdmin = computed(() => {
  try {
    return JSON.parse(localStorage.getItem('current_user') || '{}').role === 'admin'
  } catch {
    return false
  }
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
const reasonTag = (reason: string) => {
  if (reason === 'ok') return 'tag-green'
  if (reason === 'gate_score' || reason === 'gate_rerank' || reason === 'below_rerank') return 'tag-amber'
  return 'tag-red'
}

const loadEngineStatus = async () => {
  if (!isAdmin.value) return
  try {
    engineStatus.value = await api<EngineStatus>('/api/v1/knowledge/rag/status')
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
    debugResult.value = await api<DiagnoseResult>('/api/v1/knowledge/rag/debug', {
      method: 'POST',
      body: JSON.stringify({ question, k: 5 }),
    })
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
  source: document.source === 'mock' ? '后端 Mock' : document.source,
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
    const result = await api<{ results: SearchHit[]; conflicts?: SearchConflict[] }>(`/api/v1/knowledge/search?q=${encodeURIComponent(keyword)}`)
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
      groundedness?: { grounded?: boolean; overlap?: number; status?: string; warnings?: string[] }
      retrieval_gate?: { passed?: boolean; min_score?: number; top_score?: number }
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
    compareResult.value = await api(`/api/v1/knowledge/${encodeURIComponent(row.id)}/compare`)
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
    excerptResult.value = await api(`/api/v1/knowledge/${encodeURIComponent(source.source_id)}/excerpt?chunk_index=${source.chunk_index}`)
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
    historyRows.value = await api<typeof historyRows.value>(`/api/v1/knowledge/${encodeURIComponent(row.id)}/history`)
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
    await api<{ success: boolean }>(`/api/v1/knowledge/${encodeURIComponent(row.id)}`, { method: 'DELETE' })
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
    <div><el-button type="primary" plain @click="openImport">导入资料</el-button><el-button plain @click="csvVisible = true">校验遥测 CSV</el-button></div>
  </div>

  <!-- 检索诊断仅管理员可见：响应含分片摘要和召回细节，属于内部排障信息。 -->
  <div v-if="isAdmin" class="panel" style="margin-bottom:16px;padding:16px 18px">
    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px">
      <strong>检索诊断</strong>
      <span :class="['tag', engineHealth.level === 'good' ? 'tag-green' : engineHealth.level === 'warn' ? 'tag-amber' : engineHealth.level === 'bad' ? 'tag-red' : '']">{{ engineHealth.text }}</span>
      <span v-if="engineStatus" class="muted" style="font-size:12px">
        引擎 {{ engineStatus.engine_mode || '未知' }} · 分片 {{ engineStatus.chunks ?? 0 }} ·
        重排 {{ engineStatus.rerank || '未知' }} ·
        预热 {{ engineStatus.warmup?.elapsed_seconds != null ? `${engineStatus.warmup.elapsed_seconds}s` : '未执行' }}
      </span>
      <el-button link type="primary" @click="loadEngineStatus">刷新状态</el-button>
    </div>
    <p v-if="engineError" class="muted">引擎状态读取失败：{{ engineError }}</p>
    <div class="filterbar" style="padding:0">
      <el-input
        v-model="debugQuestion"
        placeholder="输入一条问句，看它为什么命中或为什么被拦"
        style="max-width:520px"
        clearable
        @keyup.enter="runDiagnose"
      />
      <el-button class="button-stable button-stable--sm" type="primary" :loading="debugging" @click="runDiagnose">诊断</el-button>
    </div>

    <div v-if="debugResult" style="margin-top:14px">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <span :class="['tag', reasonTag(debugResult.reason)]">{{ debugResult.reason }}</span>
        <strong>{{ debugResult.verdict }}</strong>
        <span class="muted" style="font-size:12px">耗时 {{ debugResult.elapsed_ms }}ms</span>
      </div>
      <p class="muted" style="margin:6px 0">{{ debugResult.reason_text }}</p>

      <div v-if="debugResult.gate" class="muted" style="font-size:12px">
        门槛：分数 ≥ {{ debugResult.gate.min_score }}
        <template v-if="debugResult.gate.min_rerank != null">、重排 ≥ {{ debugResult.gate.min_rerank }}</template>
        ｜Top1 分数 {{ debugResult.gate.top_score }}、重排 {{ debugResult.gate.top_rerank ?? '未启用' }}
        ｜{{ debugResult.gate.kept }}/{{ debugResult.gate.total }} 条可引用
      </div>

      <div v-if="debugResult.environment_notes.length" style="margin-top:8px">
        <p v-for="note in debugResult.environment_notes" :key="note" class="muted" style="color:#f5c578">· {{ note }}</p>
      </div>

      <div v-if="debugResult.notes.length" style="margin-top:8px">
        <p v-for="note in debugResult.notes" :key="note" class="muted">· {{ note }}</p>
      </div>

      <el-table v-if="debugResult.hits.length" :data="debugResult.hits" style="margin-top:12px" size="small">
        <el-table-column label="结果" width="72">
          <template #default="s">
            <span :class="['tag', s.row.passed ? 'tag-green' : 'tag-red']">{{ s.row.passed ? '可引用' : '拦下' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="资料" min-width="180">
          <template #default="s">
            <div>{{ s.row.title }}</div>
            <div class="muted" style="font-size:12px">{{ s.row.location }} · {{ s.row.category || '规程' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="总分" width="70" prop="score" />
        <el-table-column label="关键词" width="80">
          <template #default="s">{{ s.row.components.lexical ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="向量相似度" width="104">
          <template #default="s">
            {{ s.row.components.vector_similarity ?? '-' }}
            <span class="muted" style="font-size:11px">+{{ s.row.components.vector_bonus ?? 0 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="BM25" width="96">
          <template #default="s">
            {{ s.row.components.bm25_raw ?? '-' }}
            <span class="muted" style="font-size:11px">+{{ s.row.components.bm25_bonus ?? 0 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重排概率" width="92">
          <template #default="s">{{ s.row.rerank ?? '未启用' }}</template>
        </el-table-column>
        <el-table-column label="候选来源" width="90">
          <template #default="s">{{ s.row.components.candidate_from || '-' }}</template>
        </el-table-column>
      </el-table>
      <p v-else class="muted" style="margin-top:10px">没有候选片段，检索在这一步就没有拿到任何结果。</p>
    </div>
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
      <p v-if="askRetrievalGate" class="muted">{{ askRetrievalGate }}</p>
      <p v-if="askCompression" class="muted">{{ askCompression }}</p>
      <p v-if="askGroundedness" class="muted">{{ askGroundedness }}</p>
      <p v-for="source in askSources" :key="source.source_id" class="muted">引用{{ source.rank ? ` ${source.rank}` : '' }}：{{ source.title }} · {{ source.location }}<template v-if="source.chunk_index !== null && source.chunk_index !== undefined"> · 分片 {{ source.chunk_index + 1 }}</template><template v-if="source.rerank !== null && source.rerank !== undefined"> · 重排 {{ source.rerank }}</template><el-button v-if="source.chunk_index !== null && source.chunk_index !== undefined" link type="primary" size="small" @click="viewExcerpt(source)">查看原文</el-button></p>
    </div>
    <div v-if="askNeedsClarification && (askRetrievalGate || askSources.length)" style="margin-top:8px">
      <p v-if="askRetrievalGate" class="muted">{{ askRetrievalGate }}</p>
      <p v-for="source in askSources" :key="`weak-${source.source_id}`" class="muted">弱相关：{{ source.title }} · 相关度 {{ source.score }}</p>
    </div>
  </div>

  <div class="panel">
    <div class="filterbar" style="padding:16px 18px 0">
      <el-input v-model="query" placeholder="搜索规程、设备或异常处理方法" style="max-width:430px" clearable />
      <el-select v-model="statusFilter" placeholder="资料状态" clearable style="width:130px">
        <el-option label="现行" value="现行" />
        <el-option label="待审" value="待审" />
        <el-option label="废止" value="废止" />
        <el-option label="已归档" value="已归档" />
      </el-select>
      <el-button class="button-stable button-stable--sm" type="primary" :loading="loading" @click="searchKnowledge">检索</el-button>
    </div>
    <div v-if="searchMessage" style="padding:12px 18px 0">
      <p class="muted">{{ searchMessage }}</p>
      <div v-if="searchConflicts.length" class="panel" style="margin-top:8px;padding:12px 14px;border:1px solid #d97706">
        <strong style="color:#d97706">发现引用冲突，请人工核对</strong>
        <p v-for="(conflict, index) in searchConflicts" :key="`${conflict.source_ids.join('-')}-${index}`" class="muted">{{ conflict.reason }} 来源：{{ conflict.source_ids.join('、') }}</p>
      </div>
      <div v-for="hit in searchHits" :key="`${hit.source_id}-${hit.chunk_index}`" class="panel" style="margin-top:8px;padding:12px 14px">
        <strong>{{ hit.title }}</strong>
        <p class="muted">{{ hit.category || '规程' }} · {{ hit.filename || '无文件名' }} · {{ hit.version }} · {{ hit.location }} · {{ hit.station_ids.length ? hit.station_ids.join('、') : '全局' }} · 相关度 {{ hit.score }}<template v-if="hit.rerank !== null && hit.rerank !== undefined"> · 重排 {{ hit.rerank }}</template> · {{ hit.confidence === 'low' ? '低置信' : '可引用' }}</p>
        <p>{{ hit.detail }}</p>
        <p v-if="hit.context_excerpt" class="muted">上下文：{{ hit.context_excerpt }}</p>
        <p v-if="hit.matched_terms?.length" class="muted">命中词：{{ hit.matched_terms.join('、') }}</p>
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
          <template #default="s"><span :class="['tag',s.row.status==='现行'?'tag-green':s.row.status==='待审'?'tag-amber':s.row.status==='已归档'?'tag-gray':'tag-red']">{{s.row.status}}</span></template>
        </el-table-column>
        <el-table-column label="操作" width="290">
          <template #default="s">
              <el-button link type="primary" @click="preview(s.row)">预览引用</el-button>
              <el-button v-if="!s.row.id.startsWith('local-')" link type="info" @click="viewHistory(s.row)">审核历史</el-button>
            <el-button v-if="!s.row.id.startsWith('local-')" link type="primary" @click="compareVersion(s.row)">版本对比</el-button>
            <template v-if="isAdmin && !s.row.id.startsWith('local-')">
              <el-button link type="success" :disabled="statusUpdatingId === s.row.id" @click="updateStatus(s.row, '现行')">现行</el-button>
              <el-button link type="warning" :disabled="statusUpdatingId === s.row.id" @click="updateStatus(s.row, '待审')">待审</el-button>
              <el-button link type="danger" :disabled="statusUpdatingId === s.row.id" @click="updateStatus(s.row, '废止')">废止</el-button>
              <el-button link type="info" :disabled="statusUpdatingId === s.row.id" @click="updateStatus(s.row, '已归档')">归档</el-button>
              <el-button link type="danger" :disabled="statusUpdatingId === s.row.id" @click="removeDocument(s.row)">删除</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>

  <el-dialog v-model="compareVisible" :title="`版本对比：${compareTitle}`" width="720px">
    <div v-loading="compareLoading">
      <p v-if="compareResult && !compareResult.compared_version" class="muted">没有找到同标题的其他版本。</p>
      <template v-else-if="compareResult">
        <p class="muted">当前版本 {{ compareResult.version }} · 对比版本 {{ compareResult.compared_version }} · {{ compareResult.changed ? '正文有变化' : '正文无变化' }}</p>
        <pre v-if="compareResult.diff.length" class="diff-preview">{{ compareResult.diff.join('\n') }}</pre>
      </template>
    </div>
    <template #footer><el-button @click="compareVisible = false">关闭</el-button></template>
  </el-dialog>

  <el-dialog v-model="excerptVisible" title="引用原文片段" width="720px">
    <div v-loading="excerptLoading">
      <template v-if="excerptResult">
        <p class="muted">{{ excerptResult.title }} · {{ excerptResult.version }} · {{ excerptResult.location }} · 分片 {{ excerptResult.chunk_index + 1 }}</p>
        <pre class="diff-preview">{{ excerptResult.excerpt }}</pre>
      </template>
    </div>
    <template #footer><el-button @click="excerptVisible = false">关闭</el-button></template>
  </el-dialog>

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

  <el-dialog v-model="historyVisible" :title="historyTitle" width="720px">
    <el-skeleton v-if="historyLoading" :rows="4" animated />
    <el-empty v-else-if="!historyRows.length" description="暂无审核历史" />
    <el-timeline v-else>
      <el-timeline-item v-for="(item, index) in historyRows" :key="`${item.created_at || 'event'}-${index}`" :timestamp="item.created_at || '时间未知'">
        <strong>{{ item.action || '生命周期变更' }}</strong>
        <p class="muted">{{ item.detail || '无详细说明' }}<template v-if="item.actor"> · 操作人：{{ item.actor }}</template></p>
      </el-timeline-item>
    </el-timeline>
    <template #footer><el-button @click="historyVisible = false">关闭</el-button></template>
  </el-dialog>
</template>
