# -*- coding: utf-8 -*-
"""歌词查找单元测试：合成小语料，不含真实歌词原文。"""

from __future__ import annotations

import unittest

from hymn.lyrics import (
    LyricsIndex,
    find_lyrics,
    lyric_intent,
    normalize_lyric_text,
)


def _synth_rows():
    """假诗歌：系列/号码/诗名/正文结构与真实块一致，文字为测试专用。"""
    return [
        {
            "series": "big",
            "hymn_number": 1,
            "name": "诗歌第1首　测试朝阳之歌",
            "title": "测试朝阳之歌",
            "text": "诗歌第1首　测试朝阳之歌\n一　朝阳升起照亮山谷，溪水流过安静草地。\n 副　赞美歌声层层回响，回响在山谷之间。\n 二　夜晚星辰点亮天幕，旅人停下仰望穹苍。",
        },
        {
            "series": "big",
            "hymn_number": 2,
            "name": "诗歌第2首　测试海洋之歌",
            "title": "测试海洋之歌",
            "text": "诗歌第2首　测试海洋之歌\n一　海洋波浪拍打岸边，海鸟盘旋鸣叫不停。\n 二　船只缓缓驶向远方，灯光闪烁指引归途。",
        },
        {
            "series": "sup",
            "hymn_number": 10,
            "name": "补充本诗歌第10首　测试共用短句甲",
            "title": "测试共用短句甲",
            "text": "补充本诗歌第10首　测试共用短句甲\n一　同一句测试短词重复出现在多处样例里。\n 二　其余内容彼此不同以免混淆。",
        },
        {
            "series": "sup",
            "hymn_number": 11,
            "name": "补充本诗歌第11首　测试共用短句乙",
            "title": "测试共用短句乙",
            "text": "补充本诗歌第11首　测试共用短句乙\n一　同一句测试短词重复出现在多处样例里。\n 二　这里写的是另一段补充文字内容。",
        },
        {
            "series": "sup",
            "hymn_number": 12,
            "name": "补充本诗歌第12首　测试共用短句丙",
            "title": "测试共用短句丙",
            "text": "补充本诗歌第12首　测试共用短句丙\n一　同一句测试短词重复出现在多处样例里。\n 二　再加一条避免不足三首的样例。",
        },
        {
            "series": "sup",
            "hymn_number": 13,
            "name": "补充本诗歌第13首　测试共用短句丁",
            "title": "测试共用短句丁",
            "text": "补充本诗歌第13首　测试共用短句丁\n一　同一句测试短词重复出现在多处样例里。\n 二　第四首同样含该短词以便 too_common。",
        },
        {
            "series": "sup",
            "hymn_number": 14,
            "name": "补充本诗歌第14首　测试共用短句戊",
            "title": "测试共用短句戊",
            "text": "补充本诗歌第14首　测试共用短句戊\n一　同一句测试短词重复出现在多处样例里。\n 二　第五首同样含该短词。",
        },
        {
            "series": "sup",
            "hymn_number": 15,
            "name": "补充本诗歌第15首　测试共用短句己",
            "title": "测试共用短句己",
            "text": "补充本诗歌第15首　测试共用短句己\n一　同一句测试短词重复出现在多处样例里。\n 二　第六首触发超过五首阈值。",
        },
        {
            "series": "fu",
            "hymn_number": 1,
            "name": "诗歌附1测试附篇之名",
            "title": "测试附篇之名",
            "text": "诗歌附1测试附篇之名\n一　附篇独有的一句金色麦田随风摇摆。",
        },
    ]


class TestHymnLyrics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = LyricsIndex.from_rows(_synth_rows())

    def test_normalize_strips_punct_and_hints(self):
        q = normalize_lyric_text("「朝阳升起照亮山谷」是哪首诗歌的歌词？", strip_hints=True)
        self.assertEqual(q, "朝阳升起照亮山谷")
        self.assertNotIn("哪首", q)

    def test_exact_match_and_unit_label(self):
        r = find_lyrics("朝阳升起照亮山谷", index=self.index)
        self.assertEqual(r["status"], "found")
        self.assertEqual(len(r["matches"]), 1)
        m = r["matches"][0]
        self.assertEqual(m["match_type"], "exact")
        self.assertEqual(m["hymn_number"], 1)
        self.assertEqual(m["unit_label"], "一")
        self.assertTrue(m["snippet"])

    def test_cross_stanza_exact(self):
        # 第一节末 + 副歌首（去标点后相连）
        r = find_lyrics("安静草地赞美歌声", index=self.index)
        self.assertEqual(r["status"], "found")
        self.assertEqual(r["matches"][0]["match_type"], "exact")

    def test_fuzzy_one_char(self):
        # 正确：朝阳升起照亮山谷；改一字
        r = find_lyrics("朝阳升起着亮山谷", index=self.index)
        self.assertEqual(r["status"], "found")
        self.assertEqual(r["matches"][0]["match_type"], "fuzzy")
        self.assertEqual(r["matches"][0]["hymn_number"], 1)

    def test_title_match(self):
        r = find_lyrics("测试海洋之歌", index=self.index)
        self.assertEqual(r["status"], "found")
        self.assertTrue(any(m["match_type"] == "title" and m["hymn_number"] == 2 for m in r["matches"]))

    def test_too_short(self):
        r = find_lyrics("朝阳", index=self.index)
        self.assertEqual(r["status"], "too_short")
        self.assertEqual(r["matches"], [])

    def test_too_common(self):
        r = find_lyrics("同一句测试短词重复出现在多处样例里", index=self.index)
        self.assertEqual(r["status"], "too_common")
        self.assertGreater(r["total"], 5)
        self.assertLessEqual(len(r["matches"]), 5)

    def test_lyric_intent_hint_and_block_hymn_ref(self):
        self.assertTrue(lyric_intent("哪首诗歌有这句：朝阳升起照亮山谷", index=self.index))
        self.assertFalse(lyric_intent("诗歌第1首", index=self.index))

    def test_lyric_intent_long_exact(self):
        self.assertTrue(lyric_intent("朝阳升起照亮山谷溪水流过", index=self.index))

    def test_strong_hint_triggers_without_hit(self):
        # 强档「哪首诗歌」：去提示后仍≥4字，即使无诗歌命中也触发
        self.assertTrue(lyric_intent("哪首诗歌有完全虚构的合成短句甲乙丙", index=self.index))

    def test_lyric_word_mid_prose_no_hit_is_weak(self):
        # 「歌词」在属灵话语中常见：无命中时不触发（弱档）
        self.assertFalse(lyric_intent("这段交通提到歌词却与诗歌库无关内容啊", index=self.index))

    def test_weak_hint_no_hit_no_intent(self):
        # 弱档「出自」：普通话语、无命中 → 不触发
        self.assertFalse(lyric_intent("这段话出自某次交通记录摘要", index=self.index))

    def test_weak_hint_with_hit_triggers(self):
        # 弱档「这句」+ 实际歌词命中 → 触发
        self.assertTrue(lyric_intent("这句朝阳升起照亮山谷", index=self.index))

    def test_mid_lyric_not_stripped_as_hint(self):
        # 歌词中间含「出自」字样时，不应被边缘剥离误删
        rows = [
            {
                "series": "big",
                "hymn_number": 99,
                "name": "诗歌第99首　测试出处之歌",
                "title": "测试出处之歌",
                "text": "诗歌第99首　测试出处之歌\n一　恩典出自父神怀里流淌不止。",
            }
        ]
        idx = LyricsIndex.from_rows(rows)
        q = "恩典出自父神怀里流淌"  # del 一字前的近似；这里先测 exact 不被 strip
        # 查询本身含「出自」但不在首尾提示位置
        self.assertEqual(normalize_lyric_text(q, strip_hints=True), "恩典出自父神怀里流淌")
        r = find_lyrics("恩典出自父神怀里流淌不止", index=idx)
        self.assertEqual(r["status"], "found")
        self.assertEqual(r["matches"][0]["match_type"], "exact")

    def test_not_found(self):
        r = find_lyrics("完全无关的合成句子不会命中诗歌", index=self.index)
        self.assertEqual(r["status"], "not_found")

    def test_strong_hint_overrides_scripture_false_positive(self):
        # 回归 T7：正文被 parse_refs 误判为经文时，强档「是哪首诗歌的歌词」仍应触发意图
        q = "约3:16是哪首诗歌的歌词？"
        # 确认经文解析会命中（否则本回归无意义）
        from scripture.normalize import parse_refs

        self.assertTrue(bool(parse_refs(q, validate=False)))
        self.assertTrue(lyric_intent(q, index=self.index))

    def test_t3_query_ok_rejects_too_common(self):
        # 回归 T3：过短且命中过多首的跨句拼接，探针应判为不可用
        from tools.probe_hymn_lyrics import _t3_query_ok

        # 共用短句在合成语料中出现 6 首 → too_common
        q = "同一句测试短词重复出现在多处样例里"
        self.assertFalse(_t3_query_ok(q, "sup", 10, self.index))
        # 独有跨句应可用
        self.assertTrue(_t3_query_ok("安静草地赞美歌声", "big", 1, self.index))


if __name__ == "__main__":
    unittest.main()
