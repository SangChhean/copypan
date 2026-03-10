<script setup>
import { ref, computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import ToolsHeader from "./ToolsHeader.vue";

/** 轮次内发言固定顺序，与 RoundTable.vue 一致 */
const AI_ORDER = ["claude", "gpt", "gemini", "grok", "deepseek", "perplexity"];

const route = useRoute();
const router = useRouter();
const record = ref(null);
const loading = ref(true);
const errorMsg = ref("");
const pinLoading = ref(false);

const isSceneTwo = computed(() => record.value?.scene_type === "scene_two");
const aiRoles = computed(() => record.value?.ai_roles || {});

const getSpeakerName = (ai) => {
  if (isSceneTwo.value && aiRoles.value[ai]) return aiRoles.value[ai];
  return ai;
};

/** 按 AI_ORDER 返回当轮发言列表 [ [ai, speech], ... ] */
const sortedRoundEntries = (roundData) => {
  if (!roundData || typeof roundData !== "object") return [];
  return AI_ORDER.filter((ai) => roundData[ai] != null).map((ai) => [ai, roundData[ai]]);
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

const downloadFile = async (format) => {
  const token = localStorage.getItem("token");
  const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";
  const url = `${apiBase}/api/roundtable/${record.value.record_id}/export/${format}`;
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    alert("下载失败");
    return;
  }
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${record.value.topic || "圆桌"}.${format}`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(a.href);
};

const loadRecord = async () => {
  loading.value = true;
  try {
    const token = localStorage.getItem("token");
    const apiBase =
      (import.meta.env && import.meta.env.VITE_API_BASE) || "";
    const res = await fetch(
      `${apiBase}/api/roundtable/${route.params.id}`,
      {
        headers: { Authorization: `Bearer ${token}` },
      }
    );
    if (res.status === 404) {
      errorMsg.value = "记录不存在";
      return;
    }
    if (!res.ok) throw new Error(`${res.status}`);
    record.value = await res.json();
  } catch (e) {
    errorMsg.value = e.message;
  } finally {
    loading.value = false;
  }
};

const togglePin = async () => {
  pinLoading.value = true;
  try {
    const token = localStorage.getItem("token");
    const apiBase =
      (import.meta.env && import.meta.env.VITE_API_BASE) || "";
    const res = await fetch(
      `${apiBase}/api/roundtable/${route.params.id}/pin`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      }
    );
    const data = await res.json();
    if (record.value) record.value.is_pinned = data.is_pinned;
  } finally {
    pinLoading.value = false;
  }
};

onMounted(loadRecord);
</script>

<template>
  <ToolsHeader title="圆桌详情" />
  <div class="box">
    <a-button type="link" style="margin-bottom: 12px" @click="router.push('/roundtable')">
      ← 返回圆桌会议
    </a-button>
    <a-spin :spinning="loading">
      <a-alert v-if="errorMsg" type="error" :message="errorMsg" />

      <template v-if="record">
        <a-card :title="record.topic" style="margin-bottom: 16px">
          <template #extra>
            <a-space>
              <a-button :loading="pinLoading" @click="togglePin">
                {{ record.is_pinned ? "取消置顶 📌" : "置顶" }}
              </a-button>
            </a-space>
          </template>
          <p style="color: #999">
            {{ record.scene_type === "scene_two" ? "神学辩论" : "十二支派" }}
            · {{ record.created_at?.slice(0, 16)?.replace('T', ' ') }}
          </p>
          <p style="color: #999; font-size: 0.85rem">
            本次圆桌费用：{{ record.total_cost != null ? '$' + Number(record.total_cost).toFixed(4) : '—' }}
          </p>
          <!-- 场景① -->
          <p v-if="!isSceneTwo">
            参与AI：{{ record.participants?.join("、") }}
          </p>
          <!-- 场景② -->
          <template v-else>
            <p>参与立场：</p>
            <p v-for="ai in record.participants" :key="ai">
              {{ aiRoles[ai] || ai }}（{{ ai }}）
            </p>
          </template>
        </a-card>

        <!-- 各轮发言 -->
        <template v-if="record.rounds">
          <div v-for="(roundData, idx) in record.rounds" :key="idx">
            <div class="round-divider">
              <span class="line"></span>
              <span class="round-label">第 {{ idx + 1 }} 轮</span>
              <span class="line"></span>
            </div>
            <div
              v-for="[ai, speech] in sortedRoundEntries(roundData)"
              :key="ai"
              style="margin-bottom: 16px"
            >
              <strong class="speaker-name">{{ getSpeakerName(ai) }}</strong>
              <div
                style="white-space: pre-wrap; margin-top: 4px"
              >
                {{ cleanMarkdown(speech?.content ?? speech) }}
              </div>
            </div>
          </div>
        </template>

        <!-- 结论 -->
        <a-card
          v-if="record.conclusion"
          title="圆桌结论"
          style="margin-top: 16px"
        >
          <div style="white-space: pre-wrap">{{ cleanMarkdown(record.conclusion) }}</div>
          <div
            v-if="record.conclusion"
            class="download-btns"
            style="margin-top: 16px; display: flex; gap: 12px"
          >
            <button @click="downloadFile('docx')">下载 DOCX</button>
            <button @click="downloadFile('pdf')">下载 PDF</button>
          </div>
        </a-card>
      </template>
    </a-spin>
  </div>
</template>

<style scoped>
.box {
  padding: 1em;
  max-width: 1200px;
  margin: 0 auto;
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

/* 发言者名字 */
.speaker-name {
  font-size: 1.2rem;
  font-weight: bold;
}
</style>
