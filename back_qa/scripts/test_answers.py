# 保存为 back_qa/scripts/test_answers.py
import urllib.request, json, os

url = 'http://127.0.0.1:8001/api/qa/query'
questions = [
    '神的经纶的中心是什么？',
    '生命与性情有何关系？',
    '什么是召会生活？',
]

results = []
for q in questions:
    body = json.dumps({'question': q, 'skip_cache': True}).encode('utf-8')
    req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json; charset=utf-8'})
    res = urllib.request.urlopen(req, timeout=120)
    data = json.loads(res.read().decode('utf-8'))
    results.append({'question': q, 'answer': data['answer'], 'sources': data['sources'], 'concepts': data['concepts'], 'found': data['found']})
    print(f'完成：{q}')

with open('e:/copypan/_test_answers.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print('已写入 _test_answers.json')
