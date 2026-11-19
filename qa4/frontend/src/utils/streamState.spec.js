import { describe, it, expect } from 'vitest'
import {
  createStreamState,
  applyEvent,
  truncateHistory,
  renderCitationsMarkdown,
  decorateAnswerHtml,
  chooseFollowupQuestion,
  doneAnswerText,
  formatDirectTitle,
  formatNotFoundMessage,
  hasUnverifiedMark,
  planIsComplex,
  planIsSensitive,
  planSubquestions,
} from './streamState.js'

describe('streamState', () => {
  it('normal_flow_tokens_plan_done', () => {
    let s = createStreamState()
    s = applyEvent(s, { event: 'step', step: 3 })
    s = applyEvent(s, { event: 'plan', main_type: '定义' })
    s = applyEvent(s, { event: 'token', text: '甲' })
    s = applyEvent(s, { event: 'token', text: '乙' })
    s = applyEvent(s, { event: 'done', answer_text: '甲乙', citations: [{ n: 1 }] })
    expect(s.text).toBe('甲乙')
    expect(s.plan.main_type).toBe('定义')
    expect(s.done.citations[0].n).toBe(1)
  })

  // 1. 【错引】：后端 done.answer 含〔未核实〕；前端须采用 answer 字段
  it('done_answer_field_applies_unverified_mark', () => {
    let s = createStreamState()
    s = applyEvent(s, { event: 'token', text: '「这句话不在任何段落里」[1]。' })
    s = applyEvent(s, {
      event: 'done',
      answer: '「这句话不在任何段落里」〔未核实〕[1]。',
      quote_checks: [{ quote: '这句话不在任何段落里', ok: false }],
      citations: [{ n: 1, book_title: '甲' }],
    })
    expect(doneAnswerText(s.done)).toContain('〔未核实〕')
    expect(s.text).toContain('〔未核实〕')
    expect(hasUnverifiedMark(s.text)).toBe(true)
    const html = decorateAnswerHtml(s.text)
    expect(html).toContain('class="unverified"')
    expect(s.done.quote_checks[0].ok).toBe(false)
  })

  // 2. 【拆】【敏感】plan 字段
  it('plan_complex_and_sensitive_fields', () => {
    let s = createStreamState()
    s = applyEvent(s, {
      event: 'plan',
      main_type: '默认',
      complex: true,
      sensitive: true,
      subquestions: [
        { text: '子问一', qtype: '定义' },
        { text: '子问二', qtype: '个人经历' },
        { text: '综合', qtype: '默认', synthesis: true },
      ],
    })
    expect(planIsComplex(s.plan)).toBe(true)
    expect(planIsSensitive(s.plan)).toBe(true)
    expect(planSubquestions(s.plan)).toHaveLength(3)
    expect(planSubquestions(s.plan)[2].synthesis).toBe(true)
  })

  // 3. direct 出处标题
  it('direct_block_titles_from_meta', () => {
    expect(
      formatDirectTitle({ meta: { book_title: '约翰福音', ref: '约三16' } }, 0),
    ).toBe('约翰福音 约三16')
    expect(
      formatDirectTitle({ meta: { series: '大本', hymn_number: 15 } }, 0),
    ).toBe('诗歌 大本 15')
    expect(
      formatDirectTitle(
        { meta: { book_title: '罗马书生命读经', message_number: 3 } },
        0,
      ),
    ).toBe('罗马书生命读经 第3篇')
    expect(formatDirectTitle({ text: 'x' }, 2)).toBe('块 3')
  })

  // 4. 未找到独立文案
  it('not_found_message_is_standalone', () => {
    const msg = formatNotFoundMessage(
      { not_found: true, premise_note: '大本没有第99999首' },
      'not_found',
    )
    expect(msg.startsWith('没有找到相关内容')).toBe(true)
    expect(msg).toContain('大本没有第99999首')
    expect(msg).not.toContain('request_id')
  })

  it('choose_candidates_followup', () => {
    let s = createStreamState()
    s = applyEvent(s, {
      event: 'choose',
      candidates: [{ series: 'big', hymn_number: 3, name: '示例' }],
    })
    expect(s.choose.candidates).toHaveLength(1)
    expect(chooseFollowupQuestion(s.choose.candidates[0])).toBe('诗歌第3首')
    expect(chooseFollowupQuestion({ series: 'sup', hymn_number: 12 })).toBe('补充本第12首')
  })

  it('direct_multi_blocks', () => {
    let s = createStreamState()
    s = applyEvent(s, { event: 'direct', index: 0, text: '块1' })
    s = applyEvent(s, { event: 'direct', index: 1, text: '块2' })
    s = applyEvent(s, { event: 'direct', index: 2, text: '块3' })
    expect(s.directs).toHaveLength(3)
    expect(s.directs[2].text).toBe('块3')
  })

  it('error_invalidates_streamed_text', () => {
    let s = createStreamState()
    s = applyEvent(s, { event: 'token', text: '将作废' })
    s = applyEvent(s, { event: 'error', message: 'x', invalidate_streamed: true })
    expect(s.text).toBe('')
    expect(s.tokens).toEqual([])
    expect(s.invalidated).toBe(true)
  })

  it('done_citations_render_superscripts', () => {
    const { body, bibliography } = renderCitationsMarkdown('见[1]与[2]', [
      { n: 1, book_title: '甲' },
      { n: 2, book_title: '乙', message_title: '篇' },
    ])
    expect(body).toContain('data-n="1"')
    expect(body).toContain('data-n="2"')
    expect(bibliography).toContain('[1] 甲')
    expect(bibliography).toContain('[2] 乙 篇')
  })

  it('decorateAnswerHtml_converts_hash_headings', () => {
    const html = decorateAnswerHtml('## 总标题\n正文「原话」\n### 小标题\n〔归纳〕一句')
    expect(html).toContain('class="a-title"')
    expect(html).toContain('总标题')
    expect(html).toContain('class="a-sub"')
    expect(html).toContain('小标题')
    expect(html).toContain('class="quote"')
    expect(html).toContain('class="induction"')
    // 半行 / 非标题前缀不崩
    expect(() => decorateAnswerHtml('##')).not.toThrow()
    expect(decorateAnswerHtml('##')).toBe('##')
    expect(decorateAnswerHtml('###')).toBe('###')
  })

  it('citations_renumber_by_first_appearance_and_drop_unused', () => {
    const text = '先引「乙」[3] 再引「甲」[1] 又引[3]'
    const { body, plainBody, bibliography, sourceItems, origToDisp } = renderCitationsMarkdown(text, [
      { n: 1, book_title: '甲书', source_en: '(Book A)', index: 'text_cwwl' },
      { n: 2, book_title: '未引用' },
      {
        n: 3,
        book_title: '乙书',
        message_title: '篇三',
        source_en: '(Book B, msg. 3)',
        index: 'text_life',
        location: { source_zh: '（乙书，第三篇）', message_number: 3 },
      },
    ])
    // 显示顺序：首次 [3]→[1]，[1]→[2]
    expect(origToDisp).toEqual({ 3: 1, 1: 2 })
    expect(body).toContain('data-n="3">[1]</sup>')
    expect(body).toContain('data-n="1">[2]</sup>')
    expect(plainBody).toBe('先引「乙」[1] 再引「甲」[2] 又引[1]')
    expect(bibliography.split('\n')).toEqual(['[1] 乙书 篇三', '[2] 甲书'])
    expect(bibliography).not.toContain('未引用')
    expect(sourceItems[0]).toMatchObject({
      n: 1,
      zh: '[1] 乙书 篇三',
      en: '(Book B, msg. 3)',
      source_zh: '（乙书，第三篇）',
      message_number: 3,
    })
    expect(sourceItems[1]).toMatchObject({ n: 2, zh: '[2] 甲书', en: '(Book A)' })
  })

  it('map_note_bib_uses_source_zh_with_fallback', () => {
    const text = '注甲[1] 注乙[2] 题库空[3] 文集[4]'
    const { bibliography, sourceItems } = renderCitationsMarkdown(text, [
      {
        n: 1,
        index: 'map_note',
        book_title: '圣经真理题库，第一系列　圣经—神的话',
        message_title: '第一篇　更美之约',
        location: { source_zh: '（恢复本圣经，来八6，注2）' },
      },
      {
        n: 2,
        index: 'map_note',
        book_title: '圣经真理题库，第二系列',
        message_title: '第二篇',
        location: { source_zh: '（恢复本圣经，可十四24，注1）' },
      },
      {
        n: 3,
        index: 'map_note',
        book_title: '圣经真理题库，空出处系列',
        message_title: '某一篇',
        location: { source_zh: '' },
      },
      {
        n: 4,
        index: 'text_cwwl',
        book_title: '李常受文集一九五四年第三册，福音题纲',
        message_title: '第六十六题',
        location: { source_zh: '（李常受文集一九五四年第三册，福音题纲，第六十六题，第二段）' },
      },
    ])
    expect(bibliography.split('\n')).toEqual([
      '[1] 恢复本圣经，来八6，注2',
      '[2] 恢复本圣经，可十四24，注1',
      '[3] 圣经真理题库，空出处系列 某一篇',
      '[4] 李常受文集一九五四年第三册，福音题纲 第六十六题',
    ])
    expect(sourceItems[0].source_zh).toContain('来八6')
    expect(sourceItems[3].zh).toContain('李常受文集')
    expect(sourceItems[3].zh).not.toContain('恢复本')
  })

  it('history_truncate_to_three_turns', () => {
    const h = [1, 2, 3, 4, 5].map((i) => ({ question: String(i), answer: 'a' }))
    const t = truncateHistory(h, 3)
    expect(t).toHaveLength(3)
    expect(t[0].question).toBe('3')
    expect(t[2].question).toBe('5')
  })

  // 空 answer 兜底 done 不抹掉已流式正文
  it('done_empty_answer_keeps_streamed_text', () => {
    let s = createStreamState()
    s = applyEvent(s, { event: 'token', text: '已流式' })
    s = applyEvent(s, { event: 'token', text: '正文' })
    s = applyEvent(s, { event: 'done', answer: '', degraded: true })
    expect(s.text).toBe('已流式正文')
    expect(s.done.degraded).toBe(true)
  })

  // 非空 answer 覆盖流式正文（含〔未核实〕）
  it('done_nonempty_answer_overwrites_streamed_text', () => {
    let s = createStreamState()
    s = applyEvent(s, { event: 'token', text: '流式草稿' })
    s = applyEvent(s, {
      event: 'done',
      answer: '定稿「引文」〔未核实〕[1]',
    })
    expect(s.text).toBe('定稿「引文」〔未核实〕[1]')
    expect(s.text).toContain('〔未核实〕')
  })

  // invalidate 后空 answer 的 done 不恢复正文
  it('done_empty_answer_after_invalidate_keeps_empty', () => {
    let s = createStreamState()
    s = applyEvent(s, { event: 'token', text: '将被清空' })
    s = applyEvent(s, { event: 'error', message: 'fail', invalidate_streamed: true })
    expect(s.text).toBe('')
    s = applyEvent(s, { event: 'done', answer: '', degraded: true })
    expect(s.text).toBe('')
    expect(s.invalidated).toBe(true)
  })

  it('verse_data_single_and_multi', () => {
    let s = createStreamState()
    s = applyEvent(s, {
      event: 'verse_data',
      data: { book: 43, chapter: 3, verse: 16, text_gb: '神爱世人', footnotes: [], crossrefs: [] },
    })
    expect(s.verseData.book).toBe(43)
    expect(s.verseData.verse).toBe(16)
    s = applyEvent(s, {
      event: 'verse_data',
      data: { verses: [{ book: 43, chapter: 3, verse: 1 }], query_type: 'chapter' },
    })
    expect(s.verseData.query_type).toBe('chapter')
    expect(s.verseData.verses).toHaveLength(1)
  })

  it('hymn_data_payload', () => {
    let s = createStreamState()
    s = applyEvent(s, {
      event: 'hymn_data',
      data: {
        hymns: [{ series_zh: '大本', hymn_number: 15, text: '一　若无流血' }],
        notes: [],
      },
    })
    expect(s.hymnData.hymns).toHaveLength(1)
    expect(s.hymnData.hymns[0].hymn_number).toBe(15)
  })
})

