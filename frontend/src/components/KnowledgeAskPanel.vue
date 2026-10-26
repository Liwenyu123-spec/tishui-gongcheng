<script setup lang="ts">
defineProps<{
  asking: boolean
  needsClarification: boolean
  turns: { role: string; text: string }[]
  answer: string
  rewritten: string
  retrievalGate: string
  compression: string
  groundedness: string
  sources: Array<{ source_id: string; title: string; location: string; chunk_index: number | null; rerank?: number | null; rank?: number; score: number }>
}>()
const question = defineModel<string>('question', { required: true })
const emit = defineEmits<{ ask: []; clear: []; excerpt: [source: { source_id: string; chunk_index: number | null; source: string }] }>()
</script>

<template>
  <div class="panel" style="margin-bottom:16px;padding:16px 18px">
    <p class="muted">规程说明：根据现行检索片段生成，不查询实时测点。缺泵站时可多轮补问。</p>
    <div class="filterbar" style="padding:0">
      <el-input v-model="question" :placeholder="needsClarification ? '例如直接回复：二泵站' : (turns.length ? '可继续追问，例如：那电流呢' : '例如：流量下降后按规程先核查什么')" style="max-width:520px" clearable @keyup.enter="emit('ask')" />
      <el-button class="button-stable button-stable--sm" type="primary" :loading="asking" @click="emit('ask')">{{ needsClarification ? '继续' : '生成说明' }}</el-button>
      <el-button class="button-stable button-stable--sm" plain :disabled="asking" @click="emit('clear')">新对话</el-button>
    </div>
    <div v-if="turns.length" style="margin-top:12px">
      <p v-for="(turn, index) in turns" :key="`${turn.role}-${index}`" class="muted">{{ turn.role }}：{{ turn.text }}</p>
    </div>
    <div v-if="answer && !needsClarification" style="margin-top:12px">
      <p v-if="rewritten" class="muted">检索问法：{{ rewritten }}</p>
      <p v-if="retrievalGate" class="muted">{{ retrievalGate }}</p>
      <p v-if="compression" class="muted">{{ compression }}</p>
      <p v-if="groundedness" class="muted">{{ groundedness }}</p>
      <p v-for="source in sources" :key="source.source_id" class="muted">引用{{ source.rank ? ` ${source.rank}` : '' }}：{{ source.title }} · {{ source.location }}<template v-if="source.chunk_index !== null && source.chunk_index !== undefined"> · 分片 {{ source.chunk_index + 1 }}</template><template v-if="source.rerank !== null && source.rerank !== undefined"> · 重排 {{ source.rerank }}</template><el-button v-if="source.chunk_index !== null && source.chunk_index !== undefined" link type="primary" size="small" @click="emit('excerpt', source as never)">查看原文</el-button></p>
    </div>
    <div v-if="needsClarification && (retrievalGate || sources.length)" style="margin-top:8px">
      <p v-if="retrievalGate" class="muted">{{ retrievalGate }}</p>
      <p v-for="source in sources" :key="`weak-${source.source_id}`" class="muted">弱相关：{{ source.title }} · 相关度 {{ source.score }}</p>
    </div>
  </div>
</template>
