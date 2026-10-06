# -*- coding: utf-8 -*-
"""
词条分层统计（第1项测试辅助工具）

用 2373 个词条分类表（10.4 版）找出一段文字里出现的词条，按四层统计：
外在、内在、最内在、显出的外在。

做法：正向最大匹配（每个位置先取最长的词条）。
- 括号里的别名一并匹配，例如「妇人（女人）」，「妇人」「女人」都算这一条。
- 单字词条（如 神、主、灵、一、但、地）误中太多（「但是」「一个」「神学」），
  默认单列、不计入比例；人工核对后，要计入的用 --include-single 重算。
- 这只是初筛。最大匹配会切错（例如「生命的光照」会切成「生命的光」+「照」），
  统计结果要人工核对后再用。

用法：
  python term_layer_count.py --text "神把自己作恩典分赐到我们里面"
  python term_layer_count.py --file 负担说明.txt
  python term_layer_count.py --file 负担说明.txt --json        # 输出 JSON，方便程序调用
  可加 --terms 指定词条表（默认同目录下的 terms_2373.json，没有就用 terms_2373.csv）
"""
import argparse, csv, json, os, re, sys
from collections import Counter

LAYERS = ['外在', '内在', '最内在', '显出的外在']


def load_terms(path):
    """读 terms_2373.json（优先）或 terms_2373.csv，返回 文字形式 -> (原词条, 层次)。"""
    surface = {}
    if path.endswith('.json'):
        data = json.load(open(path, encoding='utf-8'))
        for t in data['terms']:
            for s in [t['term']] + t.get('aliases', []):
                surface.setdefault(s, (t['original'], t['layer']))
        return surface
    with open(path, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            name, layer = row['词条'].strip(), row['层次'].strip()
            m = re.match(r'^(.+?)（(.+?)）$', name)
            forms = [m.group(1), m.group(2)] if m else [name]
            for s in forms:
                surface.setdefault(s, (name, layer))
    return surface


def match(text, surface):
    maxlen = max(len(s) for s in surface)
    hits, i, n = [], 0, len(text)
    while i < n:
        for L in range(min(maxlen, n - i), 0, -1):
            s = text[i:i + L]
            if s in surface:
                name, layer = surface[s]
                hits.append({'位置': i, '文字': s, '词条': name, '层次': layer, '单字': L == 1})
                i += L
                break
        else:
            i += 1
    return hits


def summarize(hits, include_single=False):
    counted = [h for h in hits if include_single or not h['单字']]
    c = Counter(h['层次'] for h in counted)
    total = sum(c.values())
    return {
        '计入词条数': total,
        '各层个数': {k: c.get(k, 0) for k in LAYERS},
        '各层比例': {k: (round(c.get(k, 0) / total * 100, 1) if total else 0.0) for k in LAYERS},
        '计入的词条': [f"{h['文字']}（{h['层次']}）" for h in counted],
        '单字词条（未计入，需人工核对）': [] if include_single else
            [f"{h['文字']}（{h['层次']}）" for h in hits if h['单字']],
    }


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--text')
    g.add_argument('--file')
    here = os.path.dirname(os.path.abspath(__file__))
    default = os.path.join(here, 'terms_2373.json')
    if not os.path.exists(default):
        default = os.path.join(here, 'terms_2373.csv')
    ap.add_argument('--terms', default=default)
    ap.add_argument('--include-single', action='store_true')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()

    text = a.text if a.text is not None else open(a.file, encoding='utf-8').read()
    res = summarize(match(text, load_terms(a.terms)), a.include_single)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    print(f"计入词条数：{res['计入词条数']}")
    for k in LAYERS:
        print(f"  {k}：{res['各层个数'][k]} 个（{res['各层比例'][k]}%）")
    print('计入的词条：' + '、'.join(res['计入的词条']))
    if res['单字词条（未计入，需人工核对）']:
        print('单字词条（未计入，需人工核对）：' + '、'.join(res['单字词条（未计入，需人工核对）']))


if __name__ == '__main__':
    main()
