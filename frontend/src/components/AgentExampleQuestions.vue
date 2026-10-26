<script setup lang="ts">
const questions = ['现在四泵站出水流量是多少？', '过去 2 小时哪个泵站压力波动最大？', '二泵站流量下降后先核查什么？']
const emit = defineEmits<{ ask: [question: string] }>()
</script>

<template>
  <div class="table-wrap">
    <el-button v-for="question in questions" :key="question" style="width:100%;margin-bottom:9px;text-align:left" @click="emit('ask', question)">{{ question }}</el-button>
    <div class="warning" style="margin-top:8px">控制边界：涉及启动/停止泵、切阀或压力设定的请求将被拒绝，不生成控制命令。</div>
  </div>
</template>
