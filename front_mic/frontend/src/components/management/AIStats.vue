<script setup>
import axios from "axios";
import { ref, computed, onMounted, watch } from "vue";
import { ReloadOutlined, DeleteOutlined, ClearOutlined } from "@ant-design/icons-vue";
import { tip } from "../utils";

const showSpin = ref(false);
const days = ref(30);
const stats = ref(null);
const errMsg = ref("");

const NATURE_ORDER = ["一般性", "高真理浓度", "高生命浓度", "重实行应用"];

const natureWeightColumns = computed(() => {
  const w = stats.value?.index_weights;
  if (!w || !w._labels) return [];
  const cols = [{ title: "纲目性质", dataIndex: "nature", key: "nature", width: 100 }];
  for (const [key, label] of Object.entries(w._labels)) {
    cols.push({ title: label, dataIndex: key, key, width: 88, align: "center" });
  }
  cols.push({ title: "说明", dataIndex: "note", key: "note", width: 200 });
  return cols;
});

const natureWeightRows = computed(() => {
  const w = stats.value?.index_weights;
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

const fetchStats = () => {
  showSpin.value = true;
  errMsg.value = "";
  axios
    .get("api/ai_search/stats", { params: { days: days.value } })
    .then((res) => {
      if (res.data.status === "success") {
        stats.value = res.data.data;
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

const onReset = () => {
  showSpin.value = true;
  axios
    .post("api/ai_search/stats/reset")
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

const clearingCache = ref(false);
const onClearCache = () => {
  clearingCache.value = true;
  axios
    .post("api/ai_search/cache/clear")
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

watch(days, () => fetchStats());
onMounted(() => fetchStats());
</script>

<template>
  <div>
    <h1 class="center">AI 使用统计</h1>
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
      <a-popconfirm
        title="确定要重置所有 AI 统计吗？"
        ok-text="确定重置"
        cancel-text="取消"
        ok-type="danger"
        @confirm="onReset"
      >
        <template #description>
          <span style="color: #ff4d4f;">此操作将清空总查询数、缓存命中、响应时间、费用、纲目性质统计及每日统计，且不可恢复。</span>
        </template>
        <a-button danger :loading="showSpin">
          <template #icon><DeleteOutlined /></template>
          重置统计
        </a-button>
      </a-popconfirm>
    </a-space>
  </div>
  <div v-if="errMsg" class="err-msg">
    <a-alert type="error" :message="errMsg" show-icon />
  </div>
  <a-spin :spinning="showSpin" size="large" tip="请稍候……">
    <template v-if="stats && !stats.error">
      <div class="stats-cards">
        <a-card size="small" class="stat-card">
          <a-statistic title="总查询数" :value="stats.total_queries" />
        </a-card>
        <a-card size="small" class="stat-card">
          <a-statistic title="缓存命中率" :value="stats.cache_hit_rate" suffix="%" :precision="2" />
        </a-card>
        <a-card size="small" class="stat-card">
          <a-statistic title="平均响应时间" :value="stats.avg_response_time_ms" suffix="ms" :precision="2" />
        </a-card>
        <a-card size="small" class="stat-card">
          <a-statistic title="总费用" :value="stats.total_cost" prefix="$" :precision="4" />
        </a-card>
      </div>
      <div class="nature-section">
        <h3>纲目性质</h3>
        <a-card size="small" class="nature-card">
          <div class="nature-list">
            <div
              v-for="name in ['一般性', '高真理浓度', '高生命浓度', '重实行应用']"
              :key="name"
              class="nature-row"
            >
              <span class="nature-name">{{ name }}</span>
              <span class="nature-count">{{ (stats.nature_counts && stats.nature_counts[name]) || 0 }} 次</span>
              <span class="nature-pct">
                {{ stats.total_queries ? (((stats.nature_counts && stats.nature_counts[name]) || 0) / stats.total_queries * 100).toFixed(1) : 0 }}%
              </span>
            </div>
          </div>
        </a-card>
        <h3 class="weights-title">AI 检索权重</h3>
        <a-table
          v-if="stats.index_weights && stats.index_weights._labels"
          :columns="natureWeightColumns"
          :data-source="natureWeightRows"
          :pagination="false"
          bordered
          size="small"
          row-key="nature"
          class="weights-table"
        />
      </div>
      <div class="daily-section">
        <h3>每日统计</h3>
        <a-table
          :columns="[
            { title: '日期', dataIndex: 'date', width: 120 },
            { title: '查询数', dataIndex: 'queries', width: 100, align: 'right' },
            { title: '缓存命中', dataIndex: 'cache_hits', width: 100, align: 'right' },
            { title: '平均耗时(ms)', dataIndex: 'avg_ms', width: 120, align: 'right' },
            { title: '费用($)', dataIndex: 'cost', width: 100, align: 'right' },
          ]"
          :data-source="stats.daily || []"
          :pagination="false"
          bordered
          size="small"
          row-key="date"
        />
      </div>
    </template>
    <div v-else-if="stats && stats.message" class="empty-tip">
      <a-alert type="info" :message="stats.message" show-icon />
    </div>
  </a-spin>
</template>

<style scoped>
.center {
  text-align: center;
}
.stats-toolbar {
  margin-bottom: 16px;
}
.stats-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 24px;
}
.stat-card {
  min-width: 160px;
}
.nature-section {
  margin-bottom: 24px;
}
.nature-section h3 {
  margin-bottom: 12px;
  font-size: 14px;
}
.nature-card {
  max-width: 360px;
}
.nature-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.nature-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.nature-name {
  flex: 0 0 100px;
  font-weight: 500;
}
.nature-count {
  flex: 0 0 70px;
  text-align: right;
  color: #666;
}
.nature-pct {
  flex: 0 0 56px;
  text-align: right;
  color: #1677ff;
  font-weight: 500;
}
.weights-title {
  margin-top: 16px;
  margin-bottom: 12px;
  font-size: 14px;
}
.weights-table {
  max-width: 100%;
}
.daily-section h3 {
  margin-bottom: 12px;
  font-size: 14px;
}
.err-msg,
.empty-tip {
  margin-bottom: 16px;
}
</style>
