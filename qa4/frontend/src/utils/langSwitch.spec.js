import { describe, it, expect, vi } from 'vitest'
import {
  sourcesTitle,
  originalTranslateText,
  originalTranslateSources,
  switchMessageLang,
} from './langSwitch.js'

function makeMsg(overrides = {}) {
  return {
    plain: '神的经纶是祂的计划。',
    plainDisplay: '神的经纶是祂的计划。[1]',
    bibliography: '[1] 神的经纶，第1页',
    sourceItems: [
      {
        n: 1,
        zh: '神的经纶，第1页',
        en: "The God's Economy, p.1",
        source_zh: '神的经纶，第1页',
        book_title: '神的经纶',
        message_title: '',
        message_number: null,
      },
    ],
    question: '神的经纶是什么？',
    currentLang: 'zh',
    translating: false,
    translatedPlain: '',
    translatedHtml: '',
    translatedBib: '',
    translatedAnswers: {},
    doneMeta: { request_id: 'req-1' },
    ...overrides,
  }
}

describe('sourcesTitle', () => {
  it('三种语言小标题', () => {
    expect(sourcesTitle('zh')).toBe('引用书目')
    expect(sourcesTitle('zh_tw')).toBe('引用書目')
    expect(sourcesTitle('en')).toBe('References')
  })
})

describe('originalTranslate*', () => {
  it('永远取原始简体正文与书目，不用已显示的译文', () => {
    const m = makeMsg({
      currentLang: 'zh_tw',
      translatedPlain: '神的經綸是祂的計劃。[1]',
      translatedBib: '[1] 神的經綸，第1頁',
    })
    expect(originalTranslateText(m)).toBe('神的经纶是祂的计划。[1]')
    expect(originalTranslateText(m)).not.toMatch(/經|計/)
    const sources = originalTranslateSources(m)
    expect(sources[0].zh).toBe('神的经纶，第1页')
    expect(sources[0].zh).not.toMatch(/經/)
  })
})

describe('switchMessageLang', () => {
  it('先繁体再英文：送译必须是原始简体', async () => {
    const m = makeMsg()
    const calls = []
    const translate = vi.fn(async (req) => {
      calls.push({ text: req.text, sources: req.sources, targetLang: req.targetLang })
      if (req.targetLang === 'zh_tw') {
        return {
          answer: '神的經綸是祂的計劃。[1]',
          sources: ['[1] 神的經綸，第1頁'],
        }
      }
      return {
        answer: "God's economy is His plan.[1]",
        sources: ["[1] The God's Economy, p.1"],
      }
    })
    const decorateHtml = (t) => `<p>${t}</p>`

    await switchMessageLang(m, 'zh_tw', { translate, decorateHtml })
    expect(m.currentLang).toBe('zh_tw')
    expect(m.translatedPlain).toContain('經綸')
    expect(calls[0].text).toBe('神的经纶是祂的计划。[1]')
    expect(calls[0].sources[0].zh).toBe('神的经纶，第1页')

    // 当前显示已是繁体；再点英文仍须送原始简体
    await switchMessageLang(m, 'en', { translate, decorateHtml })
    expect(m.currentLang).toBe('en')
    expect(calls).toHaveLength(2)
    expect(calls[1].targetLang).toBe('en')
    expect(calls[1].text).toBe('神的经纶是祂的计划。[1]')
    expect(calls[1].text).not.toMatch(/經|計|God/)
    expect(calls[1].sources[0].zh).toBe('神的经纶，第1页')
    expect(calls[1].sources[0].zh).not.toMatch(/經/)
  })

  it('简→繁→英→繁→简 任意顺序可用且回简体不调接口', async () => {
    const m = makeMsg()
    const translate = vi.fn(async (req) => {
      if (req.targetLang === 'zh_tw') {
        return { answer: '繁體正文', sources: ['繁體書目'] }
      }
      return { answer: 'English body', sources: ['English src'] }
    })

    await switchMessageLang(m, 'zh_tw', { translate })
    await switchMessageLang(m, 'en', { translate })
    expect(translate).toHaveBeenCalledTimes(2)

    // 回繁：走缓存
    await switchMessageLang(m, 'zh_tw', { translate })
    expect(m.currentLang).toBe('zh_tw')
    expect(m.translatedPlain).toBe('繁體正文')
    expect(translate).toHaveBeenCalledTimes(2)

    // 回简：不调接口
    await switchMessageLang(m, 'zh', { translate })
    expect(m.currentLang).toBe('zh')
    expect(translate).toHaveBeenCalledTimes(2)

    // 再繁：仍缓存
    await switchMessageLang(m, 'zh_tw', { translate })
    expect(m.currentLang).toBe('zh_tw')
    expect(translate).toHaveBeenCalledTimes(2)
  })
})
