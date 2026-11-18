<script setup>
// 【4.0作纲目】使用统计：数据来自 4.0 测试台后端 /api/t35test/usage/stats（与 3.0 的统计完全分开）。
// 一篇 = 从负担说明、推荐重点到生成纲目带同一个「本篇编号」的所有请求；重做的次数都算在内。
import axios from "axios";
import { ref, computed, onMounted, watch } from "vue";
import { ReloadOutlined } from "@ant-design/icons-vue";

const showSpin = ref(false);
const days = ref(7);
const stats = ref(null);
const errMsg = ref("");

const NATURE_ORDER = ["综合性", "真理启示", "生命经历", "实行应用"];
const usd = (v, n = 4) => (v == null ? "-" : "$" + Number(v).toFixed(n));

const fetchStats = () => {
  showSpin.value = true;
  errMsg.value = "";
  axios
    .get("/api/t35test/usage/stats", { params: { days: days.value } })
    .then((res) => {
      stats.value = res.data || {};
    })
    .catch((e) => {
      errMsg.value = e.response?.data?.detail || e.message || "请求失败";
    })
    .finally(() => {
      showSpin.value = false;
    });
};

const summary = computed(() => stats.value?.summary || {});

const natureRows = computed(() => {
  const list = stats.value?.natures || [];
  const total = list.reduce((a, b) => a + b.count, 0);
  const map = Object.fromEntries(list.map((x) => [x.nature, x.count]));
  const names = [...NATURE_ORDER, ...list.map((x) => x.nature).filter((n) => !NATURE_ORDER.includes(n))];
  return names.map((name) => ({
    key: name,
    name,
    count: map[name] || 0,
    pct: total ? (((map[name] || 0) / total) * 100).toFixed(1) : "0.0",
  }));
});

const stepColumns = [
  { title: "步骤", dataIndex: "label", width: 140 },
  { title: "调用次数", dataIndex: "count", width: 100, align: "right" },
  { title: "费用($)", dataIndex: "cost_usd", width: 120, align: "right", customRender: ({ text }) => usd(text) },
];

const dailyColumns = [
  { title: "日期", dataIndex: "day", width: 120 },
  { title: "生成纲目篇数", dataIndex: "outlines", width: 120, align: "right" },
  { title: "开始做的篇数", dataIndex: "sessions", width: 120, align: "right" },
  { title: "费用($)", dataIndex: "cost_usd", width: 100, align: "right", customRender: ({ text }) => usd(text) },
];

const fmtTime = (ms) => {
  if (!ms) return "-";
  const d = new Date(ms);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
};

const kindText = (r, k) => {
  const x = r.kinds?.[k];
  if (!x || !x.count) return "-";
  return `${x.count} 次 ${usd(x.cost_usd, 3)}`;
};

const sessionColumns = [
  { title: "开始时间", dataIndex: "start_ts", width: 165, customRender: ({ text }) => fmtTime(text) },
  { title: "纲目主题", dataIndex: "query", ellipsis: true },
  { title: "账号", dataIndex: "username", width: 90, ellipsis: true },
  { title: "纲目性质", dataIndex: "outline_nature", width: 90 },
  { title: "思考程度", dataIndex: "effort_label", width: 80, align: "center", customRender: ({ text }) => text || "中" },
  { title: "负担说明", key: "burden", width: 120, align: "right", customRender: ({ record }) => kindText(record, "burden") },
  { title: "推荐重点", key: "concepts", width: 120, align: "right", customRender: ({ record }) => kindText(record, "concepts") },
  { title: "生成纲目", key: "outline", width: 120, align: "right", customRender: ({ record }) => kindText(record, "outline") },
  { title: "合计($)", dataIndex: "total_cost_usd", width: 100, align: "right", customRender: ({ text }) => usd(text, 3) },
  { title: "备注", key: "note", width: 150 },
];

watch(days, fetchStats);
onMounted(fetchStats);
</script>

<template>
  <div>
    <h1 class="center">4.0 作纲目</h1>
  </div>
  <div class="stats-toolbar">
    <a-space>
      <span>统计天数：</span>
      <a-select v-model:value="days" style="width: 90px" :options="[7, 14, 30, 90].map((d) => ({ label: d + ' 天', value: d }))" />
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
          <a-statistic title="生成纲目篇数" :value="summary.outlines || 0" />
        </a-card>
        <a-card size="small" class="stat-card">
          <a-statistic title="总费用" :value="summary.total_cost_usd || 0" prefix="$" :precision="4" />
        </a-card>
        <a-card size="small" class="stat-card">
          <a-statistic title="平均每篇完整费用" :value="summary.avg_cost_per_full_outline_usd ?? 0" prefix="$" :precision="4" />
        </a-card>
        <a-card size="small" class="stat-card">
          <a-statistic title="平均生成纲目耗时" :value="(summary.avg_outline_elapsed_ms || 0) / 1000" suffix="秒" :precision="1" />
        </a-card>
      </div>
      <div class="stats-hint">
        开始做的篇数 {{ summary.sessions || 0 }}（含只做了负担说明或推荐重点、还没生成纲目的）；
        从头做到尾的 {{ summary.full_outlines || 0 }} 篇用来算平均每篇费用；
        命中缓存 {{ summary.cached_outlines || 0 }} 篇（未花费）。按 Opus 5.5 标准价计算，重做的次数都算在内。
      </div>
      <div class="section">
        <h3>纲目性质分布（生成纲目的篇数）</h3>
        <a-card size="small" class="dist-card">
          <div class="dist-list">
            <div v-for="row in natureRows" :key="row.key" class="dist-row">
              <span class="dist-name">{{ row.name }}</span>
              <span class="dist-count">{{ row.count }} 篇</span>
              <span class="dist-pct">{{ row.pct }}%</span>
            </div>
          </div>
        </a-card>
      </div>
      <div class="section">
        <h3>各步骤费用</h3>
        <a-table class="narrow-table" :columns="stepColumns" :data-source="stats.steps || []" :pagination="false" bordered size="small" row-key="step" />
      </div>
      <div class="section">
        <h3>每日统计</h3>
        <a-table :columns="dailyColumns" :data-source="stats.daily || []" :pagination="false" bordered size="small" row-key="day" />
      </div>
      <div class="section">
        <h3>每篇明细</h3>
        <a-table
          :columns="sessionColumns"
          :data-source="stats.sessions || []"
          :pagination="{ pageSize: 20 }"
          bordered
          size="small"
          row-key="session_id"
          :scroll="{ x: 1180 }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'note'">
              <a-tag v-if="!record.generated" color="default">未生成纲目</a-tag>
              <a-tag v-if="record.loaded" color="blue">载入记录</a-tag>
              <a-tag v-if="record.last_outline_cached" color="green">缓存</a-tag>
            </template>
          </template>
        </a-table>
      </div>
    </template>
  </a-spin>
</template>

<style scoped>
.center { text-align: center; }
.stats-toolbar { margin-bottom: 16px; }
.stats-cards { display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 12px; }
.stat-card { min-width: 160px; }
.stats-hint { color: #888; font-size: 12px; margin-bottom: 24px; }
.section { margin-bottom: 24px; }
.section h3 { margin-bottom: 12px; font-size: 14px; }
.dist-card { max-width: 360px; }
.dist-list { display: flex; flex-direction: column; gap: 8px; }
.dist-row { display: flex; align-items: center; gap: 12px; }
.dist-name { flex: 0 0 100px; font-weight: 500; }
.dist-count { flex: 0 0 70px; text-align: right; color: #666; }
.dist-pct { flex: 0 0 56px; text-align: right; color: #1677ff; font-weight: 500; }
.narrow-table { max-width: 420px; }
.err-msg { margin-bottom: 16px; }
</style>
