import dashscope, json, urllib.request, os
from anthropic import Anthropic

dashscope.api_key = 'sk-b4cb71064b0a49a98f74f45f3d570a8d'
dashscope.base_http_api_url = 'https://dashscope-intl.aliyuncs.com/api/v1'
from dashscope.audio.asr import Transcription

# 加载环境变量取 Claude key
from dotenv import load_dotenv
load_dotenv('back_mic/backend/.env')
claude = Anthropic(api_key=os.environ.get('CLAUDE_API_KEY') or os.environ.get('ANTHROPIC_API_KEY'))

def haiku_correct(text: str) -> str:
    from back_qa.qa.asr_service import correct_transcript
    import asyncio
    return asyncio.run(correct_transcript(text))

targets = {
    '001.m4a': '结晶读经和生命读经有什么不同',
    '005.m4a': '李常受和倪柝声在职事上有什么承接关系',
    '021.m4a': '什么是属灵新陈代谢的过程',
    '030.m4a': '什么是在生命中作王',
    '032.m4a': '信徒怎么胜过罪、死与撒但',
    '040.m4a': '活力排是什么',
}

for fname, ref in targets.items():
    r = Transcription.call(
        model='fun-asr',
        file_urls=[f'https://qa.aipansearch.org/asr_audio/{fname}'],
        language_hints=['zh'],
    )
    results = r.output.get('results', [])
    url = results[0].get('transcription_url', '') if results else ''
    if url:
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read())
        funasr_text = ''.join(s['text'] for s in data['transcripts'][0]['sentences'])
    else:
        funasr_text = f"[FAILED]"

    haiku_text = haiku_correct(funasr_text)

    match = '✅' if ref in haiku_text or haiku_text.rstrip('？?') == ref else '❌'
    changed = ' (Haiku改了)' if haiku_text != funasr_text else ''
    print(f"{match} [{fname}]")
    print(f"   FunASR: {funasr_text}")
    print(f"   Haiku:  {haiku_text}{changed}")
    print(f"   ref:    {ref}")
    print()

