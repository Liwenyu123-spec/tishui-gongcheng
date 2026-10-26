<script setup lang="ts">
defineProps<{
  message: string
  conflicts: Array<{ source_ids: string[]; reason: string }>
  hits: Array<{
    source_id: string
    chunk_index: number | null
    title: string
    category: string
    filename: string
    version: string
    location: string
    station_ids: string[]
    score: number
    rerank?: number | null
    confidence: string
    detail: string
    context_excerpt?: string
    matched_terms?: string[]
  }>
}>()

const highlightExcerpt = (text: string, terms: string[] = []) => {
  const escaped = text.replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character] || character))
  const usableTerms = terms.filter(term => term.trim()).map(term => term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  if (!usableTerms.length) return escaped
  return escaped.replace(new RegExp(`(${usableTerms.join('|')})`, 'gi'), '<mark>$1</mark>')
}
</script>

<template>
  <div v-if="message" style="padding:12px 18px 0">
    <p class="knowledge-status-strip">{{ message }}<template v-if="conflicts.length"> · 冲突 {{ conflicts.length }} 条，需人工核对</template></p>
    <div v-if="conflicts.length" class="panel" style="margin-top:8px;padding:12px 14px;border:1px solid #d97706">
      <strong style="color:#d97706">发现引用冲突，请人工核对</strong>
      <p v-for="(conflict, index) in conflicts" :key="`${conflict.source_ids.join('-')}-${index}`" class="muted">{{ conflict.reason }} 来源：{{ conflict.source_ids.join('、') }}</p>
    </div>
    <div v-for="hit in hits" :key="`${hit.source_id}-${hit.chunk_index}`" class="panel" style="margin-top:8px;padding:12px 14px">
      <strong>{{ hit.title }}</strong>
      <p class="muted">{{ hit.category || '规程' }} · {{ hit.filename || '无文件名' }} · {{ hit.version }} · 定位：{{ hit.location }} · {{ hit.station_ids.length ? hit.station_ids.join('、') : '全局' }} · 相关度 {{ hit.score }}<template v-if="hit.rerank !== null && hit.rerank !== undefined"> · 重排 {{ hit.rerank }}</template> · {{ hit.confidence === 'low' ? '低置信' : '可引用' }}</p>
      <p>{{ hit.detail }}</p>
      <p v-if="hit.context_excerpt" class="muted">上下文：<span v-html="highlightExcerpt(hit.context_excerpt, hit.matched_terms)"></span></p>
      <p v-if="hit.matched_terms?.length" class="muted">命中词：{{ hit.matched_terms.join('、') }}</p>
    </div>
  </div>
</template>

<style scoped>
.knowledge-status-strip { margin: 0 0 8px; padding: 8px 10px; border-radius: 6px; background: #12384a; color: #d7ecf4; }
</style>
