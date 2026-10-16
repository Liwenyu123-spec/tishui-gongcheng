<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/http'

interface ApiUser {
  id: string
  username: string
  display_name: string
  role: string
  permissions: string[]
}

interface UserRow extends ApiUser {
  scope: string
  status: string
  last: string
  source: string
}

const roleNames: Record<string, string> = { admin: '管理员', operator: '值班调度员', engineer: '工程/设备', reviewer: '审批负责人' }
const permissionNames: Record<string, string> = {
  read: '只读查看',
  ask: 'Agent 查询',
  submit_scheme: '提交方案',
  review: '建议审核',
  knowledge: '知识库管理',
  audit: '审计查看',
}
const permissionOptions = Object.keys(permissionNames)
const localUsers: UserRow[] = [
  { id: 'local-1', username: 'zhang-duty', display_name: '张值班', role: 'operator', permissions: ['read', 'ask'], scope: '全链路只读', status: '启用', last: '今天 08:01', source: '本地示例' },
  { id: 'local-2', username: 'li-engineer', display_name: '李工程', role: 'engineer', permissions: ['read', 'knowledge'], scope: '一至四泵站', status: '启用', last: '昨天 17:32', source: '本地示例' },
  { id: 'local-3', username: 'wang-review', display_name: '王审批', role: 'reviewer', permissions: ['read', 'review'], scope: '全片区', status: '启用', last: '今天 09:12', source: '本地示例' },
]
const rows = ref<UserRow[]>(localUsers.map(user => ({ ...user, permissions: [...user.permissions] })))
const loading = ref(false)
const sourceLabel = ref('本地示例')
const formVisible = ref(false)
const editing = ref(false)
const saving = ref(false)
const form = reactive({ id: '', username: '', password: '', display_name: '', role: 'operator', permissions: ['read'] })

const pendingCount = computed(() => rows.value.length)

const scopeFor = (permissions: string[]) => {
  if (permissions.includes('audit')) return '全局管理'
  if (permissions.includes('review')) return '全片区'
  if (permissions.includes('knowledge')) return '一至四泵站'
  return '全链路只读'
}

const formatUser = (user: ApiUser, source = '后端 Mock 数据'): UserRow => ({
  ...user,
  scope: scopeFor(user.permissions),
  status: '启用',
  last: '—',
  source,
})

const loadUsers = async () => {
  loading.value = true
  try {
    const result = await api<ApiUser[]>('/api/v1/users')
    if (result.length) {
      rows.value = result.map(user => formatUser(user))
      sourceLabel.value = '后端 Mock 数据'
    } else {
      sourceLabel.value = '接口暂无用户 · 本地示例'
      ElMessage.info('用户接口当前没有数据，页面暂显示本地示例')
    }
  } catch {
    sourceLabel.value = '本地示例'
    ElMessage.warning('用户接口暂不可用，当前显示本地示例')
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  editing.value = false
  Object.assign(form, { id: '', username: '', password: '', display_name: '', role: 'operator', permissions: ['read'] })
  formVisible.value = true
}

const openEdit = (row: UserRow) => {
  editing.value = true
  Object.assign(form, { id: row.id, username: row.username, password: '', display_name: row.display_name, role: row.role, permissions: [...row.permissions] })
  formVisible.value = true
}

const saveUser = async () => {
  if (!form.display_name || (!editing.value && (!form.username || !form.password))) {
    ElMessage.warning(editing.value ? '请填写显示名称' : '请填写用户名、密码和显示名称')
    return
  }
  saving.value = true
  try {
    let result: ApiUser
    if (editing.value) {
      result = await api<ApiUser>(`/api/v1/users/${form.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ display_name: form.display_name, role: form.role, permissions: form.permissions }),
      })
      rows.value = rows.value.map(row => row.id === result.id ? formatUser(result) : row)
      ElMessage.success('用户权限已更新')
    } else {
      result = await api<ApiUser>('/api/v1/users', {
        method: 'POST',
        body: JSON.stringify({ username: form.username, password: form.password, display_name: form.display_name, role: form.role, permissions: form.permissions }),
      })
      rows.value.unshift(formatUser(result))
      ElMessage.success('用户已创建')
    }
    sourceLabel.value = '后端 Mock 数据'
    formVisible.value = false
  } catch {
    ElMessage.error(editing.value ? '用户更新失败' : '用户创建失败，请检查用户名是否重复')
  } finally {
    saving.value = false
  }
}

const viewAudit = () => {
  ElMessage.info('审计记录将在下一阶段接入')
}

onMounted(loadUsers)
</script>

<template>
  <div class="page-title">
    <div>
      <h2>用户与权限</h2>
      <p>最小权限原则 · 站点/片区范围可配置 · 操作写入审计日志 · {{ sourceLabel }}</p>
    </div>
    <el-button type="primary" :loading="loading" @click="openCreate">新增用户</el-button>
  </div>

  <div class="panel">
    <div class="panel-head"><h3>用户列表</h3><span>共 {{ pendingCount }} 个用户</span></div>
    <div class="table-wrap">
      <el-table :data="rows">
        <el-table-column prop="display_name" label="用户" />
        <el-table-column label="角色"><template #default="s">{{ roleNames[s.row.role] || s.row.role }}</template></el-table-column>
        <el-table-column prop="scope" label="数据范围" />
        <el-table-column prop="status" label="状态"><template #default="s"><span class="tag tag-green">{{s.row.status}}</span></template></el-table-column>
        <el-table-column prop="last" label="最近登录" />
        <el-table-column label="操作" width="190">
          <template #default="s">
            <el-button link type="primary" @click="openEdit(s.row)">编辑权限</el-button>
            <el-button link @click="viewAudit">查看审计</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>

  <el-dialog v-model="formVisible" :title="editing ? '编辑用户权限' : '新增用户'" width="520px">
    <el-form label-width="90px">
      <el-form-item label="用户名" required><el-input v-model="form.username" :disabled="editing" /></el-form-item>
      <el-form-item v-if="!editing" label="密码" required><el-input v-model="form.password" type="password" show-password /></el-form-item>
      <el-form-item label="显示名称" required><el-input v-model="form.display_name" /></el-form-item>
      <el-form-item label="角色"><el-select v-model="form.role" style="width:100%"><el-option v-for="(label,value) in roleNames" :key="value" :label="label" :value="value" /></el-select></el-form-item>
      <el-form-item label="权限"><el-checkbox-group v-model="form.permissions"><el-checkbox v-for="permission in permissionOptions" :key="permission" :label="permission">{{ permissionNames[permission] }}</el-checkbox></el-checkbox-group></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="formVisible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="saveUser">保存</el-button>
    </template>
  </el-dialog>
</template>
