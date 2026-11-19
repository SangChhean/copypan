/**
 * 回答下方时间 / 费用（对齐 3.0 口径）。
 */

/** 毫秒 → 一位小数的秒字符串。 */
export function elapsedMsToSeconds(elapsedMs) {
  const ms = Number(elapsedMs)
  if (!Number.isFinite(ms) || ms < 0) return '0.0'
  return (ms / 1000).toFixed(1)
}

/**
 * 首 token 时定格：从 sendTime 到 now 的秒数（一位小数）。
 * 已有值则原样返回（之后不变）。
 */
export function freezeElapsedOnFirstToken(existing, sendTime, now = Date.now()) {
  if (existing != null && existing !== '') return String(existing)
  const start = Number(sendTime)
  const end = Number(now)
  if (!Number.isFinite(start) || !Number.isFinite(end)) return '0.0'
  return ((end - start) / 1000).toFixed(1)
}

/**
 * 最终展示用耗时：优先首 token 定格值；否则用后端 elapsed_ms。
 */
export function resolveAnswerElapsed({ firstTokenElapsed, elapsedMs } = {}) {
  if (firstTokenElapsed != null && firstTokenElapsed !== '') {
    return String(firstTokenElapsed)
  }
  return elapsedMsToSeconds(elapsedMs)
}

/** 费用展示数字（四位小数）。 */
export function formatCostUsd(cost) {
  const n = Number(cost)
  if (!Number.isFinite(n) || n < 0) return '0.0000'
  return n.toFixed(4)
}
