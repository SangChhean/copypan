<script setup>
import axios from "axios";
import { ref, computed, onMounted, watch } from "vue";
import { ReloadOutlined } from "@ant-design/icons-vue";

const showSpin = ref(false);
const days = ref(7);
const stats = ref(null);
const errMsg = ref("");

const fetchStats = () => {
  showSpin.value = true;
  errMsg.value = "";
  axios
    .get("/api/ai_search/stats/detail", { params: { days: days.value } })
    .then((res) => {
      if (res.data.status === "success") {
        stats.value = res.data.data?.toolbox?.rough_outline || {};
      } else {
        errMsg.value = res.data.message || "获取失败";
      }
    })
    .catch((e) => {
      errMsg.value = e.message || "请求失败";
    })
    .finally(() => {
      showSpin.value = false;
    });
};

const AI_NAMES = {
  claude: "Claude",
  gemini: "Gemini",
  deepseek: "DeepSeek",
  openai: "GPT",
  perplexity: "Perplexity",
  grok: "Grok",
};

const tableColumns = [
  { title: "AI名称", dataIndex: "name", width: 120 },
  { title: "调用次数", dataIndex: "count", width: 100, align: "right" },
  { title: "费用($)", dataIndex: "cost", width: 120, align: "right", customRender: ({ text }) => "$" + Number(text || 0).toFixed(4) },
];

const tableRows = computed(() => {
  const ro = stats.value || {};
  const rows = Object.entries(AI_NAMES).map(([key, name]) => ({
    key,
    name,
    count: ro[key]?.count || 0,
    cost: ro[key]?.cost || 0,
  }));
  const totalCount = rows.reduce((s, r) => s + r.count, 0);
  const totalCost = rows.reduce((s, r) => s + r.cost, 0);
  rows.push({ key: "total", name: "总计", count: totalCount, cost: totalCost });
  return rows;
});

const totalCount = computed(() => tableRows.value.find((r) => r.key === "total")?.count || 0);
const totalCost = computed(() => tableRows.value.find((r) => r.key === "total")?.cost || 0);

watch(days, () => fetchStats());
onMounted(() => fetchStats());
</script>

<template>
  <div>
    <h1 class="center">毛胚纲目</h1>
  </div>
  <div class="stats-toolbar">
    <a-space>
      <span>统计天数：</span>
      <a-select v-model:value="days" style="width: 90px" :options="[7, 14, 30].map((d) => ({ label: d + ' 天', value: d }))" />
      <a-button type="primary" :loading="showSpin" @click="fetchStats">
        <template #icon><ReloadOutlined /></template>
        刷新
      </a-button>
    </a-space>
  </div>
  <div v-if="errMsg" class="err-msg">
    <a-alert type="error" :message="errMsg" show-icon />
  </div>
  <a-spin :spinning="showSpin" size="large" tip="请稍候……">
    <template v-if="stats">
      <div class="stats-cards">
        <a-card size="small" class="stat-card">
          <a-statistic title="总调用次数" :value="totalCount" />
        </a-card>
        <a-card size="small" class="stat-card">
          <a-statistic title="总费用" :value="totalCost" prefix="$" :precision="4" />
        </a-card>
      </div>
      <div class="section">
        <h3>各AI明细</h3>
        <a-table
          :columns="tableColumns"
          :data-source="tableRows"
          :pagination="false"
          bordered
          size="small"
          row-key="key"
        />
      </div>
    </template>
  </a-spin>
</template>

<style scoped>
.center { text-align: center; }
.stats-toolbar { margin-bottom: 16px; }
.stats-cards { display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 24px; }
.stat-card { min-width: 160px; }
.section { margin-bottom: 24px; }
.section h3 { margin-bottom: 12px; font-size: 14px; }
.err-msg { margin-bottom: 16px; }
</style>
