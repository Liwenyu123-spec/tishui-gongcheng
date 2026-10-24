import { ref } from 'vue'

export function useDataSource(initial = '本地示例') {
  const sourceLabel = ref(initial)
  const setBackend = (label = '后端 Mock 数据') => { sourceLabel.value = label }
  const setLocal = (label = '本地示例') => { sourceLabel.value = label }
  return { sourceLabel, setBackend, setLocal }
}
