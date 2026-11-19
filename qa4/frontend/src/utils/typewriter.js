/**
 * 打字机队列 —— 原样对齐 3.0 front_qa QAPage.vue 1125–1179 / 1627–1636。
 * 每 20ms 出一个字；done 时轮询等队列空再 stop。
 */

export const TICK_MS = 20
export const DONE_POLL_MS = 50

/**
 * 打字期间：[n] → 上标，保留原编号（qa4 必要差别；3.0 用引号后数字上标）。
 */
export function citeSupNoRenumber(text) {
  return String(text || '').replace(
    /\[(\d+)\]/g,
    (_, n) => `<sup class="cite" data-n="${n}">[${n}]</sup>`,
  )
}

/**
 * @param {object} [opts]
 * @param {(text: string) => void} [opts.onChar] 每吐出一字后回调（对应 3.0 改 msg.answer）
 * @param {typeof setInterval} [opts.setIntervalFn]
 * @param {typeof clearInterval} [opts.clearIntervalFn]
 */
export function createTypewriter(opts = {}) {
  const setIntervalFn = opts.setIntervalFn || setInterval
  const clearIntervalFn = opts.clearIntervalFn || clearInterval
  const onChar = opts.onChar

  /** @type {string[]} */
  let queue = []
  let displayed = ''
  let timer = null

  function start() {
    // 对齐 3.0 startTypewriter：已有 timer 则不重复开
    if (timer != null) return
    timer = setIntervalFn(() => {
      if (queue.length === 0) return
      const char = queue.shift()
      displayed += char
      onChar?.(displayed)
    }, TICK_MS)
  }

  /** 对齐 3.0 stopTypewriter：清 timer + 清空队列 */
  function stop() {
    if (timer != null) {
      clearIntervalFn(timer)
      timer = null
    }
    queue = []
  }

  /** 新问题 / 卸载：停表并清空已显示 */
  function clear() {
    stop()
    displayed = ''
  }

  /** 对齐 3.0：token 文本拆成单字入队后 start */
  function push(text) {
    const s = String(text || '')
    if (!s) return
    for (const char of s) {
      queue.push(char)
    }
    start()
  }

  /**
   * 对齐 3.0 done：每 50ms 看队列是否空。
   * 空后由调用方再 stop()（与 3.0 先 await 再 stopTypewriter 一致）。
   */
  function waitUntilEmpty() {
    if (queue.length === 0) return Promise.resolve(displayed)
    return new Promise((resolve) => {
      const wait = setIntervalFn(() => {
        if (queue.length === 0) {
          clearIntervalFn(wait)
          resolve(displayed)
        }
      }, DONE_POLL_MS)
    })
  }

  /** 测试用 */
  function tickOnce() {
    if (queue.length === 0) return
    const char = queue.shift()
    displayed += char
    onChar?.(displayed)
  }

  return {
    push,
    start,
    stop,
    clear,
    waitUntilEmpty,
    tickOnce,
    getDisplayed: () => displayed,
    getQueue: () => queue.slice(),
    getQueueLength: () => queue.length,
    isRunning: () => timer != null,
  }
}
