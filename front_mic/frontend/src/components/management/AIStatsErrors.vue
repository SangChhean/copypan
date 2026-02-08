<script setup>
import axios from "axios";
import { ref, onMounted } from "vue";
import { ReloadOutlined, ExportOutlined } from "@ant-design/icons-vue";
import { tip } from "../utils";

const showSpin = ref(false);
const limit = ref(20);
const errors = ref([]);
const errMsg = ref("");

const fetchErrors = () => {
  showSpin.value = true;
  errMsg.value = "";
  axios
    .get("api/ai_search/stats/errors", { params: { limit: limit.value } })
    .then((res) => {
      if (res.data.status === "success") {
        errors.value = res.data.data || [];
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

const showMore = () => {
  limit.value = 50;
  fetchErrors();
};

onMounted(() => fetchErrors());
</script>

<template>
  <div>
    <h1 class="center">AI 错误记录</h1>
  </div>
  <div class="errors-toolbar">
    <a-space>
      <a-button type="primary" :loading="showSpin" @click="fetchErrors">
        <template #icon><ReloadOutlined /></template>
        刷新
      </a-button>
      <a-button v-if="limit === 20" @click="showMore" :loading="showSpin">
        <template #icon><ExportOutlined /></template>
        显示更多（50 条）
      </a-button>
      <span v-else class="limit-tip">已显示最近 {{ limit }} 条</span>
    </a-space>
  </div>
  <div v-if="errMsg" class="err-msg">
    <a-alert type="error" :message="errMsg" show-icon />
  </div>
  <a-spin :spinning="showSpin" size="large" tip="请稍候……">
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
    <div v-if="!showSpin && errors.length === 0 && !errMsg" class="empty-tip">
      <a-empty description="暂无错误记录" />
    </div>
  </a-spin>
</template>

<style scoped>
.center {
  text-align: center;
}
.errors-toolbar {
  margin-bottom: 16px;
}
.limit-tip {
  color: #666;
  font-size: 12px;
}
.err-msg {
  margin-bottom: 16px;
}
.empty-tip {
  margin-top: 24px;
}
</style>
