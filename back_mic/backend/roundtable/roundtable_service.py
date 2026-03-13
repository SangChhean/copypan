"""
AI 圆桌会议核心调度逻辑（轮次管理、并发控制）
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List

# 复用 ai_search 已初始化的 redis_client
from ai_search.ai_service import redis_client

from .ai_clients import call_ai, RoundTableAIError
from .roundtable_db import save_record
from .roundtable_prompts import (
    build_scene_two_prompt,
    build_conclusion_prompt,
    build_scene_one_prompt,
    build_scene_one_conclusion_prompt,
    build_scene_three_round1_prompt,
    build_scene_three_round2_prompt,
    build_scene_three_round3_prompt,
    build_scene_three_conclusion_prompt,
    build_scene_four_prompt,
)

SESSION_KEY_PREFIX = "roundtable:session:"
SESSION_TTL = 24 * 3600  # 24 小时


class RoundTableService:
    async def create_session(
        self, scene_type: str, topic: str, participants: list, ai_roles: dict
    ) -> str:
        """创建圆桌 Session，写入 Redis，TTL 24 小时，返回 session_id。"""
        session_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        payload = {
            "session_id": session_id,
            "scene_type": scene_type,
            "topic": topic,
            "participants": participants,
            "ai_roles": ai_roles or {},
            "rounds": [],
            "status": "created",
            "created_at": created_at,
        }
        key = SESSION_KEY_PREFIX + session_id
        redis_client.setex(
            key,
            SESSION_TTL,
            json.dumps(payload, ensure_ascii=False),
        )
        return session_id

    async def get_session(self, session_id: str) -> dict:
        """从 Redis 取出 Session，找不到抛 ValueError。"""
        key = SESSION_KEY_PREFIX + session_id
        raw = redis_client.get(key)
        if raw is None:
            raise ValueError(f"Session {session_id} not found")
        return json.loads(raw)

    async def update_session(self, session_id: str, updates: dict) -> None:
        """取出现有 session，合并 updates，写回 Redis（保持 TTL 24 小时）。"""
        sess = await self.get_session(session_id)
        sess.update(updates)
        key = SESSION_KEY_PREFIX + session_id
        redis_client.setex(
            key,
            SESSION_TTL,
            json.dumps(sess, ensure_ascii=False),
        )

    async def run_scene_one(self, session_id: str):
        """
        场景①：十二支派。多AI并发独立历史神学研究，Claude 汇总。async generator。
        """
        await self.update_session(session_id, {"status": "running"})
        session = await self.get_session(session_id)
        participants: List[str] = session.get("participants") or []
        topic = session.get("topic") or ""
        all_speeches: Dict[str, List[str]] = {ai: [] for ai in participants}
        total_cost = 0.0

        system_prompt = "你是一位专业的历史神学研究者，请进行深度研究。"
        tasks = [(ai_name, build_scene_one_prompt(ai_name, topic)) for ai_name in participants]

        async def run_one(ai_name: str, pr: str):
            try:
                content, cost = await call_ai(ai_name, pr, system_prompt=system_prompt, scene_type="scene_one")
                return (ai_name, content, cost, None)
            except RoundTableAIError as e:
                return (ai_name, None, 0.0, e)

        for ai_name, _ in tasks:
            yield {"type": "speech_start", "round": 1, "ai": ai_name}

        async def run_one_wrapper(ai_name: str, pr: str):
            try:
                return (ai_name, await run_one(ai_name, pr))
            except Exception as e:
                return (ai_name, e)

        futs = [asyncio.ensure_future(run_one_wrapper(ai_name, pr)) for ai_name, pr in tasks]
        for fut in asyncio.as_completed(futs):
            ai_name, result = await fut
            if isinstance(result, Exception):
                all_speeches[ai_name].append("")
                yield {"type": "error", "ai": ai_name, "reason": str(result)}
            else:
                _, content, cost, err = result
                total_cost += cost
                if err is not None:
                    all_speeches[ai_name].append("")
                    yield {"type": "error", "ai": ai_name, "reason": str(err)}
                else:
                    all_speeches[ai_name].append(content)
                    yield {"type": "speech_chunk", "round": 1, "ai": ai_name, "content": content}
                    yield {"type": "speech_end", "round": 1, "ai": ai_name, "full_content": content}

        yield {"type": "round_complete", "round": 1}
        round_data = {ai: (all_speeches[ai][-1] if all_speeches[ai] else "") for ai in participants}
        sess = await self.get_session(session_id)
        await self.update_session(session_id, {"rounds": sess["rounds"] + [round_data]})

        all_responses_str = "".join(
            f"[{ai}]\n{(all_speeches[ai][0] if all_speeches[ai] else '')}\n\n"
            for ai in participants
        )
        conclusion_prompt = build_scene_one_conclusion_prompt(topic, all_responses_str)

        yield {"type": "conclusion_start"}
        try:
            conclusion, cost = await call_ai(
                "claude",
                conclusion_prompt,
                system_prompt="你是中立的神学历史学家",
                scene_type="scene_one",
            )
            total_cost += cost
        except RoundTableAIError as e:
            yield {"type": "error", "ai": "claude", "reason": str(e)}
            conclusion = ""
        yield {"type": "conclusion_chunk", "content": conclusion}
        yield {"type": "conclusion_end", "conclusion": conclusion, "total_cost": round(total_cost, 6)}

        await self.update_session(session_id, {"status": "done", "conclusion": conclusion})
        sess = await self.get_session(session_id)
        save_record({
            "record_id": session_id,
            "scene_type": sess.get("scene_type", "scene_one"),
            "topic": sess.get("topic", ""),
            "participants": sess.get("participants", []),
            "ai_roles": sess.get("ai_roles", {}),
            "rounds": sess.get("rounds", []),
            "conclusion": conclusion,
            "created_at": sess.get("created_at"),
            "is_pinned": False,
            "total_cost": total_cost,
        })

    async def run_scene_two(self, session_id: str):
        """
        场景②：3 轮辩论 + 结论。async generator，yield SSE 事件字典。
        不负责 HTTP/SSE 推送，只负责调度与状态管理。
        """
        await self.update_session(session_id, {"status": "running"})
        session = await self.get_session(session_id)
        participants: List[str] = session.get("participants") or []
        ai_roles: Dict[str, str] = session.get("ai_roles") or {}
        topic = session.get("topic") or ""
        # 每 AI 的历史发言列表，按轮次索引
        all_speeches: Dict[str, List[str]] = {ai: [] for ai in participants}
        # 立场名称 key，供 build_scene_two_prompt 使用
        all_stances = {ai_roles[ai]: ai_roles[ai] for ai in participants if ai in ai_roles}
        total_cost = 0.0

        for round_num in (1, 2, 3):
            # 本轮的 (ai_name, prompt) 列表；others_last_round 按当前 AI 计算
            tasks = []
            for ai_name in participants:
                if round_num == 1:
                    others_last_round = {}
                else:
                    others_last_round = {
                        ai_roles[other]: all_speeches[other][round_num - 2]
                        for other in participants
                        if other != ai_name
                        and other in ai_roles
                        and len(all_speeches.get(other, [])) >= round_num - 1
                    }
                stance = ai_roles.get(ai_name, "")
                prompt = build_scene_two_prompt(
                    ai_name, topic, stance, round_num, all_speeches[ai_name], others_last_round, all_stances=all_stances
                )
                tasks.append((ai_name, prompt))

            async def run_one(ai_name: str, pr: str):
                try:
                    content, cost = await call_ai(ai_name, pr, system_prompt="", scene_type=session.get("scene_type", "scene_two"))
                    return (ai_name, content, cost, None)
                except RoundTableAIError as e:
                    return (ai_name, None, 0.0, e)

            # 先 yield 所有 AI 的 speech_start
            for ai_name, _ in tasks:
                yield {"type": "speech_start", "round": round_num, "ai": ai_name}

            async def run_one_wrapper(ai_name: str, pr: str):
                try:
                    return (ai_name, await run_one(ai_name, pr))
                except Exception as e:
                    return (ai_name, e)

            futs = [asyncio.ensure_future(run_one_wrapper(ai_name, pr)) for ai_name, pr in tasks]
            for fut in asyncio.as_completed(futs):
                ai_name, result = await fut
                if isinstance(result, Exception):
                    all_speeches[ai_name].append("")
                    yield {"type": "error", "ai": ai_name, "reason": str(result)}
                else:
                    _, content, cost, err = result
                    total_cost += cost
                    if err is not None:
                        all_speeches[ai_name].append("")
                        yield {"type": "error", "ai": ai_name, "reason": str(err)}
                    else:
                        all_speeches[ai_name].append(content)
                        yield {"type": "speech_chunk", "round": round_num, "ai": ai_name, "content": content}
                        yield {"type": "speech_end", "round": round_num, "ai": ai_name, "full_content": content}

            yield {"type": "round_complete", "round": round_num}
            # 本轮记录：{ai: content}
            round_data = {ai: (all_speeches[ai][-1] if all_speeches[ai] else "") for ai in participants}
            sess = await self.get_session(session_id)
            await self.update_session(session_id, {"rounds": sess["rounds"] + [round_data]})

        # 结论
        all_stances_str = "".join(
            f"{ai_roles[ai]}\n"
            for ai in participants if ai in ai_roles
        )
        rounds_data = [
            {ai: (all_speeches[ai][r] if r < len(all_speeches.get(ai, [])) else "") for ai in participants}
            for r in range(3)
        ]
        all_speeches_str = ""
        for round_idx, round_data in enumerate(rounds_data):
            all_speeches_str += f"第{round_idx + 1}轮\n"
            for ai, content in round_data.items():
                stance_label = ai_roles.get(ai, ai)
                all_speeches_str += f"[{stance_label}]：{content}\n\n"
        conclusion_prompt = build_conclusion_prompt(topic, all_stances_str, all_speeches_str)

        yield {"type": "conclusion_start"}
        try:
            conclusion, cost = await call_ai("claude", conclusion_prompt, system_prompt="你是中立的神学裁判", scene_type="scene_two")
            total_cost += cost
        except RoundTableAIError as e:
            yield {"type": "error", "ai": "claude", "reason": str(e)}
            conclusion = ""
        yield {"type": "conclusion_chunk", "content": conclusion}
        yield {"type": "conclusion_end", "conclusion": conclusion, "total_cost": round(total_cost, 6)}

        await self.update_session(session_id, {"status": "done", "conclusion": conclusion})
        sess = await self.get_session(session_id)
        save_record({
            "record_id": session_id,
            "scene_type": sess.get("scene_type", "scene_two"),
            "topic": sess.get("topic", ""),
            "participants": sess.get("participants", []),
            "ai_roles": sess.get("ai_roles", {}),
            "rounds": sess.get("rounds", []),
            "conclusion": conclusion,
            "created_at": sess.get("created_at"),
            "is_pinned": False,
            "total_cost": total_cost,
        })

    async def run_scene_three(self, session_id: str):
        """
        场景③：重大讨论。第一轮各 AI 作答，第二轮互相指出（至少点评 2～3 人），第三轮对题目本身做最终评价，Claude 总结。
        """
        await self.update_session(session_id, {"status": "running"})
        session = await self.get_session(session_id)
        participants: List[str] = session.get("participants") or []
        topic = session.get("topic") or ""
        all_speeches: Dict[str, List[str]] = {ai: [] for ai in participants}
        total_cost = 0.0

        async def run_one(ai_name: str, prompt: str, system_prompt: str = ""):
            try:
                content, cost = await call_ai(
                    ai_name, prompt, system_prompt=system_prompt, scene_type="scene_three"
                )
                return (ai_name, content, cost, None)
            except RoundTableAIError as e:
                return (ai_name, None, 0.0, e)

        # 第一轮：各 AI 独立作答
        round1_prompt = build_scene_three_round1_prompt(topic)
        tasks_r1 = [(ai_name, round1_prompt) for ai_name in participants]
        for ai_name, _ in tasks_r1:
            yield {"type": "speech_start", "round": 1, "ai": ai_name}

        async def run_one_wrapper(ai_name: str, pr: str):
            try:
                return (ai_name, await run_one(ai_name, pr, ""))
            except Exception as e:
                return (ai_name, e)

        futs = [asyncio.ensure_future(run_one_wrapper(ai_name, pr)) for ai_name, pr in tasks_r1]
        for fut in asyncio.as_completed(futs):
            ai_name, result = await fut
            if isinstance(result, Exception):
                all_speeches[ai_name].append("")
                yield {"type": "error", "ai": ai_name, "reason": str(result)}
            else:
                _, content, cost, err = result
                total_cost += cost
                if err is not None:
                    all_speeches[ai_name].append("")
                    yield {"type": "error", "ai": ai_name, "reason": str(err)}
                else:
                    all_speeches[ai_name].append(content)
                    yield {"type": "speech_chunk", "round": 1, "ai": ai_name, "content": content}
                    yield {"type": "speech_end", "round": 1, "ai": ai_name, "full_content": content}

        yield {"type": "round_complete", "round": 1}
        round1_data = {ai: (all_speeches[ai][-1] if all_speeches[ai] else "") for ai in participants}
        sess = await self.get_session(session_id)
        await self.update_session(session_id, {"rounds": sess["rounds"] + [round1_data]})

        # 第二轮：互相指出（至少点评 2～3 人）
        for ai_name in participants:
            yield {"type": "speech_start", "round": 2, "ai": ai_name}
        tasks_r2 = [
            (
                ai_name,
                build_scene_three_round2_prompt(ai_name, topic, round1_data, participants),
            )
            for ai_name in participants
        ]
        futs_r2 = [asyncio.ensure_future(run_one_wrapper(ai_name, pr)) for ai_name, pr in tasks_r2]
        for fut in asyncio.as_completed(futs_r2):
            ai_name, result = await fut
            if isinstance(result, Exception):
                all_speeches[ai_name].append("")
                yield {"type": "error", "ai": ai_name, "reason": str(result)}
            else:
                _, content, cost, err = result
                total_cost += cost
                if err is not None:
                    all_speeches[ai_name].append("")
                    yield {"type": "error", "ai": ai_name, "reason": str(err)}
                else:
                    all_speeches[ai_name].append(content)
                    yield {"type": "speech_chunk", "round": 2, "ai": ai_name, "content": content}
                    yield {"type": "speech_end", "round": 2, "ai": ai_name, "full_content": content}

        yield {"type": "round_complete", "round": 2}
        round2_data = {ai: (all_speeches[ai][-1] if all_speeches[ai] else "") for ai in participants}
        sess = await self.get_session(session_id)
        await self.update_session(session_id, {"rounds": sess["rounds"] + [round2_data]})

        # 第三轮：对题目本身做最终评价
        for ai_name in participants:
            yield {"type": "speech_start", "round": 3, "ai": ai_name}
        tasks_r3 = [
            (
                ai_name,
                build_scene_three_round3_prompt(
                    ai_name, topic, round1_data, round2_data, participants
                ),
            )
            for ai_name in participants
        ]
        futs_r3 = [asyncio.ensure_future(run_one_wrapper(ai_name, pr)) for ai_name, pr in tasks_r3]
        for fut in asyncio.as_completed(futs_r3):
            ai_name, result = await fut
            if isinstance(result, Exception):
                all_speeches[ai_name].append("")
                yield {"type": "error", "ai": ai_name, "reason": str(result)}
            else:
                _, content, cost, err = result
                total_cost += cost
                if err is not None:
                    all_speeches[ai_name].append("")
                    yield {"type": "error", "ai": ai_name, "reason": str(err)}
                else:
                    all_speeches[ai_name].append(content)
                    yield {"type": "speech_chunk", "round": 3, "ai": ai_name, "content": content}
                    yield {"type": "speech_end", "round": 3, "ai": ai_name, "full_content": content}

        yield {"type": "round_complete", "round": 3}
        round3_data = {ai: (all_speeches[ai][-1] if all_speeches[ai] else "") for ai in participants}
        sess = await self.get_session(session_id)
        await self.update_session(session_id, {"rounds": sess["rounds"] + [round3_data]})

        # 结论：Claude 总结
        rounds_data = [round1_data, round2_data, round3_data]
        round_titles = ["第1轮·作答", "第2轮·互相指出", "第3轮·最终评价"]
        all_speeches_str = ""
        for idx, r_data in enumerate(rounds_data):
            all_speeches_str += f"{round_titles[idx]}\n"
            all_speeches_str += "".join(
                f"[{ai}]：{(r_data.get(ai) or '')}\n\n" for ai in participants
            )
        conclusion_prompt = build_scene_three_conclusion_prompt(topic, all_speeches_str)

        yield {"type": "conclusion_start"}
        try:
            conclusion, cost = await call_ai(
                "claude",
                conclusion_prompt,
                system_prompt="你是讨论主持人，负责客观总结",
                scene_type="scene_three",
            )
            total_cost += cost
        except RoundTableAIError as e:
            yield {"type": "error", "ai": "claude", "reason": str(e)}
            conclusion = ""
        yield {"type": "conclusion_chunk", "content": conclusion}
        yield {"type": "conclusion_end", "conclusion": conclusion, "total_cost": round(total_cost, 6)}

        await self.update_session(session_id, {"status": "done", "conclusion": conclusion})
        sess = await self.get_session(session_id)
        save_record({
            "record_id": session_id,
            "scene_type": sess.get("scene_type", "scene_three"),
            "topic": sess.get("topic", ""),
            "participants": sess.get("participants", []),
            "ai_roles": sess.get("ai_roles", {}),
            "rounds": sess.get("rounds", []),
            "conclusion": conclusion,
            "created_at": sess.get("created_at"),
            "is_pinned": False,
            "total_cost": total_cost,
        })

    async def run_scene_four(self, session_id: str):
        """
        场景④：顶级模型思考。仅一轮回答，无总结；participants 仅 1 个（claude_opus / gpt_pro / gemini_pro）。
        """
        await self.update_session(session_id, {"status": "running"})
        session = await self.get_session(session_id)
        participants: List[str] = session.get("participants") or []
        topic = session.get("topic") or ""
        if len(participants) != 1:
            yield {"type": "error", "ai": participants[0] if participants else "?", "reason": "场景④ 仅支持选择 1 个 AI"}
            return
        ai_name = participants[0]
        total_cost = 0.0

        prompt = build_scene_four_prompt(topic)
        yield {"type": "speech_start", "round": 1, "ai": ai_name}
        try:
            content, cost = await call_ai(
                ai_name,
                prompt,
                system_prompt="你是一位善于深度思考与分析的助手。",
                scene_type="scene_four",
            )
            total_cost += cost
            yield {"type": "speech_chunk", "round": 1, "ai": ai_name, "content": content}
            yield {"type": "speech_end", "round": 1, "ai": ai_name, "full_content": content}
        except RoundTableAIError as e:
            yield {"type": "error", "ai": ai_name, "reason": str(e)}
            content = ""
        except Exception as e:
            yield {"type": "error", "ai": ai_name, "reason": str(e)}
            content = ""

        yield {"type": "round_complete", "round": 1}
        round_data = {ai_name: content}
        sess = await self.get_session(session_id)
        await self.update_session(session_id, {"rounds": sess["rounds"] + [round_data], "status": "done"})
        yield {"type": "conclusion_end", "conclusion": "", "total_cost": round(total_cost, 6)}
        save_record({
            "record_id": session_id,
            "scene_type": "scene_four",
            "topic": sess.get("topic", ""),
            "participants": sess.get("participants", []),
            "ai_roles": {},
            "rounds": sess.get("rounds", []) + [round_data],
            "conclusion": "",
            "created_at": sess.get("created_at"),
            "is_pinned": False,
            "total_cost": total_cost,
        })
