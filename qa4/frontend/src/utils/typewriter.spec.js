import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { citeSupNoRenumber, createTypewriter, TICK_MS, DONE_POLL_MS } from './typewriter.js'
import { renderCitationsMarkdown } from './streamState.js'

describe('typewriter (3.0 port)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('queue_drains_one_char_per_20ms_in_order', async () => {
    const texts = []
    const tw = createTypewriter({ onChar: (t) => texts.push(t) })
    tw.push('甲乙丙')
    expect(tw.getQueue()).toEqual(['甲', '乙', '丙'])
    await vi.advanceTimersByTimeAsync(TICK_MS)
    expect(tw.getDisplayed()).toBe('甲')
    await vi.advanceTimersByTimeAsync(TICK_MS)
    expect(tw.getDisplayed()).toBe('甲乙')
    await vi.advanceTimersByTimeAsync(TICK_MS)
    expect(tw.getDisplayed()).toBe('甲乙丙')
    expect(tw.getQueueLength()).toBe(0)
    expect(texts).toEqual(['甲', '甲乙', '甲乙丙'])
  })

  it('done_waits_until_queue_empty_then_stop', async () => {
    const tw = createTypewriter()
    tw.push('一二三')
    const p = tw.waitUntilEmpty()
    let settled = false
    p.then(() => {
      settled = true
    })
    expect(settled).toBe(false)
    await vi.advanceTimersByTimeAsync(TICK_MS * 3 + DONE_POLL_MS)
    await p
    expect(settled).toBe(true)
    expect(tw.getQueueLength()).toBe(0)
    tw.stop()
    expect(tw.isRunning()).toBe(false)
    expect(tw.getDisplayed()).toBe('一二三')
  })

  it('clear_on_new_question_drops_queue_and_text', () => {
    const tw = createTypewriter()
    tw.push('残留')
    tw.tickOnce()
    expect(tw.getDisplayed().length).toBeGreaterThan(0)
    tw.clear()
    expect(tw.getQueueLength()).toBe(0)
    expect(tw.getDisplayed()).toBe('')
    expect(tw.isRunning()).toBe(false)
  })

  it('cite_during_type_keeps_original_numbers_no_renumber', () => {
    const typed = '见[5]与[2]。'
    const html = citeSupNoRenumber(typed)
    expect(html).toContain('data-n="5"')
    expect(html).toContain('[5]')
    expect(html).toContain('data-n="2"')
    expect(html).toContain('[2]')
    expect(html).not.toContain('>[1]<')
    expect(html).not.toMatch(/\[1\]/)

    const final = renderCitationsMarkdown(typed, [
      { n: 5, book_title: '甲' },
      { n: 2, book_title: '乙' },
    ])
    expect(final.body).toContain('>[1]<')
    expect(final.body).toContain('data-n="5"')
    expect(final.plainBody).toContain('[1]')
  })

  it('fixed_20ms_not_adaptive_one_char_even_with_backlog', async () => {
    const tw = createTypewriter()
    tw.push('字'.repeat(10))
    await vi.advanceTimersByTimeAsync(TICK_MS)
    // 3.0：每 tick 严格 1 字，不因积压加速
    expect(tw.getDisplayed().length).toBe(1)
    expect(tw.getQueueLength()).toBe(9)
  })
})
