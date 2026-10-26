<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { currentUserRole } from '../composables/currentUser'
import { backendSourceLabel, remoteListMessage, useDataSource } from '../composables/dataSource'
import { fetchReport, fetchReports, generateReport as generateReportApi, saveReport, updateReportStatus as updateReportStatusApi } from '../api/reports'
import { registerPageRefresh } from '../composables/pageRefresh'
import { formatLocalClock } from '../utils/time'

interface ReportMetric {
  key: string
  label: string
  value: number
  unit: string
  source_ids: string[]
}

interface ApiReport {
  id: string
  report_type: string
  report_date: string
  status: string
  title: string
  summary: string
  from_time?: string
  to_time?: string
  data_version?: string
  created_at: string
  source: string
  metrics?: ReportMetric[]
  source_ids?: string[]
}

// 后端暂时没有记录或接口不可用时，页面继续使用这条本地示例数据展示结构。
const localReport: ApiReport = {
  id: 'local-report',
  report_type: '日报',
  report_date: '2026-10-16',
  status: 'draft',
  title: '今日运行日报 · 草稿',
  summary: '当前显示本地示例报告，点击“生成报告草稿”后请求后端接口。',
  from_time: '2026-10-16T00:00:00Z',
  to_time: '2026-10-16T23:59:59Z',
  data_version: 'local-demo-v1',
  created_at: '2026-10-16T10:46:00Z',
  metrics: [
    { key: 'total_supply', label: '总供水量', value: 18900, unit: 'm3/d', source_ids: ['supply:pump-02', 'supply:pump-03', 'supply:pump-04'] },
    { key: 'total_demand', label: '总需求量', value: 19700, unit: 'm3/d', source_ids: ['supply:pump-02', 'supply:pump-03', 'supply:pump-04'] },
    { key: 'total_balance', label: '供需结余', value: -800, unit: 'm3/d', source_ids: ['supply:pump-02', 'supply:pump-03', 'supply:pump-04'] },
    { key: 'alarm_count', label: '关联告警数', value: 3, unit: '条', source_ids: ['alarm-20261015-001', 'alarm-20261015-002', 'alarm-20261015-003'] },
    { key: 'bottleneck_balance', label: '瓶颈片区：西部片区', value: -600, unit: 'm3/d', source_ids: ['supply:pump-02'] },
  ],
  source_ids: ['supply:pump-02', 'supply:pump-03', 'supply:pump-04', 'alarm-20261015-001', 'alarm-20261015-002', 'alarm-20261015-003'],
  source: '本地示例',
}

// 报告列表用于左侧选择和状态展示，当前选中的记录同步到详情卡片。
const reports = ref<ApiReport[]>([{ ...localReport }])
const report = ref<ApiReport>({ ...localReport })
const selectedReportId = ref(localReport.id)
const listLoading = ref(false)
const loading = ref(false)
const detailLoading = ref(false)
const statusLoading = ref(false)
const generateVisible = ref(false)
const generateSaving = ref(false)
const editVisible = ref(false)
const editSaving = ref(false)
const generateForm = reactive({
  report_type: '日报',
  report_date: new Date().toISOString().slice(0, 10),
  from_time: '00:00',
  to_time: '23:59',
})
// 编辑表单只暂存当前草稿的标题和摘要，确认后再提交到后端。
const editForm = reactive({ title: '', summary: '' })
const { sourceLabel, setBackend, setLocal } = useDataSource()
const statusNames: Record<string, string> = { draft: '草稿', reviewed: '已复核', archived: '已归档' }

// 只有管理员或审核负责人可以调用报告状态更新接口。
const canUpdateStatus = computed(() => {
  try {
    const role = currentUserRole()
    return role === 'admin' || role === 'reviewer'
  } catch {
    return false
  }
})

// 报告生成属于调度工作，审批负责人只负责复核和归档已有报告。
const canGenerateReport = computed(() => {
  try {
    const role = currentUserRole()
    return role === 'admin' || role === 'operator'
  } catch {
    return false
  }
})

// 草稿内容由管理员或调度员维护，审批负责人只处理复核状态。
const canEditContent = computed(() => {
  try {
    const role = currentUserRole()
    return (role === 'admin' || role === 'operator') && isBackendReport.value && report.value.status === 'draft'
  } catch {
    return false
  }
})

// 本地示例只用于展示页面结构，只有后端返回的真实报告才允许修改生命周期。
const isBackendReport = computed(() => !report.value.id.startsWith('local-') && report.value.id !== 'local-report')

// 将后端返回的报告设置为当前详情，并同步列表中的同一条记录。
const setActiveReport = (value: ApiReport) => {
  report.value = value
  selectedReportId.value = value.id
  reports.value = reports.value.map(item => item.id === value.id ? value : item)
}

// 接口没有数据时恢复本地示例，避免页面出现空白详情卡片。
const useLocalReport = () => {
  reports.value = [{ ...localReport }]
  report.value = { ...localReport }
  selectedReportId.value = localReport.id
  setLocal()
}

// 加载报告草稿列表，并默认选中最新返回的第一条记录。
const loadReports = async () => {
  listLoading.value = true
  try {
    const result = await fetchReports<ApiReport>()
    if (result.length) {
      reports.value = result
      setActiveReport(result[0])
      setBackend(backendSourceLabel(result[0].source))
    } else {
      useLocalReport()
      ElMessage.info(remoteListMessage('empty', '报告'))
    }
  } catch {
    useLocalReport()
    ElMessage.warning(remoteListMessage('failed', '报告列表'))
  } finally {
    listLoading.value = false
  }
}

// 点击列表中的报告时切换详情；后端记录会再请求一次详情确保内容最新。
const selectReport = async (value: ApiReport) => {
  setActiveReport(value)
  if (!value.id.startsWith('local-') && value.id !== 'local-report') {
    await refreshReportDetail(value.id, false)
  }
}

const openGenerateDialog = () => {
  generateForm.report_date = new Date().toISOString().slice(0, 10)
  generateForm.from_time = '00:00'
  generateForm.to_time = '23:59'
  generateVisible.value = true
}

// 打开编辑弹窗时复制当前报告内容，取消操作不会改变详情卡片。
const openEditDialog = () => {
  editForm.title = report.value.title
  editForm.summary = report.value.summary
  editVisible.value = true
}

const saveReportContent = async () => {
  if (!canEditContent.value) {
    ElMessage.info('当前账号或报告状态不允许编辑内容')
    return
  }
  if (!editForm.title.trim() || !editForm.summary.trim()) {
    ElMessage.warning('报告标题和摘要不能为空')
    return
  }
  editSaving.value = true
  try {
    const result = await saveReport<ApiReport>(report.value.id, { title: editForm.title, summary: editForm.summary })
    setActiveReport(result)
    editVisible.value = false
    ElMessage.success('报告草稿内容已保存')
  } catch {
    ElMessage.error('报告草稿保存失败，请确认报告仍处于草稿状态')
  } finally {
    editSaving.value = false
  }
}

const generateReport = async () => {
  if (!generateForm.report_date || !generateForm.from_time || !generateForm.to_time) {
    ElMessage.warning('请填写报告日期和统计时间窗')
    return
  }
  if (generateForm.from_time >= generateForm.to_time) {
    ElMessage.warning('统计开始时间必须早于结束时间')
    return
  }
  generateSaving.value = true
  loading.value = true
  try {
    const result = await generateReportApi<ApiReport>({
        report_type: generateForm.report_type,
        report_date: generateForm.report_date,
        from_time: `${generateForm.report_date}T${generateForm.from_time}:00Z`,
        to_time: `${generateForm.report_date}T${generateForm.to_time}:00Z`,
      })
    reports.value = [result, ...reports.value.filter(item => !item.id.startsWith('local-') && item.id !== 'local-report')]
    setActiveReport(result)
    setBackend(backendSourceLabel(result.source))
    ElMessage.success('报告草稿已生成')
    generateVisible.value = false
  } catch {
    useLocalReport()
    ElMessage.warning('报告接口暂不可用，当前保留本地示例')
  } finally {
    generateSaving.value = false
    loading.value = false
  }
}

const refreshReportDetail = async (reportId = report.value.id, showMessage = true) => {
  if (reportId === 'local-report') {
    if (showMessage) ElMessage.info('请先点击“生成报告草稿”后再刷新后端详情')
    return
  }
  detailLoading.value = true
  try {
    const result = await fetchReport<ApiReport>(reportId)
    setActiveReport(result)
    if (showMessage) ElMessage.success('报告详情已刷新')
  } catch {
    if (showMessage) ElMessage.warning('报告详情接口暂不可用，保留生成结果')
  } finally {
    detailLoading.value = false
  }
}

// 更新当前报告的生命周期状态，并把后端返回值同步到列表和详情区域。
const updateReportStatus = async (status: 'reviewed' | 'archived') => {
  if (!canUpdateStatus.value || report.value.id.startsWith('local-') || report.value.id === 'local-report') {
    ElMessage.info('当前账号或本地示例报告不能修改状态')
    return
  }
  statusLoading.value = true
  try {
    const result = await updateReportStatusApi<ApiReport>(report.value.id, status)
    setActiveReport(result)
    ElMessage.success(`报告状态已更新为${statusNames[result.status] || result.status}`)
  } catch {
    ElMessage.error('报告状态更新失败，请刷新后重试')
  } finally {
    statusLoading.value = false
  }
}

// 统一生成当前报告的 Markdown 文本，复制和下载操作共用同一份内容。
const buildMarkdown = () => {
  const metricLines = (report.value.metrics || []).map(metric => `- ${metric.label}：${metric.value} ${metric.unit}`)
  const sourceLine = (report.value.source_ids || []).join(', ') || '无'
  return `# ${report.value.title}\n\n- 日期：${report.value.report_date}\n- 状态：${statusNames[report.value.status] || report.value.status}\n- 统计时间窗：${reportDateTime(report.value.from_time)} 至 ${reportDateTime(report.value.to_time)}\n\n## 摘要\n\n${report.value.summary}\n\n## 核心指标\n\n${metricLines.length ? metricLines.join('\\n') : '- 暂无结构化指标'}\n\n## 数据来源\n\n${sourceLine}`
}

const copyMarkdown = async () => {
  try {
    await navigator.clipboard.writeText(buildMarkdown())
    ElMessage.success('报告 Markdown 已复制')
  } catch {
    ElMessage.warning('浏览器未允许访问剪贴板，请手动复制报告内容')
  }
}

// 使用浏览器本地 Blob 下载 Markdown 文件，不新增后端存储或外部文件接口。
const downloadMarkdown = () => {
  const url = URL.createObjectURL(new Blob([buildMarkdown()], { type: 'text/markdown;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `${report.value.title || '运行报告'}.md`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
  ElMessage.success('报告 Markdown 已下载')
}

const reportTime = (value: string) => formatLocalClock(value)
const reportDateTime = (value?: string) => value ? value.replace('T', ' ').replace('Z', '') : '—'

// 顶栏刷新复用列表加载逻辑；页面内的“刷新列表”“刷新报告详情”保持原样。
registerPageRefresh(loadReports)
// 页面进入报告中心时立即拉取后端列表。
onMounted(loadReports)
</script>

<template>
  <div class="page-title">
    <div>
      <h2>报告与交接班</h2>
      <p>日报、周报和交接班摘要草稿 · 自动汇总内容待人工确认 · {{ sourceLabel }}</p>
    </div>
    <el-button v-if="canGenerateReport" class="report-generate-button" type="primary" :loading="loading" @click="openGenerateDialog">生成报告草稿</el-button>
    <span v-else class="tag tag-gray">审批负责人只读复核</span>
  </div>

  <div class="panel" style="margin-bottom:16px">
    <div class="panel-head">
      <h3>报告草稿列表</h3>
      <el-button class="report-list-button" plain size="small" :loading="listLoading" @click="loadReports">刷新列表</el-button>
    </div>
    <div class="table-wrap">
      <el-table :data="reports" row-key="id" :current-row-key="selectedReportId" highlight-current-row @row-click="selectReport">
        <el-table-column prop="title" label="报告名称" min-width="220" />
        <el-table-column prop="report_date" label="业务日期" width="120" />
        <el-table-column label="状态" width="100">
          <template #default="scope"><span :class="['tag', scope.row.status === 'archived' ? 'tag-gray' : scope.row.status === 'reviewed' ? 'tag-green' : 'tag-amber']">{{ statusNames[scope.row.status] || scope.row.status }}</span></template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="120" />
        <el-table-column label="操作" width="90">
          <template #default="scope"><el-button link type="primary" @click.stop="selectReport(scope.row as ApiReport)">查看</el-button></template>
        </el-table-column>
      </el-table>
    </div>
  </div>

  <div class="grid grid-2">
    <div class="panel">
      <div class="panel-head">
        <h3>{{ report.title }}</h3>
        <span>{{ report.report_date }} · {{ statusNames[report.status] || report.status }}</span>
      </div>
      <div class="table-wrap">
        <p class="muted">报告摘要</p>
        <p>{{ report.summary }}</p>
        <p class="muted">核心指标</p>
        <div v-if="report.metrics?.length" class="report-metrics">
          <div v-for="metric in report.metrics" :key="metric.key" class="report-metric">
            <span>{{ metric.label }}</span>
            <strong>{{ Number(metric.value).toLocaleString(undefined, { maximumFractionDigits: String(metric.unit).includes('MPa') ? 2 : 0 }) }} {{ metric.unit }}</strong>
          </div>
        </div>
        <p v-else class="muted">当前报告没有结构化指标。</p>
        <p class="muted">数据来源</p>
        <p class="report-source-ids">{{ report.source_ids?.join('、') || '暂无来源编号' }}</p>
        <p class="muted">供水量摘要</p>
        <p>今日累计供水量 24,860 m3，较昨日同期上升 4.2%。</p>
        <p class="muted">关键告警</p>
        <p>二泵站流量偏低，关联西部片区压力下降，待值班人员核查。</p>
        <p class="muted">生成信息</p>
        <p>{{ reportTime(report.created_at) }} · {{ sourceLabel }}</p>
        <p class="muted">统计时间窗</p>
        <p>{{ reportDateTime(report.from_time) }} 至 {{ reportDateTime(report.to_time) }}</p>
        <p class="muted">数据版本</p>
        <p>{{ report.data_version || '—' }}</p>
        <div class="report-actions">
          <el-button class="report-copy-button" plain @click="copyMarkdown">复制 Markdown</el-button>
          <el-button class="report-download-button" plain @click="downloadMarkdown">下载 Markdown</el-button>
          <el-button class="report-detail-button" plain :loading="detailLoading" @click="refreshReportDetail()">刷新报告详情</el-button>
          <el-button v-if="canEditContent" class="report-edit-button" plain @click="openEditDialog">编辑内容</el-button>
          <el-button class="report-status-button" v-if="canUpdateStatus && isBackendReport && report.status === 'draft'" type="success" plain :loading="statusLoading" @click="updateReportStatus('reviewed')">标记已复核</el-button>
          <el-button class="report-status-button" v-if="canUpdateStatus && isBackendReport && report.status === 'reviewed'" type="warning" plain :loading="statusLoading" @click="updateReportStatus('archived')">归档报告</el-button>
        </div>
        <p v-if="canUpdateStatus && !isBackendReport" class="muted report-status-hint">当前为本地示例，请先生成报告草稿后再修改状态。</p>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head">
        <h3>交接班事项</h3>
        <span>未闭环 3 项</span>
      </div>
      <div class="table-wrap">
        <el-timeline>
          <el-timeline-item timestamp="10:42" type="warning">二泵站流量告警待确认</el-timeline-item>
          <el-timeline-item timestamp="09:30">西部片区方案 A 待审批</el-timeline-item>
          <el-timeline-item timestamp="08:00" type="success">早班巡检记录已归档</el-timeline-item>
        </el-timeline>
      </div>
    </div>
  </div>

  <el-dialog v-model="generateVisible" title="生成报告草稿" width="520px">
    <el-form label-width="100px">
      <el-form-item label="报告类型"><el-select v-model="generateForm.report_type" style="width:100%"><el-option label="日报" value="日报" /><el-option label="周报" value="周报" /><el-option label="交接班报告" value="交接班报告" /></el-select></el-form-item>
      <el-form-item label="业务日期"><el-input v-model="generateForm.report_date" type="date" /></el-form-item>
      <el-form-item label="开始时间"><el-input v-model="generateForm.from_time" type="time" /></el-form-item>
      <el-form-item label="结束时间"><el-input v-model="generateForm.to_time" type="time" /></el-form-item>
    </el-form>
    <p class="muted">当前时间窗写入报告记录，不按历史监测重新计算。</p>
    <template #footer>
      <el-button @click="generateVisible = false">取消</el-button>
      <el-button class="button-stable button-stable--md" type="primary" :loading="generateSaving" @click="generateReport">确认生成</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="editVisible" title="编辑报告草稿" width="620px">
    <el-form label-width="80px">
      <el-form-item label="标题"><el-input v-model="editForm.title" maxlength="120" show-word-limit /></el-form-item>
      <el-form-item label="摘要"><el-input v-model="editForm.summary" type="textarea" :rows="6" maxlength="2000" show-word-limit /></el-form-item>
    </el-form>
    <p class="muted">仅草稿状态允许编辑；提交复核后需要通过状态流程继续处理。</p>
    <template #footer>
      <el-button @click="editVisible = false">取消</el-button>
      <el-button class="button-stable button-stable--md" type="primary" :loading="editSaving" @click="saveReportContent">保存内容</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
/* 为带 loading 状态的报告按钮保留固定宽度，避免点击后文字和布局跳动。 */
.report-generate-button { width: 146px; }
.report-list-button { width: 82px; }
.report-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
.report-actions .el-button { margin-left: 0; }
.report-metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin: 8px 0 16px; }
.report-metric { display: flex; justify-content: space-between; gap: 12px; padding: 10px 12px; border: 1px solid var(--line, #e5e7eb); border-radius: 8px; background: var(--panel-soft, #f8fafc); }
.report-metric span { color: var(--text-muted, #64748b); }
.report-metric strong { color: var(--text-primary, #1f2937); }
.report-source-ids { word-break: break-word; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: var(--text-muted, #64748b); }
.report-copy-button { width: 112px; }
.report-download-button { width: 112px; }
.report-detail-button { width: 128px; }
.report-edit-button { width: 96px; }
.report-status-button { width: 112px; }
</style>
