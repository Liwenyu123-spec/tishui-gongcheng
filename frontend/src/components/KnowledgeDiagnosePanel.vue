<script setup lang="ts">
defineProps<{
  engineHealth: { level: string; text: string }
  engineStatus: {
    engine_mode?: string
    rerank?: string
    chunks?: number
    warmup?: { elapsed_seconds?: number | null }
  } | null
  engineError: string
  debugging: boolean
  debugResult: {
    reason: string
    verdict: string
    elapsed_ms: number
    reason_text: string
    environment_notes: string[]
    notes: string[]
    gate: {
      min_score?: number
      min_rerank?: number | null
      top_score?: number
      top_rerank?: number | null
      kept?: number
      total?: number
    } | null
    hits: Array<{
      title: string
      location: string
      category: string
      score: number
      rerank: number | null
      passed: boolean
      components: {
        lexical?: number
        vector_similarity?: number
        vector_bonus?: number
        bm25_raw?: number
        bm25_bonus?: number
        candidate_from?: string
      }
    }>
  } | null
}>()

const debugQuestion = defineModel<string>('question', { required: true })
const emit = defineEmits<{ refresh: []; diagnose: [] }>()

const reasonTag = (reason: string) => {
  if (reason === 'ok') return 'tag-green'
  if (reason === 'gate_score' || reason === 'gate_rerank' || reason === 'below_rerank') return 'tag-amber'
  return 'tag-red'
}
</script>

<template>
  <div class="panel" style="margin-bottom:16px;padding:16px 18px">
    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px">
      <strong>检索诊断</strong>
      <span :class="['tag', engineHealth.level === 'good' ? 'tag-green' : engineHealth.level === 'warn' ? 'tag-amber' : engineHealth.level === 'bad' ? 'tag-red' : '']">{{ engineHealth.text }}</span>
      <span v-if="engineStatus" class="muted" style="font-size:12px">
        引擎 {{ engineStatus.engine_mode || '未知' }} · 分片 {{ engineStatus.chunks ?? 0 }} ·
        重排 {{ engineStatus.rerank || '未知' }} ·
        预热 {{ engineStatus.warmup?.elapsed_seconds != null ? `${engineStatus.warmup.elapsed_seconds}s` : '未执行' }}
      </span>
      <el-button link type="primary" @click="emit('refresh')">刷新状态</el-button>
    </div>
    <p v-if="engineError" class="muted">引擎状态读取失败：{{ engineError }}</p>
    <div class="filterbar" style="padding:0">
      <el-input v-model="debugQuestion" placeholder="输入一条问句，看它为什么命中或为什么被拦" style="max-width:520px" clearable @keyup.enter="emit('diagnose')" />
      <el-button class="button-stable button-stable--sm" type="primary" :loading="debugging" @click="emit('diagnose')">诊断</el-button>
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
          <template #default="s"><span :class="['tag', s.row.passed ? 'tag-green' : 'tag-red']">{{ s.row.passed ? '可引用' : '拦下' }}</span></template>
        </el-table-column>
        <el-table-column label="资料" min-width="180">
          <template #default="s"><div>{{ s.row.title }}</div><div class="muted" style="font-size:12px">{{ s.row.location }} · {{ s.row.category || '规程' }}</div></template>
        </el-table-column>
        <el-table-column label="总分" width="70" prop="score" />
        <el-table-column label="关键词" width="80"><template #default="s">{{ s.row.components.lexical ?? '-' }}</template></el-table-column>
        <el-table-column label="向量相似度" width="104">
          <template #default="s">{{ s.row.components.vector_similarity ?? '-' }} <span class="muted" style="font-size:11px">+{{ s.row.components.vector_bonus ?? 0 }}</span></template>
        </el-table-column>
        <el-table-column label="BM25" width="96">
          <template #default="s">{{ s.row.components.bm25_raw ?? '-' }} <span class="muted" style="font-size:11px">+{{ s.row.components.bm25_bonus ?? 0 }}</span></template>
        </el-table-column>
        <el-table-column label="重排概率" width="92"><template #default="s">{{ s.row.rerank ?? '未启用' }}</template></el-table-column>
        <el-table-column label="候选来源" width="90"><template #default="s">{{ s.row.components.candidate_from || '-' }}</template></el-table-column>
      </el-table>
      <p v-else class="muted" style="margin-top:10px">没有候选片段，检索在这一步就没有拿到任何结果。</p>
    </div>
  </div>
</template>
