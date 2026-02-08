<script setup>
import axios from "axios";
import { ref, onMounted } from "vue";
import { ReloadOutlined } from "@ant-design/icons-vue";

const showSpin = ref(false);
const retrievalLog = ref([]);
const errMsg = ref("");

const fetchLog = () => {
  showSpin.value = true;
  errMsg.value = "";
  axios
    .get("api/ai_search/stats", { params: { days: 30 } })
    .then((res) => {
      if (res.data.status === "success") {
        retrievalLog.value = res.data.data?.retrieval_log || [];
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

onMounted(() => fetchLog());
</script>

<template>
  <div>
    <h1 class="center">检索统计日志</h1>
  </div>
  <div class="retrieval-toolbar">
    <a-button type="primary" :loading="showSpin" @click="fetchLog">
      <template #icon><ReloadOutlined /></template>
      刷新
    </a-button>
  </div>
  <div v-if="errMsg" class="err-msg">
    <a-alert type="error" :message="errMsg" show-icon />
  </div>
  <a-spin :spinning="showSpin" size="large" tip="请稍候……">
    <a-table
      :columns="[
        { title: '时间', dataIndex: 'ts', width: 165, ellipsis: true },
        { title: '问题', dataIndex: 'question', ellipsis: true },
        { title: '总检索', dataIndex: 'total', width: 90, align: 'right' },
        { title: '使用', dataIndex: 'used', width: 80, align: 'right' },
        { title: '浪费率', dataIndex: 'waste_rate', width: 90, align: 'right', customRender: ({ text }) => text != null ? text + '%' : '-' },
      ]"
      :data-source="retrievalLog"
      :pagination="{ pageSize: 20 }"
      bordered
      size="small"
      :row-key="(r, i) => `${r.ts}-${i}`"
    />
  </a-spin>
</template>

<style scoped>
.center {
  text-align: center;
}
.retrieval-toolbar {
  margin-bottom: 16px;
}
.err-msg {
  margin-bottom: 16px;
}
</style>
