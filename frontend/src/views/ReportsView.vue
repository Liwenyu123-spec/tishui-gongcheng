<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/http'

interface ApiReport {
  id: string
  report_type: string
  report_date: string
  status: string
  title: string
  summary: string
  created_at: string
  source: string
}

const report = ref<ApiReport>({
  id: 'local-report',
  report_type: '日报',
  report_date: '2026-10-16',
  status: 'draft',
  title: '今日运行日报 · 草稿',
  summary: '当前显示本地示例报告，点击“生成报告草稿”后请求后端接口。',
  created_at: '2026-10-16T10:46:00Z',
  source: '本地示例',
})
const loading = ref(false)
const sourceLabel = ref('本地示例')
const statusNames: Record<string, string> = { draft: '草稿', reviewed: '已复核' }

const generateReport = async () => {
  loading.value = true
  try {
    const result = await api<ApiReport>('/api/v1/reports/generate', {
      method: 'POST',
      body: JSON.stringify({ report_type: '日报' }),
    })
    report.value = result
    sourceLabel.value = result.source === 'mock' ? '后端 Mock 数据' : result.source
    ElMessage.success('报告草稿已生成')
  } catch {
    sourceLabel.value = '本地示例'
    ElMessage.warning('报告接口暂不可用，当前保留本地示例')
  } finally {
    loading.value = false
  }
}

const reportTime = (value: string) => value.slice(11, 16)
</script>

<template>
  <div class="page-title">
    <div>
      <h2>报告与交接班</h2>
      <p>日报、周报和交接班摘要草稿 · 自动汇总内容待人工确认 · {{ sourceLabel }}</p>
    </div>
    <el-button type="primary" :loading="loading" @click="generateReport">生成报告草稿</el-button>
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
        <p class="muted">供水量摘要</p>
        <p>今日累计供水量 24,860 m³，较昨日同期上升 4.2%。</p>
        <p class="muted">关键告警</p>
        <p>二泵站流量偏低，关联西部片区压力下降，待值班人员核查。</p>
        <p class="muted">生成信息</p>
        <p>{{ reportTime(report.created_at) }} · {{ sourceLabel }}</p>
        <el-button plain>复制 Markdown</el-button>
        <el-button plain>打印预览</el-button>
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
</template>
