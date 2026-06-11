<script setup>
import { ref, computed, onMounted } from "vue";
import ToolsHeader from "@/components/toolbox/ToolsHeader.vue";

import claudeAvatar from "@/assets/roundtable/claude.png";
import gptAvatar from "@/assets/roundtable/gpt.png";
import geminiAvatar from "@/assets/roundtable/gemini.png";
import grokAvatar from "@/assets/roundtable/grok.png";
import deepseekAvatar from "@/assets/roundtable/deepseek.png";
import perplexityAvatar from "@/assets/roundtable/perplexity.png";

const AI_LIST = [
  { key: "claude", label: "Claude", desc: "Anthropic", avatar: claudeAvatar },
  { key: "gpt", label: "GPT", desc: "OpenAI", avatar: gptAvatar },
  { key: "gemini", label: "Gemini", desc: "Google", avatar: geminiAvatar },
  { key: "grok", label: "Grok", desc: "xAI", avatar: grokAvatar },
  { key: "deepseek", label: "DeepSeek", desc: "DeepSeek", avatar: deepseekAvatar },
  { key: "perplexity", label: "Perplexity", desc: "Perplexity", avatar: perplexityAvatar },
];

/** 轮次内发言固定顺序（与 AI_LIST 一致） */
const AI_ORDER = ["claude", "gpt", "gemini", "grok", "deepseek", "perplexity"];

/** 场景④ 顶级模型思考：三选一 */
const SCENE4_AI_LIST = [
  { key: "claude_opus", label: "Claude Opus 4.6", desc: "thinking" },
  { key: "gpt_pro", label: "GPT-5.4", desc: "pro" },
  { key: "gemini_pro", label: "Gemini 3.1 Pro", desc: "" },
];
const SCENE4_ORDER = ["claude_opus", "gpt_pro", "gemini_pro"];

const getAvatar = (aiKey) => {
  const scene4 = SCENE4_AI_LIST.find((a) => a.key === aiKey);
  if (scene4) {
    if (aiKey === "claude_opus") return claudeAvatar;
    if (aiKey === "gpt_pro") return gptAvatar;
    if (aiKey === "gemini_pro") return geminiAvatar;
  }
  return AI_LIST.find((a) => a.key === aiKey)?.avatar || "";
};

const getDisplayName = (aiKey) => {
  if (runSceneType.value === "scene_two" && stances.value[aiKey]) {
    return stances.value[aiKey];
  }
  return aiKey;
};

const getSpeakerName = (ai) => {
  if (runSceneType.value === "scene_two" && stances.value[ai]) return stances.value[ai];
  const s4 = SCENE4_AI_LIST.find((a) => a.key === ai);
  if (s4) return s4.desc ? `${s4.label}（${s4.desc}）` : s4.label;
  return ai;
};

const cleanMarkdown = (text) => {
  if (!text) return "";
  return String(text)
    .replace(/\*\*(.+?)\*\*/gs, "$1")
    .replace(/\*(.+?)\*/gs, "$1")
    .replace(/#{1,6}\s+/g, "")
    .replace(/`(.+?)`/g, "$1")
    .replace(/^\s*[-*]\s+/gm, "");
};

const topic = ref("");
const selectedAIs = ref([]);
const selectedScene4Ai = ref(""); // 场景④ 单选：claude_opus | gpt_pro | gemini_pro
const sceneType = ref("scene_two");
const stances = ref({
  claude: "",
  gpt: "",
  gemini: "",
  grok: "",
  deepseek: "",
  perplexity: "",
});
const isLoading = ref(false);

const sessionId = ref("");
const speeches = ref([]); // 每条格式：{ round: 1, ai: 'claude', content: '...', displayContent: '', done: false, typing: false }
const endedSpeeches = ref({}); // { '1': ['claude', 'gpt', ...] } 每轮已收到 speech_end 的 AI
const sceneOneTypedAis = ref([]); // 场景①已完成打字机的AI列表
const sceneOneEndedAis = ref([]); // 场景①已收到speech_end的AI列表
const typingQueue = ref([]); // 待执行的轮次队列，严格串行
const isTyping = ref(false);
const currentRound = ref(0);
const conclusion = ref("");
const errorMsg = ref("");
const conclusionLoading = ref(false);

const showProgress = ref(false);
const configCollapsed = ref(false);
const roundDone = ref(false);

const showConclusion = computed(
  () =>
    (conclusionLoading.value || conclusion.value.length > 0) &&
    typingQueue.value.length === 0 &&
    !isTyping.value
);
const showConclusionOrScene4Done = computed(
  () => showConclusion.value || (roundDone.value && runSceneType.value === "scene_four")
);

const historyList = ref([]);
const historyLoading = ref(false);
const runSceneType = ref("scene_two"); // 当前运行的场景，用于进行区标题
const totalCost = ref(0);

const sceneOptions = [
  { value: "scene_two", label: "神学辩论", desc: "3轮交锋 · 结论" },
  { value: "scene_one", label: "十二支派", desc: "历史神学研究 · 汇总" },
  { value: "scene_three", label: "重大讨论", desc: "作答 → 互相指出 → 最终评价 · 总结" },
  { value: "scene_four", label: "顶级模型思考", desc: "单轮深度思考 · 无总结" },
];

const sceneDesc = computed(() => {
  if (sceneType.value === "scene_one") return "十二支派：多AI并行历史神学研究，综合汇总";
  if (sceneType.value === "scene_three") return "重大讨论：第一轮各AI作答，第二轮互相点评（至少2～3人），第三轮对题目做最终评价，Claude 总结";
  if (sceneType.value === "scene_four") return "顶级模型思考：从 Claude Opus 4.6（thinking）、GPT-5.4（pro）、Gemini 3.1 Pro 中选一个，单轮深度思考，无总结";
  return "神学辩论：3轮交锋 + 中立结论";
});

const topicPlaceholder = computed(() => {
  if (sceneType.value === "scene_one")
    return '请输入研究题目，例如：已过两千年来，基督教界对"因信称义"的看法如何？';
  if (sceneType.value === "scene_three")
    return "请输入讨论题目或材料（可粘贴整篇文章），例如：请讨论初信者如何建立晨兴习惯";
  if (sceneType.value === "scene_four")
    return "请输入希望 AI 深度思考的题目或材料";
  return "请输入辩论题目，例如：因信称义";
});

const canStart = computed(() => {
  const topicOk = (topic.value || "").trim().length > 0;
  if (sceneType.value === "scene_four") {
    return topicOk && !!selectedScene4Ai.value;
  }
  const n = selectedAIs.value.length;
  const countOk = n >= 2 && n <= 6;
  if (sceneType.value === "scene_one" || sceneType.value === "scene_three") {
    return topicOk && countOk;
  }
  const allStancesOk = selectedAIs.value.every(
    (k) => (stances.value[k] || "").trim().length > 0
  );
  return topicOk && countOk && allStancesOk;
});

const typewriterEffect = (s) => {
  const fullText = cleanMarkdown(s.content);
  return new Promise((resolve) => {
    let i = 0;
    s.typing = true;
    const timer = setInterval(() => {
      i += 5;
      s.displayContent = fullText.slice(0, i);
      if (i >= fullText.length) {
        s.displayContent = fullText;
        s.done = true;
        s.typing = false;
        clearInterval(timer);
        resolve();
      }
    }, 50);
  });
};

const startTypingQueue = async (round) => {
  const order = runSceneType.value === "scene_four" ? SCENE4_ORDER : AI_ORDER;
  const roundSpeeches = order.map((ai) =>
    speeches.value.find((s) => s.round === round && s.ai === ai)
  ).filter(Boolean);
  for (const s of roundSpeeches) {
    await typewriterEffect(s);
  }
};

const enqueueRound = (round) => {
  typingQueue.value.push(round);
  if (!isTyping.value) {
    processNextRound();
  }
};

const tryAdvanceSceneOne = async () => {
  if (isTyping.value) return;
  // 按AI_ORDER找下一个还没打字机的AI
  const nextAi = AI_ORDER.find(
    (ai) =>
      speeches.value.some((sp) => sp.round === 1 && sp.ai === ai) &&
      !sceneOneTypedAis.value.includes(ai)
  );
  if (!nextAi) return;
  // 如果下一个AI还没收到speech_end，停止等待
  if (!sceneOneEndedAis.value.includes(nextAi)) return;
  const s = speeches.value.find((sp) => sp.round === 1 && sp.ai === nextAi);
  if (!s) return;
  isTyping.value = true;
  await typewriterEffect(s);
  sceneOneTypedAis.value.push(nextAi);
  isTyping.value = false;
  await tryAdvanceSceneOne();
};

const processNextRound = async () => {
  if (typingQueue.value.length === 0) {
    isTyping.value = false;
    return;
  }
  isTyping.value = true;
  const round = typingQueue.value.shift();
  // 当轮发言按 AI_ORDER 排序后再进入打字机，保证显示顺序一致
  const order = runSceneType.value === "scene_four" ? SCENE4_ORDER : AI_ORDER;
  speeches.value.sort(
    (a, b) =>
      a.round - b.round ||
      order.indexOf(a.ai) - order.indexOf(b.ai)
  );
  await startTypingQueue(round);
  await processNextRound();
};

const handleSSEEvent = (event, sse) => {
  if (event.type === "speech_start") {
    currentRound.value = event.round;
    speeches.value.push({
      round: event.round,
      ai: event.ai,
      content: "",
      displayContent: "",
      done: false,
      typing: false,
    });
  } else if (event.type === "speech_chunk") {
    const s = speeches.value.find(
      (sp) => sp.round === event.round && sp.ai === event.ai
    );
    if (s) s.content += event.content;
  } else if (event.type === "speech_end") {
    const s = speeches.value.find(
      (sp) => sp.round === event.round && sp.ai === event.ai
    );
    if (s) s.content = event.full_content ?? s.content;

    if (!endedSpeeches.value[event.round]) endedSpeeches.value[event.round] = [];
    endedSpeeches.value[event.round].push(event.ai);

    const roundParticipants = speeches.value
      .filter((sp) => sp.round === event.round)
      .map((sp) => sp.ai);
    const allEnded = roundParticipants.every((ai) =>
      endedSpeeches.value[event.round]?.includes(ai)
    );
    if (runSceneType.value === "scene_one") {
      sceneOneEndedAis.value.push(event.ai);
      tryAdvanceSceneOne();
    } else if (runSceneType.value === "scene_two" || runSceneType.value === "scene_three" || runSceneType.value === "scene_four") {
      if (allEnded) {
        enqueueRound(event.round);
      }
    }
  } else if (event.type === "conclusion_start") {
    conclusionLoading.value = true;
  } else if (event.type === "conclusion_chunk") {
    conclusion.value += event.content;
  } else if (event.type === "conclusion_end") {
    conclusionLoading.value = false;
    roundDone.value = true;
    totalCost.value = event.total_cost ?? 0;
    loadHistory();
    sse.close();
  } else if (event.type === "error") {
    errorMsg.value = `${event.ai} 出错：${event.reason}`;
  }
};

const handleStart = async () => {
  if (!canStart.value) return;
  isLoading.value = true;
  errorMsg.value = "";
  speeches.value = [];
  endedSpeeches.value = {};
  typingQueue.value = [];
  isTyping.value = false;
  sceneOneTypedAis.value = [];
  sceneOneEndedAis.value = [];
  conclusion.value = "";
  showProgress.value = false;
  roundDone.value = false;
  totalCost.value = 0;

  try {
    const token = localStorage.getItem("token");
    runSceneType.value = sceneType.value;

    const apiBase =
      (import.meta.env && import.meta.env.VITE_API_BASE) || "";
    const res = await fetch(`${apiBase}/api/roundtable/start`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        scene_type: sceneType.value,
        topic: topic.value,
        participants: sceneType.value === "scene_four" ? [selectedScene4Ai.value] : selectedAIs.value,
        ai_roles: sceneType.value === "scene_two" ? stances.value : {},
      }),
    });
    if (!res.ok) throw new Error(`创建失败：${res.status}`);
    const { session_id } = await res.json();
    sessionId.value = session_id;

    showProgress.value = true;
    isLoading.value = false;
    configCollapsed.value = true;

    const sse = new EventSource(
      `${apiBase}/api/roundtable/stream/${session_id}?token=${encodeURIComponent(token || "")}`
    );

    sse.onmessage = (e) => {
      const event = JSON.parse(e.data);
      handleSSEEvent(event, sse);
    };

    sse.onerror = () => {
      errorMsg.value = "SSE 连接中断，请刷新重试";
      sse.close();
    };
  } catch (e) {
    errorMsg.value = e.message;
    isLoading.value = false;
  }
};

const loadHistory = async () => {
  historyLoading.value = true;
  try {
    const token = localStorage.getItem("token");
    const apiBase =
      (import.meta.env && import.meta.env.VITE_API_BASE) || "";
    const res = await fetch(`${apiBase}/api/roundtable/history`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error(`${res.status}`);
    historyList.value = await res.json();
  } catch (e) {
    console.error("加载历史失败", e);
  } finally {
    historyLoading.value = false;
  }
};

const deleteRecord = async (recordId) => {
  if (!confirm("确认删除这条记录？")) return;
  const token = localStorage.getItem("token");
  const apiBase =
    (import.meta.env && import.meta.env.VITE_API_BASE) || "";
  const res = await fetch(`${apiBase}/api/roundtable/${recordId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    if (res.status === 404) errorMsg.value = "记录不存在";
    else errorMsg.value = `删除失败：${res.status}`;
    return;
  }
  await loadHistory();
};

const exportDoc = async (format) => {
  if (!sessionId.value) return;
  const token = localStorage.getItem("token");
  const apiBase =
    (import.meta.env && import.meta.env.VITE_API_BASE) || "";
  try {
    const res = await fetch(
      `${apiBase}/api/roundtable/${sessionId.value}/export/${format}`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    if (!res.ok) throw new Error(`导出失败：${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `圆桌_${topic.value}.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    errorMsg.value = e.message;
  }
};

const toggleConfig = () => {
  configCollapsed.value = !configCollapsed.value;
};

onMounted(loadHistory);
</script>

<template>
  <ToolsHeader title="AI圆桌会议" />
  <div class="box">
    <!-- 配置区：可折叠 -->
    <a-card title="配置" :style="{ marginBottom: '16px' }">
      <template #extra>
        <a @click="toggleConfig" style="cursor: pointer">{{
          configCollapsed ? "展开" : "收起"
        }}</a>
      </template>
      <div v-show="!configCollapsed">
        <div style="display: flex; gap: 12px; margin-bottom: 16px">
          <div
            v-for="scene in sceneOptions"
            :key="scene.value"
            @click="sceneType = scene.value"
            :style="{
              flex: 1,
              padding: '12px 16px',
              border: sceneType === scene.value ? '2px solid #1677ff' : '1px solid #d9d9d9',
              borderRadius: '8px',
              cursor: 'pointer',
              background: sceneType === scene.value ? '#e6f4ff' : '#fff',
            }"
          >
            <div style="font-weight: 600">{{ scene.label }}</div>
            <div style="font-size: 12px; color: #888; margin-top: 4px">{{ scene.desc }}</div>
          </div>
        </div>
        <p class="scene-hint">{{ sceneDesc }}</p>
        <a-divider :style="{ margin: '12px 0' }" />

        <div class="field">
          <span class="label">题目：</span>
          <a-textarea
            v-model:value="topic"
            :placeholder="topicPlaceholder"
            :rows="(sceneType === 'scene_three' || sceneType === 'scene_four') ? 6 : 2"
            :maxlength="(sceneType === 'scene_three' || sceneType === 'scene_four') ? undefined : 100"
            :show-count="sceneType !== 'scene_three' && sceneType !== 'scene_four'"
            :style="{ maxWidth: '600px' }"
          />
        </div>

        <div v-if="sceneType === 'scene_four'" class="field ai-section">
          <span class="label">选择模型：</span>
          <a-radio-group v-model:value="selectedScene4Ai" class="ai-rows">
            <div v-for="ai in SCENE4_AI_LIST" :key="ai.key" class="ai-row">
              <a-radio :value="ai.key">
                <span class="ai-label">{{ ai.label }}</span>
                <span v-if="ai.desc" class="ai-desc">（{{ ai.desc }}）</span>
              </a-radio>
            </div>
          </a-radio-group>
        </div>
        <div v-else class="field ai-section">
          <span class="label">参与 AI：</span>
          <a-checkbox-group v-model:value="selectedAIs" class="ai-rows">
            <div
              v-for="ai in AI_LIST"
              :key="ai.key"
              class="ai-row"
            >
              <div class="ai-check">
                <a-checkbox :value="ai.key" />
                <span class="ai-label">{{ ai.label }}</span>
                <span class="ai-desc">{{ ai.desc }}</span>
              </div>
              <a-input
                v-if="sceneType === 'scene_two' && selectedAIs.includes(ai.key)"
                v-model:value="stances[ai.key]"
                placeholder="请输入该AI的神学立场"
                class="stance-input"
              />
            </div>
          </a-checkbox-group>
        </div>

        <p v-if="sceneType !== 'scene_four'" class="count-hint" :class="{ invalid: selectedAIs.length < 2 }">
          已选 {{ selectedAIs.length }} 个 AI（最少2个，最多6个）
        </p>

        <a-button
          type="primary"
          :disabled="!canStart"
          :loading="isLoading"
          @click="handleStart"
        >
          开始
        </a-button>
      </div>
    </a-card>

    <!-- 进行区：默认隐藏，开始后显示 -->
    <a-card
      v-show="showProgress"
      title="圆桌进行中"
      :style="{ marginBottom: '16px' }"
    >
      <a-alert
        v-if="errorMsg"
        type="error"
        :message="errorMsg"
        show-icon
        style="margin-bottom: 16px"
      />

      <template v-for="round in (runSceneType === 'scene_one' || runSceneType === 'scene_four') ? [1] : [1, 2, 3]" :key="round">
        <div class="round-divider">
          <span class="line"></span>
          <span class="round-label">{{
            runSceneType === "scene_one"
              ? "第 1 步 · 各AI独立研究"
              : runSceneType === "scene_three"
                ? (round === 1 ? "第 1 轮 · 作答" : round === 2 ? "第 2 轮 · 互相指出" : "第 3 轮 · 最终评价")
                : runSceneType === "scene_four"
                  ? "顶级模型思考"
                  : `第 ${round} 轮`
          }}</span>
          <span class="line"></span>
        </div>
        <div
          v-for="s in speeches.filter((sp) => sp.round === round).sort((a, b) => (runSceneType === 'scene_four' ? SCENE4_ORDER : AI_ORDER).indexOf(a.ai) - (runSceneType === 'scene_four' ? SCENE4_ORDER : AI_ORDER).indexOf(b.ai))"
          :key="`${s.round}-${s.ai}`"
          style="
            display: flex;
            gap: 12px;
            margin-bottom: 20px;
            align-items: flex-start;
          "
        >
          <img
            :src="getAvatar(s.ai)"
            style="
              width: 36px;
              height: 36px;
              border-radius: 50%;
              object-fit: contain;
              flex-shrink: 0;
              background: #f5f5f5;
            "
          />
          <div style="flex: 1">
            <div class="speaker-name" style="margin-bottom: 4px">
              {{ getSpeakerName(s.ai) }}
              <span
                v-if="s.typing"
                style="color: #999; font-size: 12px; font-weight: 400"
              > 发言中...</span>
              <span
                v-else-if="!s.done && !s.typing"
                style="color: #999; font-size: 12px; font-weight: 400"
              > 等待中...</span>
            </div>
            <div style="white-space: pre-wrap; line-height: 1.7">
              {{ s.displayContent }}
            </div>
          </div>
        </div>
      </template>

    </a-card>

    <!-- 结论区：默认隐藏，结束后显示；场景④ 无结论文案，仅显示完成与费用 -->
    <a-card
      v-if="showConclusionOrScene4Done"
      :title="runSceneType === 'scene_four' ? '完成' : '圆桌结论'"
      :style="{ marginBottom: '16px' }"
    >
      <template #extra>
        <a-space v-if="roundDone">
          <a-button size="small" @click="exportDoc('docx')"
            >下载 DOCX</a-button
          >
          <a-button size="small" @click="exportDoc('pdf')"
            >下载 PDF</a-button
          >
        </a-space>
      </template>
      <div v-if="runSceneType !== 'scene_four'" style="white-space: pre-wrap">{{ conclusion }}</div>
      <div
        v-if="roundDone"
        style="margin-top:12px; padding:10px 16px; background:#f6ffed; border:1px solid #b7eb8f; border-radius:8px; text-align:right; font-size:13px"
      >
        本次圆桌总费用：<strong>${{ (totalCost ?? 0).toFixed(4) }} USD</strong>
      </div>
    </a-card>

    <!-- 历史记录区 -->
    <a-card title="历史记录" style="margin-top: 16px">
      <a-spin :spinning="historyLoading">
        <div v-if="historyList.length === 0" style="color: #999">
          暂无历史记录
        </div>
        <div
          v-for="item in historyList"
          :key="item.record_id"
          style="
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 0;
            border-bottom: 1px solid #f0f0f0;
            cursor: pointer;
          "
          @click="$router.push('/roundtable/' + item.record_id)"
        >
          <div>
            <span style="font-weight: 500">{{ item.topic }}</span>
            <span
              style="color: #999; font-size: 12px; margin-left: 8px"
            >
              {{ item.scene_type === "scene_two" ? "神学辩论" : item.scene_type === "scene_three" ? "重大讨论" : item.scene_type === "scene_four" ? "顶级模型思考" : "十二支派" }}
            </span>
            <span
              v-if="item.is_pinned"
              style="color: #faad14; margin-left: 4px"
            >📌</span>
          </div>
          <div style="display: flex; align-items: center; gap: 8px">
            <span style="color: #999; font-size: 0.85rem">
              {{ item.total_cost != null ? '$' + Number(item.total_cost).toFixed(4) : '—' }}
            </span>
            <span style="color: #999; font-size: 12px">
              {{ item.created_at?.slice(0, 16)?.replace('T', ' ') }}
            </span>
            <a-button
              size="small"
              danger
              @click.stop="deleteRecord(item.record_id)"
            >
              删除
            </a-button>
          </div>
        </div>
      </a-spin>
    </a-card>
  </div>
</template>

<style scoped>
.box {
  padding: 1em;
  max-width: 1200px;
  margin: 0 auto;
}
.placeholder {
  color: #888;
  margin: 0;
}
.scene-hint {
  color: #555;
  margin: 0;
  font-weight: 500;
}
.field {
  margin-bottom: 16px;
}
.field .label {
  display: block;
  font-weight: 600;
  margin-bottom: 8px;
}
.ai-section .ai-rows {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.ai-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
.ai-check {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 200px;
}
.ai-label {
  font-weight: 500;
}
.ai-desc {
  font-size: 12px;
  color: #888;
}
.stance-input {
  flex: 1;
  min-width: 200px;
}
.count-hint {
  margin: 12px 0 16px;
  color: #555;
}
.count-hint.invalid {
  color: #ff4d4f;
}

/* 轮次分隔线：左右横线夹住文字 */
.round-divider {
  display: flex;
  align-items: center;
  margin: 2rem 0;
}
.round-divider .line {
  flex: 1;
  border-top: 2px solid #666;
}
.round-divider .round-label {
  padding: 0 1rem;
  font-size: 1.5rem;
  font-weight: bold;
  color: #333;
  white-space: nowrap;
}

/* 发言者名字：头像右侧 */
.speaker-name {
  font-size: 1.2rem;
  font-weight: bold;
}
</style>
