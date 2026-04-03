<script setup>
import axios from "axios";
import { ref, computed, onMounted, watch } from "vue";
import { ReloadOutlined, DeleteOutlined, ClearOutlined, ExportOutlined } from "@ant-design/icons-vue";
import { Modal } from "ant-design-vue";
import { tip } from "../utils";

const showSpin = ref(false);
const days = ref(7);
const stats = ref(null);
const legacyStats = ref(null);
const errMsg = ref("");

const NATURE_ORDER = ["一般性", "高真理浓度", "高生命浓度", "重实行应用"];

const fetchStats = () => {
  showSpin.value = true;
  errMsg.value = "";
  Promise.all([
    axios.get("/api/ai_search/stats/detail", { params: { days: days.value } }),
    axios.get("/api/ai_search/stats", { params: { days: days.value } }),
  ])
    .then(([detailRes, legacyRes]) => {
      if (detailRes.data.status === "success") {
        stats.value = detailRes.data.data?.rag || {};
      } else {
        errMsg.value = detailRes.data.message || "获取失败";
      }
      if (legacyRes.data.status === "success") {
        legacyStats.value = legacyRes.data.data || {};
      }
    })
    .catch((e) => {
      errMsg.value = e.message || "请求失败";
    })
    .finally(() => {
      showSpin.value = false;
    });
};

const natureRows = computed(() => {
  const nc = stats.value?.nature_counts || {};
  const total = stats.value?.total_queries || 0;
  return NATURE_ORDER.map((name) => ({
    key: name,
    name,
    count: nc[name] || 0,
    pct: total ? ((nc[name] || 0) / total * 100).toFixed(1) : "0.0",
  }));
});

const modeRows = computed(() => {
  const mc = stats.value?.mode_counts || {};
  const total = stats.value?.total_queries || 0;
  return ["新版方式一", "新版方式二", "旧版"].map((name) => ({
    key: name,
    name,
    count: mc[name] || 0,
    pct: total ? ((mc[name] || 0) / total * 100).toFixed(1) : "0.0",
  }));
});

const depthRows = computed(() => {
  const dc = stats.value?.depth_counts || {};
  const total = stats.value?.total_queries || 0;
  return [
    { key: "general", name: "普通", count: dc.general || 0, pct: total ? ((dc.general || 0) / total * 100).toFixed(1) : "0.0" },
    { key: "deep", name: "深度", count: dc.deep || 0, pct: total ? ((dc.deep || 0) / total * 100).toFixed(1) : "0.0" },
  ];
});

const dailyColumns = [
  { title: "日期", dataIndex: "date", width: 120 },
  { title: "查询数", dataIndex: "queries", width: 100, align: "right" },
  { title: "费用($)", dataIndex: "cost", width: 100, align: "right", customRender: ({ text }) => "$" + Number(text || 0).toFixed(4) },
];

const retrievalLogColumns = [
  { title: "时间", dataIndex: "ts", width: 165, ellipsis: true },
  { title: "问题", dataIndex: "question", ellipsis: true },
  { title: "总检索", dataIndex: "total", width: 90, align: "right" },
  { title: "使用", dataIndex: "used", width: 80, align: "right" },
  { title: "浪费率", dataIndex: "waste_rate", width: 90, align: "right", customRender: ({ text }) => text != null ? text + "%" : "-" },
  { title: "模式", dataIndex: "mode", width: 100, ellipsis: true },
  { title: "深度", dataIndex: "depth", width: 80, align: "center", customRender: ({ text }) => text === "deep" ? "深度" : (text === "general" ? "普通" : (text || "-")) },
  { title: "负担说明", dataIndex: "burden", width: 90, align: "center", customRender: ({ text }) => text === "是" ? "是" : (text === "否" ? "否" : (text || "-")) },
];

const retrievalLog = computed(() => legacyStats.value?.retrieval_log || []);

const natureWeightColumns = computed(() => {
  const w = legacyStats.value?.index_weights;
  if (!w || !w._labels) return [];
  const cols = [{ title: "纲目性质", dataIndex: "nature", key: "nature", width: 100 }];
  for (const [key, label] of Object.entries(w._labels)) {
    cols.push({ title: label, dataIndex: key, key, width: 88, align: "center" });
  }
  cols.push({ title: "说明", dataIndex: "note", key: "note", width: 200 });
  return cols;
});

const natureWeightRows = computed(() => {
  const w = legacyStats.value?.index_weights;
  if (!w || !w._labels) return [];
  return NATURE_ORDER.map((nature) => {
    const config = w[nature];
    const row = { nature, key: nature };
    if (config) {
      for (const key of Object.keys(w._labels)) {
        row[key] = config[key] ?? "-";
      }
    }
    row.note = (w._notes && w._notes[nature]) || "-";
    return row;
  });
});

const clearingCache = ref(false);
const onClearCache = () => {
  clearingCache.value = true;
  axios
    .post("/api/ai_search/cache/clear")
    .then((res) => {
      if (res.data.status === "success") {
        const data = res.data.data || {};
        tip(data.message || `已清理 ${data.cleared ?? 0} 条缓存`);
        fetchStats();
      } else {
        tip("清理失败：" + (res.data.message || ""));
      }
    })
    .catch((e) => {
      tip("清理失败：" + (e.message || ""));
    })
    .finally(() => {
      clearingCache.value = false;
    });
};

const onReset = () => {
  showSpin.value = true;
  axios
    .post("/api/ai_search/stats/reset")
    .then((res) => {
      if (res.data.status === "success") {
        tip("统计已重置");
        fetchStats();
      } else {
        tip("重置失败：" + (res.data.message || ""));
      }
    })
    .catch((e) => {
      tip("重置失败：" + (e.message || ""));
    })
    .finally(() => {
      showSpin.value = false;
    });
};

const onResetClick = () => {
  Modal.confirm({
    title: "确认重置",
    content: "确定要重置所有统计数据吗？此操作不可恢复。",
    okText: "确定",
    cancelText: "取消",
    okType: "danger",
    onOk() {
      Modal.confirm({
        title: "再次确认",
        content: "再次确认：所有历史统计、费用记录将被永久清空，无法还原，确定继续吗？",
        okText: "确定继续",
        cancelText: "取消",
        okType: "danger",
        onOk() {
          onReset();
        },
      });
    },
  });
};

const errorLimit = ref(20);
const errors = ref([]);
const fetchErrors = () => {
  axios
    .get("/api/ai_search/stats/errors", { params: { limit: errorLimit.value } })
    .then((res) => {
      if (res.data.status === "success") {
        errors.value = res.data.data || [];
      }
    })
    .catch(() => {});
};

const showMoreErrors = () => {
  errorLimit.value = 50;
  fetchErrors();
};

watch(days, () => {
  fetchStats();
  fetchErrors();
});
onMounted(() => {
  fetchStats();
  fetchErrors();
});
</script>

<template>
  <div>
    <h1 class="center">AI 纲目制作</h1>
  </div>
  <div class="stats-toolbar">
    <a-space>
      <span>统计天数：</span>
      <a-select v-model:value="days" style="width: 90px" :options="[7, 14, 30].map((d) => ({ label: d + ' 天', value: d }))" />
      <a-button type="primary" :loading="showSpin" @click="fetchStats">
        <template #icon><ReloadOutlined /></template>
        刷新
      </a-button>
      <a-popconfirm
        title="确定要清理 AI 搜索缓存吗？"
        ok-text="确定清理"
        cancel-text="取消"
        @confirm="onClearCache"
      >
        <template #description>
          <span>清理后，相同问题将重新调用 Claude 生成答案，可能产生费用。</span>
        </template>
        <a-button :loading="clearingCache">
          <template #icon><ClearOutlined /></template>
          清理缓存
        </a-button>
      </a-popconfirm>
      <a-button danger :loading="showSpin" @click="onResetClick">
        <template #icon><DeleteOutlined /></template>
        重置统计
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
          <a-statistic title="调用次数" :value="stats.total_queries || 0" />
        </a-card>
        <a-card size="small" class="stat-card">
          <a-statistic title="总费用" :value="stats.total_cost || 0" prefix="$" :precision="4" />
        </a-card>
        <a-card size="small" class="stat-card">
          <a-statistic title="缓存命中率" :value="stats.cache_hit_rate || 0" suffix="%" :precision="2" />
        </a-card>
        <a-card size="small" class="stat-card">
          <a-statistic title="平均响应时间" :value="stats.avg_response_time_ms || 0" suffix="ms" :precision="2" />
        </a-card>
      </div>
      <div class="section">
        <h3>纲目性质分布</h3>
        <a-card size="small" class="dist-card">
          <div class="dist-list">
            <div v-for="row in natureRows" :key="row.key" class="dist-row">
              <span class="dist-name">{{ row.name }}</span>
              <span class="dist-count">{{ row.count }} 次</span>
              <span class="dist-pct">{{ row.pct }}%</span>
            </div>
          </div>
        </a-card>
      </div>
      <div class="section">
        <h3>使用模式分布</h3>
        <a-card size="small" class="dist-card">
          <div class="dist-list">
            <div v-for="row in modeRows" :key="row.key" class="dist-row">
              <span class="dist-name">{{ row.name }}</span>
              <span class="dist-count">{{ row.count }} 次</span>
              <span class="dist-pct">{{ row.pct }}%</span>
            </div>
          </div>
        </a-card>
      </div>
      <div class="section">
        <h3>深度模式分布</h3>
        <a-card size="small" class="dist-card">
          <div class="dist-list">
            <div v-for="row in depthRows" :key="row.key" class="dist-row">
              <span class="dist-name">{{ row.name }}</span>
              <span class="dist-count">{{ row.count }} 次</span>
              <span class="dist-pct">{{ row.pct }}%</span>
            </div>
          </div>
        </a-card>
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
      <div class="section">
        <h3>检索统计日志</h3>
        <a-table
          :columns="retrievalLogColumns"
          :data-source="retrievalLog"
          :pagination="{ pageSize: 20 }"
          bordered
          size="small"
          :row-key="(r, i) => `${r.ts}-${i}`"
        />
      </div>
      <div class="section">
        <h3>错误记录</h3>
        <div class="section-toolbar">
          <a-space>
            <a-button v-if="errorLimit === 20" @click="showMoreErrors">
              <template #icon><ExportOutlined /></template>
              显示更多（50 条）
            </a-button>
            <span v-else class="limit-tip">已显示最近 {{ errorLimit }} 条</span>
          </a-space>
        </div>
        <a-table
          :columns="[
            { title: '时间', dataIndex: 'ts', width: 180, ellipsis: true },
            { title: '错误信息', dataIndex: 'message', ellipsis: true },
            { title: '问题', dataIndex: 'question', width: 180, ellipsis: true },
          ]"
          :data-source="errors"
          :pagination="false"
          bordered
          size="small"
          :row-key="(record, index) => record.ts + '-' + index"
          :scroll="{ x: 600 }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.dataIndex === 'message'">
              <a-tooltip :title="record.message">
                <span>{{ record.message }}</span>
              </a-tooltip>
            </template>
            <template v-if="column.dataIndex === 'question'">
              <span>{{ record.question || '-' }}</span>
            </template>
          </template>
        </a-table>
        <div v-if="errors.length === 0" class="empty-tip">
          <a-empty description="暂无错误记录" />
        </div>
      </div>
      <div class="section" v-if="legacyStats?.index_weights && legacyStats.index_weights._labels">
        <h3>AI 检索权重</h3>
        <a-table
          :columns="natureWeightColumns"
          :data-source="natureWeightRows"
          :pagination="false"
          bordered
          size="small"
          row-key="nature"
          class="weights-table"
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
.section-toolbar { margin-bottom: 12px; }
.dist-card { max-width: 360px; }
.dist-list { display: flex; flex-direction: column; gap: 8px; }
.dist-row { display: flex; align-items: center; gap: 12px; }
.dist-name { flex: 0 0 100px; font-weight: 500; }
.dist-count { flex: 0 0 70px; text-align: right; color: #666; }
.dist-pct { flex: 0 0 56px; text-align: right; color: #1677ff; font-weight: 500; }
.weights-table { max-width: 100%; }
.err-msg { margin-bottom: 16px; }
.empty-tip { margin-top: 16px; }
.limit-tip { color: #666; font-size: 12px; }
</style>
