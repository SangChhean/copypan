<script setup>
import axios from "axios";
import { ref, computed, onMounted, watch } from "vue";
import { ReloadOutlined } from "@ant-design/icons-vue";

const showSpin = ref(false);
const days = ref(7);
const data = ref(null);
const errMsg = ref("");

const fetchStats = () => {
  showSpin.value = true;
  errMsg.value = "";
  axios
    .get("/api/ai_search/stats/detail", { params: { days: days.value } })
    .then((res) => {
      if (res.data.status === "success") {
        data.value = res.data.data || {};
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

const summary = computed(() => data.value?.summary || {});
const rag = computed(() => data.value?.rag || {});
const toolbox = computed(() => data.value?.toolbox || {});

const feastCost = computed(() => toolbox.value?.feast_outline?.claude?.cost || 0);
const roughCost = computed(() => {
  const ro = toolbox.value?.rough_outline || {};
  return Object.values(ro).reduce((s, v) => s + (v?.cost || 0), 0);
});
const translationCost = computed(() => {
  const tr = toolbox.value?.translation || {};
  return (tr.zh2en?.cost || 0) + (tr.en2zh?.cost || 0);
});

const moduleColumns = [
  { title: "模块名称", dataIndex: "name", width: 140 },
  { title: "费用($)", dataIndex: "cost", width: 120, align: "right", customRender: ({ text }) => "$" + Number(text || 0).toFixed(4) },
  { title: "占比", dataIndex: "pct", width: 80, align: "right", customRender: ({ text }) => text + "%" },
];

const moduleRows = computed(() => {
  const s = summary.value;
  const total = s.total_cost || 0;
  const pct = (v) => (total ? ((v / total) * 100).toFixed(1) : "0.0");
  const ragCost = s.rag_cost || 0;
  const tbCost = s.toolbox_cost || 0;
  const rtCost = s.roundtable_cost || 0;
  return [
    { key: "rag", name: "AI纲目制作", cost: ragCost, pct: pct(ragCost) },
    { key: "feast", name: "节期纲目", cost: feastCost.value, pct: pct(feastCost.value) },
    { key: "rough", name: "毛胚纲目", cost: roughCost.value, pct: pct(roughCost.value) },
    { key: "translation", name: "纲目翻译", cost: translationCost.value, pct: pct(translationCost.value) },
    { key: "roundtable", name: "AI圆桌", cost: rtCost, pct: pct(rtCost) },
    { key: "total", name: "合计", cost: total, pct: "100.0" },
  ];
});

const dailyColumns = [
  { title: "日期", dataIndex: "date", width: 120 },
  { title: "费用($)", dataIndex: "cost", width: 120, align: "right", customRender: ({ text }) => "$" + Number(text || 0).toFixed(4) },
];

watch(days, () => fetchStats());
onMounted(() => fetchStats());
</script>

<template>
  <div>
    <h1 class="center">费用总览</h1>
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
    <template v-if="data">
      <div class="stats-cards">
        <a-card size="small" class="stat-card">
          <a-statistic title="AI纲目制作" :value="summary.rag_cost || 0" prefix="$" :precision="4" />
        </a-card>
        <a-card size="small" class="stat-card">
          <a-statistic title="节期纲目" :value="feastCost" prefix="$" :precision="4" />
        </a-card>
        <a-card size="small" class="stat-card">
          <a-statistic title="毛胚纲目" :value="roughCost" prefix="$" :precision="4" />
        </a-card>
        <a-card size="small" class="stat-card">
          <a-statistic title="纲目翻译" :value="translationCost" prefix="$" :precision="4" />
        </a-card>
        <a-card size="small" class="stat-card">
          <a-statistic title="AI圆桌" :value="summary.roundtable_cost || 0" prefix="$" :precision="4" />
        </a-card>
        <a-card size="small" class="stat-card highlight-card">
          <a-statistic title="合计" :value="summary.total_cost || 0" prefix="$" :precision="4" />
        </a-card>
      </div>
      <div class="section">
        <h3>各模块费用对比</h3>
        <a-table
          :columns="moduleColumns"
          :data-source="moduleRows"
          :pagination="false"
          bordered
          size="small"
          row-key="key"
        />
      </div>
      <div class="section">
        <h3>每日费用</h3>
        <a-table
          :columns="dailyColumns"
          :data-source="summary.daily || []"
          :pagination="false"
          bordered
          size="small"
          row-key="date"
        />
      </div>
    </template>
  </a-spin>
</template>

<style scoped>
.center { text-align: center; }
.stats-toolbar { margin-bottom: 16px; }
.stats-cards { display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 24px; }
.stat-card { min-width: 140px; }
.highlight-card { background: #e6f7ff; border-color: #1890ff; }
.section { margin-bottom: 24px; }
.section h3 { margin-bottom: 12px; font-size: 14px; }
.err-msg { margin-bottom: 16px; }
</style>
