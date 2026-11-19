import { describe, it, expect } from 'vitest'
import {
  elapsedMsToSeconds,
  freezeElapsedOnFirstToken,
  resolveAnswerElapsed,
  formatCostUsd,
} from './answerMeta.js'

describe('answerMeta', () => {
  it('freeze_elapsed_on_first_token_one_decimal', () => {
    const send = 1_000_000
    expect(freezeElapsedOnFirstToken(null, send, send + 12340)).toBe('12.3')
    expect(freezeElapsedOnFirstToken('', send, send + 500)).toBe('0.5')
  })

  it('freeze_elapsed_does_not_change_after_set', () => {
    const frozen = freezeElapsedOnFirstToken(null, 0, 2500)
    expect(frozen).toBe('2.5')
    expect(freezeElapsedOnFirstToken(frozen, 0, 99999)).toBe('2.5')
  })

  it('resolve_uses_backend_ms_when_no_token', () => {
    expect(resolveAnswerElapsed({ elapsedMs: 8700 })).toBe('8.7')
    expect(resolveAnswerElapsed({ firstTokenElapsed: null, elapsedMs: 100 })).toBe('0.1')
    expect(resolveAnswerElapsed({ firstTokenElapsed: '3.1', elapsedMs: 99999 })).toBe('3.1')
  })

  it('elapsed_ms_to_seconds_and_cost_format', () => {
    expect(elapsedMsToSeconds(0)).toBe('0.0')
    expect(elapsedMsToSeconds(1234)).toBe('1.2')
    expect(formatCostUsd(0.0123)).toBe('0.0123')
    expect(formatCostUsd(0)).toBe('0.0000')
    expect(formatCostUsd(undefined)).toBe('0.0000')
  })
})
