<script setup lang="ts">
defineProps<{
  extracting: boolean
  importing: boolean
}>()

const visible = defineModel<boolean>({ default: false })
const form = defineModel<Record<string, string>>('form', { required: true })
const emit = defineEmits<{ extract: [event: Event]; submit: [] }>()
</script>

<template>
  <el-dialog v-model="visible" title="导入知识资料" width="520px">
    <el-form label-width="90px">
      <el-form-item label="上传文件">
        <input type="file" accept=".txt,.md,.html,.htm,.pdf,.docx" :disabled="extracting" @change="emit('extract', $event)" />
        <p class="muted">支持 PDF、Word、Markdown 和文本；抽出正文后仍需确认导入，新资料默认为待审。</p>
      </el-form-item>
      <el-form-item label="文件名"><el-input v-model="form.filename" placeholder="例如 pump-02-operation.md" /></el-form-item>
      <el-form-item label="资料名称"><el-input v-model="form.title" placeholder="例如二泵站运行规程" /></el-form-item>
      <el-form-item label="版本"><el-input v-model="form.version" /></el-form-item>
      <el-form-item label="类别">
        <el-select v-model="form.category" style="width:100%">
          <el-option label="规程" value="规程" /><el-option label="手册" value="手册" /><el-option label="台账" value="台账" /><el-option label="维修记录" value="维修记录" /><el-option label="应急预案" value="应急预案" />
        </el-select>
      </el-form-item>
      <el-form-item label="适用站点"><el-input v-model="form.stationIds" placeholder="例如 pump-02；留空表示全局" /></el-form-item>
      <el-form-item label="生效时间"><el-input v-model="form.effectiveFrom" type="datetime-local" /></el-form-item>
      <el-form-item label="失效时间"><el-input v-model="form.effectiveTo" type="datetime-local" /></el-form-item>
      <el-form-item label="正文内容"><el-input v-model="form.content" type="textarea" :rows="6" placeholder="输入需要保存的资料正文" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button class="button-stable button-stable--md" type="primary" :loading="importing" @click="emit('submit')">确认导入</el-button>
    </template>
  </el-dialog>
</template>
