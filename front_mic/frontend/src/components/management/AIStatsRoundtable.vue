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
    .get("api/ai_search/stats/detail", { params: { days: days.value } })
    .then((res) => {
      if (res.data.status === "success") {
        stats.value = res.data.data?.roundtable || {};
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

const SCENE_NAMES = {
  scene_one: "十二支派",
  scene_two: "神学辩论",
};

const sceneColumns = [
  { title: "场景名称", dataIndex: "name", width: 120 },
  { title: "调用次数", dataIndex: "count", width: 100, align: "right" },
  { title: "费用($)", dataIndex: "cost", width: 120, align: "right", customRender: ({ text }) => "$" + Number(text || 0).toFixed(4) },
];

const sceneRows = computed(() => {
  const sc = stats.value?.scene_counts || {};
  const s1 = sc.scene_one || { count: 0, cost: 0 };
  const s2 = sc.scene_two || { count: 0, cost: 0 };
  const totalCount = s1.count + s2.count;
  const totalCost = s1.cost + s2.cost;
  return [
    { key: "scene_one", name: SCENE_NAMES.scene_one, count: s1.count, cost: s1.cost },
    { key: "scene_two", name: SCENE_NAMES.scene_two, count: s2.count, cost: s2.cost },
    { key: "total", name: "总计", count: totalCount, cost: totalCost },
  ];
});

const dailyColumns = [
  { title: "日期", dataIndex: "date", width: 120 },
  { title: "次数", dataIndex: "count", width: 100, align: "right" },
  { title: "费用($)", dataIndex: "cost", width: 120, align: "right", customRender: ({ text }) => "$" + Number(text || 0).toFixed(4) },
];

watch(days, () => fetchStats());
onMounted(() => fetchStats());
</script>

<template>
  <div>
    <h1 class="center">AI 圆桌</h1>
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
          <a-statistic title="总调用次数" :value="stats.total_count || 0" />
        </a-card>
        <a-card size="small" class="stat-card">
          <a-statistic title="总费用" :value="stats.total_cost || 0" prefix="$" :precision="4" />
        </a-card>
      </div>
      <div class="section">
        <h3>场景分布</h3>
        <a-table
          :columns="sceneColumns"
          :data-source="sceneRows"
          :pagination="false"
          bordered
          size="small"
          row-key="key"
        />
      </div>
      <div class="section">
        <h3>每日统计</h3>
        <a-table
          :columns="dailyColumns"
          :data-source="stats.daily || []"
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
.stat-card { min-width: 160px; }
.section { margin-bottom: 24px; }
.section h3 { margin-bottom: 12px; font-size: 14px; }
.err-msg { margin-bottom: 16px; }
</style>
