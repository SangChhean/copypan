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
        stats.value = res.data.data?.toolbox?.feast_outline?.claude || { count: 0, cost: 0 };
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

watch(days, () => fetchStats());
onMounted(() => fetchStats());
</script>

<template>
  <div>
    <h1 class="center">节期纲目</h1>
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
          <a-statistic title="调用次数" :value="stats.count || 0" />
        </a-card>
        <a-card size="small" class="stat-card">
          <a-statistic title="总费用" :value="stats.cost || 0" prefix="$" :precision="4" />
        </a-card>
      </div>
      <div class="section">
        <a-alert type="info" message="模型：claude-sonnet-4-6" show-icon />
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
.err-msg { margin-bottom: 16px; }
</style>
