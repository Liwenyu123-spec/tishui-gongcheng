/**
 * 页级刷新注册表。
 *
 * 顶栏的「刷新本页」按钮不直接调用各页面内部函数，而是通过这里注册和触发：
 * 每个页面只声明自己的刷新动作，按钮的位置、图标和 loading 表现因此在所有
 * 页面保持一致，不需要为每个页面重复写一套按钮样式。
 *
 * 约定：页面在 setup 中调用一次 registerPageRefresh，注册函数必须是幂等
 * 的加载动作（重复调用只重新取数据，不改变业务状态）。
 */

import { onBeforeUnmount, ref } from 'vue'

/** 页面向顶栏注册的刷新动作，允许返回 Promise。 */
export type PageRefreshHandler = () => void | Promise<void>

/** 当前页面注册的刷新动作；没有页面注册时（例如登录页）顶栏按钮置灰。 */
const handler = ref<PageRefreshHandler | null>(null)

/** 刷新进行中标记，供顶栏按钮显示 loading 并防止重复触发。 */
const refreshing = ref(false)

export function registerPageRefresh(fn: PageRefreshHandler): void {
  handler.value = fn
  // 页面卸载时清掉自己注册的动作，避免切到新页面后仍调用旧页面的加载逻辑。
  onBeforeUnmount(() => {
    if (handler.value === fn) handler.value = null
  })
}

export function usePageRefresh() {
  return { handler, refreshing }
}

export async function runPageRefresh(): Promise<boolean> {
  // 没有注册动作（登录页等）或正在刷新时直接返回，避免重复请求。
  if (!handler.value || refreshing.value) return false
  refreshing.value = true
  try {
    await handler.value()
  } finally {
    refreshing.value = false
  }
  return true
}
