# -*- coding: utf-8 -*-
"""根据负担说明生成「六阶段」龙骨，直接调 Claude（claude-opus-5）。

用法：
  python generate_skeleton.py --trial          # 只跑 JSON 第一条，打印结果
  python generate_skeleton.py --id 24作贵重    # 只更新指定 id，合并写回 JSON
  python generate_skeleton.py --folder 3应用实行
  python generate_skeleton.py                  # 跑全部 30 条，写出 skeleton_results_30.json
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parents[1] / "back_mic" / "backend"
INPUT_JSON = SCRIPT_DIR / "第一次测试" / "feast_burdens_30_sonnet5.json"
OUTPUT_JSON = SCRIPT_DIR / "第一次测试" / "skeleton_results_30.json"

MODEL = "claude-opus-5"
MAX_TOKENS = 8192

SYSTEM_PROMPT = """你是一位熟悉倪柝声、李常受职事信息的资深研究者，同时具备纲目写作的实务经验。
严格只输出最终结果，不输出内部思考步骤、分析过程、分隔线。"""

SIX_STAGE_CRITERIA = """一、圣经根据
- 判断依据：这句话是否满足以下两个分支之一——

分支①近乎逐字引用：这句话的主要内容必须就是经文原句本身（照原文字词逐字或近乎逐字复述，不是替换过同义词的转述），而且这处引用是这句话在陈述的核心内容本身——不是附带在另一个独立论点上的装饰性引证（不是"我论述了一个观点，顺带提一句某节经文也这么说"这种用法）。

示范：保罗说，"神已经照着所应许的，给以色列带来一位救主，就是耶稣"（徒十三23），"……你是我的儿子，我今日生了你"（33，引诗二7）——文字本身就是经文原句加引号的直接引用，不是转述或解读，属分支①。

分支②解经性阐释：必须同时满足两个条件——① 带着确切引用的经文出处（具体到章节）；② 这句话的内容离开这处具体经文/记载，就没法换一种说法单独存在。判断方法：把经文出处从这句话里去掉，写出剩下的内容，再判断这剩下的内容是——
  (a) 一条可以脱离这处经文被独立主张的教义性原则/道理——不算圣经根据，改按其余标准判断；还是
  (b) 在转述/解读这处经文记载的具体情节、意象、用语，或句子结构本身就依赖这处引用才有指代对象——算圣经根据。

示范1（转述具体情节）：撒下七章十二至十四节上半论到"你……的后裔"和"我的子"，指明大卫的后裔要成为神的儿子……大卫有心为神建殿，但神向大卫指明，祂要建造一位成为大卫的后裔——去掉"撒下七12~14"，剩下的是在转述一段具体记载（大卫想建殿、神的回应），读者不知道在讲哪件事，内容立不住，属分支②。

示范2（句子结构依赖引用，最典型）：罗马一章三至四节与撒下七章十二至十四节上半相符……这二处经节的内在意义，是向我们启示一个兼有人性和神性的人位——去掉"罗一3~4，撒下七12~14"，"这二处经节"就没有指代对象，句子结构本身散架，不只是读着别扭，是语法上就不完整，属分支②。

反例（教义性原则，不算圣经根据）：基督是我们已在其中生根的土壤——即使带着"西二6~7启示"这样的出处，去掉出处后依然是一条完整、可独立成立的教义性比喻，不需要知道具体章节才能明白，这类改归真理启示。

- 若这段文字没有满足以上任一分支的内容，这一项缺席，属正常情况

二、真理启示
- 判断依据：是否讲清楚「是什么」——常见「不是A乃是B」「不只是A更要B」这类句式；或明确真理的定义、说明
- 需注意：这类句式不是唯一判据，同样的句式如果出现在这段文字的结尾、起收束作用，则应归确定目标，不归真理启示——关键还是看这句话在整段负担里的位置和功能，不是句式本身
- 判断这句话是不是真理启示的时候，还要留意它用语是否准确、没有偷换概念或混用——比如「分赐」「构成」「建造」这类核心用词，是不是照着职事的定义在使用
- 更细的判断角度：如果一句话是在列举一套完整的步骤/阶段（比如「从A、B、C，直到D」这种清单式表达，或负担说明里明确出现「这几步」「这N步」这类总括词），即便每一步的动词看起来很像个人经历（长大、变化、模成、得荣等），只要句子的主语是这套机制/真理本身在运作、不是「我们」以第一人称在经历，仍归真理启示，属于对这套机制「是什么、包含哪几步」的陈明，不归主观经历。但如果这句话是「真理性主干＋使/让/叫……我们……」这个结构——前半句陈明客观真理或机制，后半句借目的/结果从句把落点带到信徒个人身上（不限「我们」这一称谓）、触及人里面的灵、心、魂、生命——不能再简单地整条归主观经历。应按下方【应用实行、团体建造、主观经历、真理启示的判断顺序】改判：若从句点名了具体、可重复操练的动作或路径，归应用实行；若从句走到团体实际，归团体建造；若从句只讲里面感受、状态，未点名操练动作也未走到团体，才归主观经历。不因为前半句主语是神、是机制，就把整条留在真理启示。真正该留在真理启示的"机制性主语"句子，是通篇都没有走到信徒个人身上、没有把力度落在个人身上的那种——纯粹陈明这套真理/机制本身是什么、怎么运作，才归真理启示。
【保护条款】若句子主干本身已足以独立成立为客观道理的界定("是什么"/"乃是"句式)，且后接的从句只是该道理自然而然的延伸说明——既未点名具体操练动作，也未指向个人里面具体的感受或状态——整句仍归真理启示，不因带有从句结构就自动改判到主观经历或应用实行。

三、主观经历
- 判断依据：这句话是否落在信徒个人这一层——不限定「我们」这个字，「他」「他们」「相信之人」这类指向信徒个人的第三人称表述，跟「我们」一样算；不论是信徒对真理积极方面的经历，或是消极、对付的经历，只要讨论对象落在个人这一层，都算主观经历——但若该句点名了具体、可重复操练的动作或路径（见应用实行标准与下方判断顺序），则按应用实行判断，不归主观经历。
- 更具体的判断角度：这句话有没有触及人里面的灵、心、魂，而不是停留在客观知识的陈述——主观的经历在于灵和生命，一切在人里头、在人身上的经历都是主观的——但若该经历是点名了具体、可重复操练的动作或路径（转向灵、吸取话、浇灌人等，见应用实行标准与下方判断顺序），则按应用实行判断，不归主观经历。
- 需注意："我们"做主语，不代表就自动落到个人这一层——要看这句话是在陈述一条谁都适用的普遍原则（比如"我们所遭遇的每件事都在神主宰之下"这类泛指性处境陈述），还是在具体描述这个人里面发生了什么、有什么被触动或领受。前者仍归真理启示，只有后者才归主观经历——但后者若点名了具体、可重复操练的动作或路径，仍按应用实行判断。
- 主观经历严格限定为：操练之后或伴随操练发生的里面状态、感受、领受结果的描述——如被构成、被浸透、蒙光照、得安慰、有平安、里面受对付、生命被显大等——且句中没有点名具体、可重复操练的动作或路径。
- 排除条款：句子即使落在信徒个人这一层、即使动词语态是领受性的（享受、蒙、让、被……），只要点名了具体操练动作或路径（参见应用实行标准中的动作清单），就不归主观经历，改按应用实行判断。

四、团体建造
- 判断依据：这句话是否带到团体的一面——比如过召会生活、团体的神人生活，或点到召会的聚会等，而不只是停留在个人
- 需注意：句子里出现「身体」「召会」这类字眼，不代表就一定归这一项——如果这句话还停留在「定义什么是基督的身体」，应归真理启示；只有走到「过团体的召会生活、团体神人生活」等这类实际，才归团体建造
- 更细的判断角度：留意这句话里的个人经历，是被当成终点，还是通向团体建造的过程——如果个人经历只是被提出来、就停在那里，没有继续走向团体，不算团体建造；只有个人经历被带向召会生活、团体聚会这类团体性的实际，才算
- 补充判断角度：一句内容只要目的/结果从句具体交代了团体生活/建造这件事本身该怎么发生、或正在发生什么（比如彼此配搭、团体地敬拜、过召会生活、信徒之间正在发生的具体互动场景），就归团体建造，不要求一定是叙事性的具体互动场景才算。但如果这句话只是在结尾用一个团体性的异象/终点词给全篇收尾——比如仅仅说"终极完成于新耶路撒冷""成为基督的身体"这类单纯的终点/异象词，没有交代任何具体的团体生活或建造内容该怎么发生——这种情况仍归确定目标，不算团体建造。只有当整句话完全停留在陈述个人职责/呼召，没有点出任何团体性的具体指向时，才仍归应用实行。
- 【团体建造与确定目标的优先级】若一句话同时满足团体建造（具体交代了团体生活/建造该怎么发生、或正在发生什么）与确定目标（位置在结尾、语气收束）两方面特征，团体建造优先——但这一优先级只在这句话真的具体交代了团体实际本身时才适用，不能因为收束句里恰好带了个团体性的名词或异象词，就自动判团体建造（这类仍归确定目标，见上文补充判断角度）。

五、应用实行
- 判断依据：这句话是否给出具体、可操作的路径（不只是原则性的呼吁）
- 更具体的判断角度：不要死板地只认几个固定形式（比如晨兴、祷读、家聚会）——只要是具体、可操作的路径，不限形式，都算应用实行；反过来，就算提到了「晨兴」「祷读」这类字眼，如果只是笼统带过、没有具体怎么做，也不算真正落地的应用实行
【"主干＋从句"结构的动作命名测试】
当句子呈现"真理性/表征性主干＋使/让/叫/享受/蒙+个人化从句"或类似结构时，不能仅凭从句主导动词的语态（是主动操练还是被动领受），也不能仅凭是否出现"竭力""当""需要"等字面努力词，来判断归应用实行还是主观经历。应改为直接追问：从句或后半部分，有没有点名一项具体、可重复操练的动作或路径？

凡点名了具体操练动作或路径的——如：转向灵、呼求主名、祷读主话、吸取话中的水、浇灌人、撒种建造、往下扎根向上结果、进至圣所、摸施恩宝座、支取基督、儆醒祷告等——不论主干动词的语态如何，也不论有没有"竭力"这类字眼，都归应用实行。

示范：
①"我们凭吸取这土壤的元素而长大，正如树栽于水旁借吸取水的丰富而生长，往下扎根、向上结果。"——虽以"凭吸取……而长大"这类领受性语态起句，但"吸取""扎根""结果"点名的是具体可操练的路径，归应用实行，不归主观经历。
②"我们享受基督作生命的流，是使我们作撒种者、栽种者、浇灌者、生育者、喂养者和建造者。"——"享受"是领受性动词不假，但"作撒种者……浇灌者……建造者"点名的是具体服事动作，归应用实行。
③"我们一转向灵，就经历基督作梯子，进入至圣所，摸着施恩的宝座。"——"经历""进入""摸着"看似领受性表述，但"一转向灵"本身就是具体、可重复的操练动作，后续路径由它带出，整句归应用实行。
反例对照："竭力进入安息，来到施恩宝座前受怜悯、得恩典"——这条因带"竭力"一词而被归为应用实行，与③本质是同一件事（进至施恩宝座），却因字面有无"竭力"而判法不同，说明字面努力词不能作为判断依据；两条都应统一按"是否点名具体操练动作"归应用实行。

【动作命名测试的两个前置排除】
在套用上面的动作命名测试之前，先检查以下两种情况，命中就不适用①这一步，改按对应阶段判断：

排除一——信徒间团体互动优先归团体建造：
若从句/后半部分描述的是信徒之间彼此的具体团体互动（如彼此相顾、遮盖别人的过失、维持那灵的一、彼此配搭事奉、将基督供应给别的圣徒等——这类描述"信徒关系/团体生活如何运作"的具体场景，落点是别人或召会整体），应先按【判断顺序】的②团体建造判断，不适用①。
若只是宣告个人蒙召尽某种服事身份/职分（如作撒种者、栽种者、浇灌者、牧人这类角色宣告，没有具体交代信徒之间此刻正在怎样互动），仍归应用实行——这跟本节官方示范②（撒种者、栽种者、浇灌者、生育者、喂养者、建造者）不冲突，那个例子讲的是身份宣告，不是具体互动场景。

示范：
"我们需要在凡事上照顾圣徒，将基督作对付罪的生命供应给他们，恢复堕落的圣徒，维持那灵的一；彼此交通时并要遮盖别人的罪，不揭露、不毁谤。"——落点是"圣徒""别人"，描述信徒之间具体怎么相待，按排除一归团体建造，不归应用实行。

排除二——主观经历范例词优先归主观经历：
若从句/后半部分真正的落脚点，就是【三、主观经历】标准所列的状态词本身（被构成、被浸透、蒙光照、得安慰、有平安、活神、彰显神、生命被显大、满溢等）——即这句话要交代的核心内容是这个"内在状态/性质变化"，而不是靠一个先行的具体操练动作带出的路径——仍归主观经历，不因为句子里搭了别的动词外壳就整条判应用实行。
只有当动作本身（转向灵、吸取话、扎根结果等）才是这句话交代的实际操练路径、状态词只是这个动作带出的自然结果时，才归应用实行（参照本节官方示范③"一转向灵…经历基督作梯子…摸着施恩宝座"——动作在前带出后续，这类不受影响，仍归应用实行）。

示范：
"…将神涂抹到我们里面，使我们被神浸透，据有神。"——"被神浸透，据有神"是这句话的落脚点，按排除二归主观经历，不归应用实行。

- 【应用实行、团体建造、主观经历、真理启示的判断顺序】
遇到"主干＋从句"或类似复合结构的句子，按以下顺序判断，前面命中就不再往下看：
① 从句/后半部分是否点名具体、可重复操练的动作或路径？是→应用实行。
② 是否走到团体实际（按团体建造标准中的判断角度）？是→团体建造。
③ 是否只讲操练后的里面感受或状态，未点名操练动作，也未走到团体？是→主观经历。
④ 以上都不是，即从句只是主干道理的自然延伸说明→整句仍归真理启示。

六、确定目标
- 判断依据：这句话是否在把整段负担的力度推向顶点、收束
- 需注意：确定目标通常出现在这段文字结尾，但有时也会在开头先点一下、跟结尾首尾呼应——不能默认这一项只会出现在结尾。但如果这句话只是在复述标题、交代整篇的背景主题（哪怕字面出现「目标」「终极完成」这类词），不算确定目标；只有当这句话是这篇负担自己论证到最后、真正起到收束作用的那一句，才归确定目标。判断的关键不是「有没有出现终极性的字眼」，而是「这句话有没有真正做到把这篇独有的力度推向顶点」
- 更具体的判断角度：这句话有没有一个清晰、可陈述的终极指向——可以是新耶路撒冷、基督身体的建造、神人调和的终极完成、预言的成全，也可以是个人生命长大成熟、模成、得荣、在生命中作王等，或是这篇纲目本身的中心主题；不拘个人或团体，关键看指向是否清晰有力，而不是指向哪一个具体异象"""

USER_PROMPT_TEMPLATE = """你的任务是：根据用户提供的「主题」与「负担说明」，将负担说明拆解、归入「六阶段」骨架。

━━━━━━━━━━━━━━━━━━━
⛔ 严格遵守
━━━━━━━━━━━━━━━━━━━

① 内容必须原样摘自负担说明原文，不改写、不扩写、不概括——每一项的「内容」字段，必须是负担说明里能逐字找到的句子或短语，不是你自己的转述。
② 六项并非每篇负担都要凑齐，缺一项、两项属正常情况，缺席的项不要勉强填入内容。
③ 同一项之下，也可能有好几处句子共同归入，不限一处。
④ 内部工作流程所有步骤均不输出，直接输出最终结果。
⑤ 输出的排列顺序：圣经根据、真理启示、主观经历、团体建造、应用实行这五项，严格按负担说明原文里句子出现的先后顺序排列，不归堆、不按六阶段固定顺序调整。确定目标是唯一的例外——不论它在负担说明原文的哪个位置出现（开头、中段、结尾都有可能），输出时永远排在整个列表的最后；如果确定目标出现不止一处，这几处之间仍按各自在原文里出现的先后顺序排列，只是作为一个整体挪到列表末尾。
⑥ 同一个完整句子如果内部有目的/结果从句（常见「使……」「让……」「以致……」「好……」这类连接词），且与前一分句共用同一主语脉络，必须合并成一条，不能拆成两条分别归类。只有当负担说明本身用句号、分号断开成两个独立句子时，才可以分开判断、分开归类。

【六阶段：参考背景】
以下六个阶段，是从宏观角度总结出来的参考方向——真理启示、主观经历、团体建造、应用实行，大致是从客观真理到个人经历、到团体、到实行这样一个逐步展开的方向感，圣经根据常在开篇、确定目标常在收束。但这只是宏观参考，不是每篇负担都会严格按这个顺序展开，实际顺序完全跟着负担说明原文走（见上方⑤）。

【六阶段判断依据】

""" + SIX_STAGE_CRITERIA + """

━━━━━━━━━━━━━━━━━━━
📌 内部工作流程（此过程不输出，直接输出最终结果）
━━━━━━━━━━━━━━━━━━━

第一步：通读负担说明全文，结合主题，理解整篇要讲的核心是什么。
第二步：按负担说明原文的行文顺序，把全文拆成若干个独立的意思单元（一句话、或一个分句），保持原文先后次序不变；注意⑥，目的/结果从句不能单独拆出来。
第三步：按原文顺序，逐一判断每个意思单元该归六阶段里的哪一项——依据是这句话「在做什么」，不是它「用了什么字眼」；同一个字眼（如「身体」「召会」「目标」「启示」）在不同位置，可能归属完全不同的项。
第四步：检查是否有意思单元被遗漏、没有归入任何一项；如果有，回到第三步重新判断。
第五步：对每一个意思单元，把归入的原文摘出来（不改写），并写一句简短的判断依据；输出时按⑤的排列规则整理顺序。

━━━━━━━━━━━━━━━━━━━
【用户输入】
━━━━━━━━━━━━━━━━━━━
- 主题：{主题}
- 负担说明：{负担说明}

━━━━━━━━━━━━━━━━━━━
【输出格式】（严格遵守，只输出以下格式，不输出任何其他文字）
━━━━━━━━━━━━━━━━━━━

①[类别名]
内容：[原样摘自负担说明的句子]
依据：[判断理由]

②[类别名]
内容：[...]
依据：[...]

（依此类推，编号连续往下排；顺序按上方⑤的规则排列）"""


CATEGORY_TO_FOLDER = {
    "真理类": "1真理启示",
    "生命类": "2生命经历",
    "实行类": "3应用实行",
}


def _load_api_key() -> str:
    load_dotenv(BACKEND_DIR / ".env")
    key = (os.getenv("CLAUDE_API_KEY") or "").strip()
    if not key:
        raise SystemExit("未找到 CLAUDE_API_KEY（请检查 back_mic/backend/.env）")
    return key


def build_user_prompt(topic: str, burden: str) -> str:
    return USER_PROMPT_TEMPLATE.replace("{主题}", topic).replace("{负担说明}", burden)


def call_claude(api_key: str, user_prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key, timeout=600.0)
    kwargs = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    last_empty_info = ""
    for attempt in range(2):
        if attempt:
            kwargs["max_tokens"] = max(int(kwargs["max_tokens"]), 16000)
        msg = client.messages.create(**kwargs)
        print(
            f"  API model={getattr(msg, 'model', MODEL)} "
            f"stop={getattr(msg, 'stop_reason', None)} attempt={attempt + 1}",
            flush=True,
        )
        parts = []
        block_types = []
        for block in msg.content or []:
            btype = getattr(block, "type", None) or type(block).__name__
            block_types.append(str(btype))
            if btype and btype != "text":
                continue
            text = getattr(block, "text", None)
            if text and str(text).strip():
                parts.append(str(text).strip())
        raw = "\n".join(parts).strip()
        if raw:
            return raw
        last_empty_info = (
            f"stop_reason={getattr(msg, 'stop_reason', None)} "
            f"block_types={block_types}"
        )
        print(f"  空正文，将重试 | {last_empty_info}", flush=True)
    raise RuntimeError(f"Claude 返回为空 | {last_empty_info}")


def process_one(item: dict, api_key: str) -> dict:
    topic = str(item.get("主题") or "").strip()
    burden = str(item.get("负担说明") or "").strip()
    if not topic or not burden:
        raise ValueError("缺少主题或负担说明")
    raw = call_claude(api_key, build_user_prompt(topic, burden))
    return {
        "id": item.get("id") or "",
        "分类": item.get("分类") or "",
        "主题": topic,
        "龙骨结果": raw,
    }


def merge_into_output(
    new_records: list[dict],
    *,
    input_json: Path = INPUT_JSON,
    output_json: Path = OUTPUT_JSON,
) -> None:
    existing: list[dict] = []
    if output_json.is_file():
        data = json.loads(output_json.read_text(encoding="utf-8"))
        if isinstance(data, list):
            existing = data
    by_id = {x.get("id"): x for x in existing}
    for rec in new_records:
        by_id[rec["id"]] = rec
    # 保持输入 JSON 的顺序
    items = json.loads(input_json.read_text(encoding="utf-8"))
    ordered = []
    seen = set()
    for item in items:
        rec_id = item.get("id")
        if rec_id in by_id:
            ordered.append(by_id[rec_id])
            seen.add(rec_id)
    for rec in existing:
        if rec.get("id") not in seen:
            ordered.append(rec)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="批量生成六阶段龙骨")
    parser.add_argument("--trial", action="store_true", help="只处理 JSON 第一条，打印结果，不写输出文件")
    parser.add_argument("--id", default="", help="只处理 id 包含该字符串的条目，并合并写回 JSON")
    parser.add_argument("--folder", default="", help="只处理对应分类，如 3应用实行")
    parser.add_argument("--exclude", default="", help="跳过 id 包含该字符串的条目")
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="自定义输入负担 JSON。不指定则用第一次测试/feast_burdens_30_sonnet5.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="自定义输出龙骨 JSON。不指定则写第一次测试/skeleton_results_30.json",
    )
    args = parser.parse_args()

    input_json = args.input.resolve() if args.input else INPUT_JSON
    output_json = args.output.resolve() if args.output else OUTPUT_JSON

    if not input_json.is_file():
        raise SystemExit(f"找不到输入文件: {input_json}")
    items = json.loads(input_json.read_text(encoding="utf-8"))
    if not isinstance(items, list) or not items:
        raise SystemExit("输入 JSON 不是非空列表")

    folder_to_cat = {v: k for k, v in CATEGORY_TO_FOLDER.items()}
    if args.trial:
        jobs = items[:1]
    elif args.id:
        jobs = [x for x in items if args.id in str(x.get("id") or "")]
        if not jobs:
            raise SystemExit(f"找不到 id 含「{args.id}」的条目")
    elif args.folder:
        cat = folder_to_cat.get(args.folder)
        if not cat:
            raise SystemExit(f"未知文件夹: {args.folder}")
        jobs = [x for x in items if x.get("分类") == cat]
        if not jobs:
            raise SystemExit(f"{args.folder} 下没有条目")
    else:
        jobs = items
    if args.exclude:
        jobs = [x for x in jobs if args.exclude not in str(x.get("id") or "")]
        if not jobs:
            raise SystemExit("排除后没有可处理的条目")

    api_key = _load_api_key()
    records: list[dict] = []
    errors: list[str] = []
    for i, item in enumerate(jobs, 1):
        rec_id = item.get("id") or f"#{i}"
        print(f"[{i}/{len(jobs)}] {item.get('分类', '')} {rec_id}", flush=True)
        try:
            rec = process_one(item, api_key)
        except Exception as e:
            errors.append(f"{rec_id}: {e}")
            print(f"  失败: {e}", flush=True)
            continue
        records.append(rec)
        print("---")
        print(rec["龙骨结果"])
        print("---")
        if records and not args.trial:
            merge_into_output(records, input_json=input_json, output_json=output_json)

    if records and not args.trial:
        merge_into_output(records, input_json=input_json, output_json=output_json)
        print(f"已合并写入 {output_json}（本次 {len(records)} 条）")
    if errors:
        print("失败列表：")
        for line in errors:
            print(f"  - {line}")


if __name__ == "__main__":
    main()
