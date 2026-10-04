# -*- coding: utf-8 -*-
"""SC 直写版（v3）默认模板：C0–C12 / P1–P12 精确替换。

加词条定义版与 exp_bc 共用 apply_ref_v3_transforms / build_ref_prompt_default_v3。
"""
from __future__ import annotations

from .config import PLAIN_NEW, PLAIN_OLD


class ReplaceError(RuntimeError):
    pass


def exact_replace_once(text: str, old: str, new: str, *, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise ReplaceError(f"{label}：在底稿中出现 {n} 次（期望 1），停止")
    return text.replace(old, new, 1)


def exact_delete_once(text: str, old: str, *, label: str) -> str:
    return exact_replace_once(text, old, "", label=label)


# ----- C / 加词条定义版 v3 -----

C0_OLD = (
    "· 凡依据这些定义写出的界定，在【职事界定】的「依据」处写「参考材料·词条名」；"
    "取自定义原文的说法，记忆程度可标「原用语」。"
)
C0_NEW = "· 用到的词条，在文末【用到的参考材料】里列出词条名。"

C1_OLD = "；【职事界定】与【真理脉络】不计入字数"
C1_NEW = "；【用到的参考材料】不计入字数"

C2_OLD = "②依次输出【职事界定】【真理脉络】【负担说明】三段，格式见文末【输出格式】；其余步骤不输出。"
C2_NEW = "②依次输出【负担说明】【用到的参考材料】两段，格式见文末【输出格式】；其余步骤不输出。"

C3_OLD = (
    "此条同样适用于【职事界定】与【真理脉络】所写的依据："
    "没有把握的经文不写，改写职事材料的出处范围，或舍去。"
)

C4_OLD = "（包括记得不准、按第二步规则标为「印象」的）"
C4_NEW = "（记得不准的，不可写成确定的说法）"

C5_OLD = "目标必须是【真理脉络】的终点"
C5_NEW = "目标必须是负担说明的终点"

C6_OLD = (
    "但六阶段不是构思的框架，而是检查【真理脉络】的标准（见第五步）："
    "每一项都要挂在脉络的某一环上；负担说明照着脉络写，六项就自然覆盖。"
    "某一项挂不上，要回头补脉络，不可在负担说明里补一个词凑数。"
)
C6_NEW = (
    "但六阶段不是构思的框架，而是检查负担说明的标准（见第五步）："
    "负担说明照着真理本身的推进来写，写完后逐项对照，缺项的回头改写，不可补一个词凑数。"
)

C7_OLD = "可在【真理脉络】第0行下注明「团体面：本题不明显」，不可临时补出"
C7_NEW = "可不写这一面，不可临时补出"

C8_OLD = "只用在【真理脉络】；负担说明里的机理"
C8_NEW = "不用于负担说明；机理"

C9_OLD = "第七步检查用词时参考"
C9_NEW = "第五步检查用词时参考"

C11_STEP2_REF = (
    "第二步：读参考材料——逐条读文首【词条定义】，找出与本题直接相关的职事说法；"
    "用在负担说明里的，尽量采用定义中最合适的原用语和句式。"
    "参考材料没有而本题确需的，才用你所知道的职事信息补，补的须有把握。"
)

C11_STEP2_PLAIN = (
    "第二步：回想职事信息——先想本题的关键经文，以及职事怎样讲解这些经文；"
    "旧约的题目，同时想新约怎样解释这段经文。再对照上方【扫描角度】逐一想一遍，补上遗漏的角度；"
    "某个角度没有内容，不必勉强补上。只取职事信息方向的说法，不用一般基督教的解释补充；"
    "写成本题的具体形式，换一个篇题也能照搬的通用说法不取；记不准的，不可写成确定的说法，也不可编造经文或篇名。"
)

_C11_FRAME = """【写作步骤】（第一步至第四步在内部完成，不输出；第四步写成负担说明；第五步为内部检查，不输出）

━━━━━━━━━━━━━━━━━━━

第一步：篇题结构分析——拆解篇题的核心名词，以及「并」「而」「以致」等这类连接词，判断各自表示凭借、过程还是结果。

{STEP2}

第三步：定核心命题——用一句含有凭借与结果的话写成命题（例如「借着……，以致……」），写出「在本题中，神把什么作到人里面，人因此成为什么」；若本题确实没有这一面，不勉强写。命题须回应篇题的每个关键词。

第四步：写成负担说明，字数控制在360字左右——
·按真理本身的推进顺序写，一句一个要点，以句号结束；并列的要点可共用一句，用分号分开。核心命题并入开头第一句，不另外成句。确定目标放在最后收束。
·每句要写出这一点与上一点的凭借或因果关系；可以用回指承接上一句（如「这生命」「这供应」），不重述上一句的内容，把字数留给凭借。
·六阶段各项不另占句子，嵌进句子里。
·经文只标出处、不引原文，全篇以2-3处为宜；经文只在有把握时才用（见⛔④）。
·不用同义并列的修饰语。

第五步：总检查——
·字数是否在360字左右；六阶段名称是否被写进正文（若有须删去）；引用的经文是否确实存在、且对应得上要讲的真理点。
·六阶段六项是否都有对应内容（团体建造一项按上文可不写的情形除外）。
·相邻两句之间，能否说出后一句为什么接在前一句后面；删掉某一句，推进会不会断；不会断的就是填充句，要删去或改写。
·每个关系连接词后面，是否有实际内容。
·应用是否写出人怎样配合神在人里面的作为，并出自本题特有的机理；换一个篇题也能照搬的，或只是照做人物外在行为的，不合格。
·是否使用了职事信息的惯用术语（可参考💡职事风格参考）。
"""

C11_NEW = _C11_FRAME.format(STEP2=C11_STEP2_REF)
C11_NEW_PLAIN = _C11_FRAME.format(STEP2=C11_STEP2_PLAIN)

C12_NEW = """【负担说明】[360字左右]

【用到的参考材料】词条名、词条名、……（只列词条名，用顿号隔开）
"""

C12_NEW_PLAIN = """【负担说明】[360字左右]
"""

# ----- 普通版 v3 专用 -----

P1_OLD = "；【职事界定】与【真理脉络】不计入字数。"
P1_NEW = "。"

P2_OLD = "②依次输出【职事界定】【真理脉络】【负担说明】三段，格式见文末【输出格式】；其余步骤不输出。"
P2_NEW = "②只输出【负担说明】一段，格式见文末【输出格式】；其余步骤不输出。"

P10_OLD = "🔍扫描角度（供第二步第(3)轮查漏使用）"
P10_NEW = "🔍扫描角度（供第二步回想时查漏使用）"


def _scan_angle_block(draft: str) -> str:
    start = draft.find("━━━━━━━━━━━━━━━━━━━\n🔍扫描角度（供第二步第(3)轮查漏使用）")
    if start < 0:
        raise ReplaceError("C10：找不到扫描角度标题块")
    end = draft.find("━━━━━━━━━━━━━━━━━━━\n【写作步骤】", start)
    if end < 0:
        raise ReplaceError("C10：找不到【写作步骤】标题块")
    return draft[start:end]


def _writing_steps_block(draft: str) -> str:
    start = draft.find(
        "【写作步骤】（第一步至第五步的结果体现在【职事界定】【真理脉络】两段里；"
        "第六步写成【负担说明】；第七步为内部检查，不输出）"
    )
    if start < 0:
        raise ReplaceError("C11/P11：找不到【写作步骤】标题行")
    end = draft.find("━━━━━━━━━━━━━━━━━━━\n【用户输入】", start)
    if end < 0:
        raise ReplaceError("C11/P11：找不到【用户输入】标题块")
    return draft[start:end]


def _output_format_tail(draft: str) -> str:
    title = "【输出格式】（严格遵守）"
    idx = draft.find(title)
    if idx < 0:
        raise ReplaceError("C12/P12：找不到【输出格式】标题")
    return draft[idx + len(title) :]


def apply_ref_v3_transforms(draft: str) -> tuple[str, list[str]]:
    """对「参考块+v0.3(PLAIN已换)」底稿应用 C0–C12。"""
    applied: list[str] = []
    text = draft
    text = exact_replace_once(text, C0_OLD, C0_NEW, label="C0")
    applied.append("C0")
    text = exact_replace_once(text, C1_OLD, C1_NEW, label="C1")
    applied.append("C1")
    text = exact_replace_once(text, C2_OLD, C2_NEW, label="C2")
    applied.append("C2")
    text = exact_delete_once(text, C3_OLD, label="C3")
    applied.append("C3")
    text = exact_replace_once(text, C4_OLD, C4_NEW, label="C4")
    applied.append("C4")
    text = exact_replace_once(text, C5_OLD, C5_NEW, label="C5")
    applied.append("C5")
    text = exact_replace_once(text, C6_OLD, C6_NEW, label="C6")
    applied.append("C6")
    text = exact_replace_once(text, C7_OLD, C7_NEW, label="C7")
    applied.append("C7")
    text = exact_replace_once(text, C8_OLD, C8_NEW, label="C8")
    applied.append("C8")
    text = exact_replace_once(text, C9_OLD, C9_NEW, label="C9")
    applied.append("C9")
    block = _scan_angle_block(text)
    text = exact_delete_once(text, block, label="C10")
    applied.append("C10")
    c11 = _writing_steps_block(text)
    text = exact_replace_once(text, c11, C11_NEW.rstrip("\n") + "\n", label="C11")
    applied.append("C11")
    tail = _output_format_tail(text)
    text = exact_replace_once(text, tail, "\n" + C12_NEW, label="C12")
    applied.append("C12")
    return text, applied


def apply_plain_v3_transforms(plain_v03: str) -> tuple[str, list[str]]:
    """对 Prompt1 v0.3 原文应用 P1–P12。"""
    applied: list[str] = []
    text = plain_v03
    text = exact_replace_once(text, P1_OLD, P1_NEW, label="P1")
    applied.append("P1")
    text = exact_replace_once(text, P2_OLD, P2_NEW, label="P2")
    applied.append("P2")
    text = exact_delete_once(text, C3_OLD, label="P3")
    applied.append("P3")
    text = exact_replace_once(text, C4_OLD, C4_NEW, label="P4")
    applied.append("P4")
    text = exact_replace_once(text, C5_OLD, C5_NEW, label="P5")
    applied.append("P5")
    text = exact_replace_once(text, C6_OLD, C6_NEW, label="P6")
    applied.append("P6")
    text = exact_replace_once(text, C7_OLD, C7_NEW, label="P7")
    applied.append("P7")
    text = exact_replace_once(text, C8_OLD, C8_NEW, label="P8")
    applied.append("P8")
    text = exact_replace_once(text, C9_OLD, C9_NEW, label="P9")
    applied.append("P9")
    text = exact_replace_once(text, P10_OLD, P10_NEW, label="P10")
    applied.append("P10")
    c11 = _writing_steps_block(text)
    text = exact_replace_once(text, c11, C11_NEW_PLAIN.rstrip("\n") + "\n", label="P11")
    applied.append("P11")
    tail = _output_format_tail(text)
    text = exact_replace_once(text, tail, "\n" + C12_NEW_PLAIN, label="P12")
    applied.append("P12")
    return text, applied


def build_ref_prompt_v1_block_only_local(plain_v03: str, ref_block: str) -> str:
    patched = exact_replace_once(plain_v03, PLAIN_OLD, PLAIN_NEW, label="Prompt1 v0.3 PLAIN 原句")
    return ref_block + patched


def build_ref_prompt_default_v3(plain_v03: str, ref_block: str) -> str:
    """直写版（v3）加词条定义版默认模板（未填占位符）。"""
    draft = build_ref_prompt_v1_block_only_local(plain_v03, ref_block)
    text, _ = apply_ref_v3_transforms(draft)
    return text


def build_plain_prompt_default_v3(plain_v03: str) -> str:
    text, _ = apply_plain_v3_transforms(plain_v03)
    return text


def build_ref_prompt_default_v2(plain_v03: str, ref_block: str) -> str:
    """参考优先版（v2）留档用。"""
    from .config import REF_V2_BASIS_NEW, REF_V2_BASIS_OLD, REF_V2_STEP2_NEW, REF_V2_STEP2_OLD

    patched = exact_replace_once(plain_v03, PLAIN_OLD, PLAIN_NEW, label="Prompt1 v0.3 PLAIN 原句")
    patched = exact_replace_once(patched, REF_V2_STEP2_OLD, REF_V2_STEP2_NEW, label="v2 第二步")
    patched = exact_replace_once(patched, REF_V2_BASIS_OLD, REF_V2_BASIS_NEW, label="v2 依据类型")
    return ref_block + patched
