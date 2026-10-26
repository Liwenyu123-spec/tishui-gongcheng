import { ref } from 'vue'

export type RemoteListKind = 'backend' | 'empty' | 'failed'

export function backendSourceLabel(source?: string | null) {
  if (!source || source === 'mock') return '数据库'
  return source
}

export function classifyRemoteList<T>(items: T[] | null | undefined): RemoteListKind {
  if (items == null) return 'failed'
  return items.length ? 'backend' : 'empty'
}

export function remoteListMessage(kind: RemoteListKind, name: string) {
  if (kind === 'empty') return `${name}当前没有记录，页面暂显示本地示例`
  if (kind === 'failed') return `${name}暂不可用，当前显示本地示例`
  return ''
}

export function remoteListLabel(kind: RemoteListKind, source?: string | null) {
  if (kind === 'backend') return backendSourceLabel(source)
  if (kind === 'empty') return '接口暂无记录 · 本地示例'
  return '本地示例'
}

export function useDataSource(initial = '本地示例') {
  const sourceLabel = ref(initial)
  const sourceKind = ref<RemoteListKind>('failed')
  const setBackend = (label = '数据库') => { sourceKind.value = 'backend'; sourceLabel.value = label }
  const setLocal = (label = '本地示例') => { sourceKind.value = 'failed'; sourceLabel.value = label }
  const applyList = (items: { source?: string }[]) => {
    const kind = classifyRemoteList(items)
    sourceKind.value = kind
    sourceLabel.value = remoteListLabel(kind, items[0]?.source)
    return kind
  }
  return { sourceLabel, sourceKind, setBackend, setLocal, applyList }
}
