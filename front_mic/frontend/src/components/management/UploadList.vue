<script lang="ts" setup>
import axios from "axios";
import { ref, onMounted, reactive } from "vue";
import { SearchOutlined, ReloadOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import { showMsg } from "../utils";

const showSpin = ref(false);
const openM = ref(false);
const openP = ref(false);
const moTitle = ref("");
const filenamev = ref("");
const actionv = ref("");
const importingFilename = ref("");
const progressVal = ref(0);

const state = reactive({
  searchText: "",
  searchedColumn: "",
});

const searchInput = ref();

const columns = ref([
  {
    title: "文件名",
    dataIndex: "filename",
    customFilterDropdown: true,
    onFilter: (value, record) => record.filename.toString().toLowerCase().includes(value.toLowerCase()),
    onFilterDropdownOpenChange: (visible) => {
      if (visible) {
        setTimeout(() => {
          searchInput.value.focus();
        }, 100);
      }
    },
  },
  { title: "导入数据库", dataIndex: "ins", width: "120px", align: "center" },
  { title: "删除", dataIndex: "del", width: "120px", align: "center" },
]);

const handleSearch = (selectedKeys, confirm, dataIndex) => {
  confirm();
  state.searchText = selectedKeys[0];
  state.searchedColumn = dataIndex;
};

const handleReset = (clearFilters) => {
  clearFilters({ confirm: true });
  state.searchText = "";
};

const datarow = ref([]);

let ws: WebSocket | null = null;

function closeWebSocket() {
  if (ws) {
    try {
      ws.close();
    } catch {
      /* ignore */
    }
    ws = null;
  }
}

function finishImport() {
  importingFilename.value = "";
  showSpin.value = false;
  openP.value = false;
  closeWebSocket();
}

function connectWebSocket() {
  return new Promise<WebSocket>((resolve, reject) => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const isLocal =
      ["localhost", "127.0.0.1"].includes(window.location.hostname) &&
      window.location.port !== "443";
    const wsHost = isLocal ? "localhost:8000" : window.location.host;
    const socket = new WebSocket(`${protocol}//${wsHost}/api/ws/progress`);
    ws = socket;

    socket.onopen = () => {
      resolve(socket);
    };

    socket.onerror = (error) => {
      console.error("WebSocket connection failed.", error);
      reject(new Error("WebSocket 连接失败，无法获取导入进度，请检查 Nginx /api/ws/ 配置"));
    };

    socket.onmessage = function (event) {
      const progressData = JSON.parse(event.data);
      progressVal.value = progressData.progress;
    };

    socket.onclose = function () {
      console.log("WebSocket closed.");
    };
  });
}

function getProcessErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data;
    if (data && typeof data === "object" && "error" in data && data.error) {
      return String(data.error);
    }
    const status = error.response?.status;
    if (status === 403) return "导入失败：无权限（HTTP 403）";
    if (status === 502) return "导入失败：网关错误（HTTP 502），请检查后端是否运行";
    if (status === 504) return "导入失败：网关超时（HTTP 504），请检查 Nginx proxy_read_timeout";
    if (status) return `导入失败：HTTP ${status}`;
    return error.message || "导入失败";
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "导入失败";
}

const startProcess = async (formData: FormData) => {
  importingFilename.value = filenamev.value;
  progressVal.value = 0;
  try {
    await connectWebSocket();
    openP.value = true;
    const apost = axios.create({
      timeout: 1000 * 60 * 10,
    });
    const res = await apost.post("/api/process", formData);
    if (res.data?.error) {
      message.error(String(res.data.error));
    } else if (res.data?.tip) {
      showMsg(res.data.tip);
    } else {
      message.error("导入失败：服务器未返回结果");
    }
  } catch (error) {
    message.error(getProcessErrorMessage(error));
  } finally {
    finishImport();
  }
};

const make_action = async () => {
  let filename = filenamev.value;
  let action = actionv.value;
  let formData = new FormData();
  formData.append("filename", filename);
  formData.append("action", action);

  if (action == "ins") {
    startProcess(formData);
  } else {
    showSpin.value = true;
    axios.post("/api/upopt", formData).then((res) => {
      let data = res.data;
      if (data.msg == "datalist") {
        datarow.value = data.datalist;
      }
      if (data.tip) {
        showMsg(data.tip);
      }
      if (data.error) {
        message.error(String(data.error));
      }
      showSpin.value = false;
    }).catch((error) => {
      message.error(getProcessErrorMessage(error));
      showSpin.value = false;
    });
  }
};

const dealData = (filename, action) => {
  filenamev.value = filename;
  actionv.value = action;
  if (["del", "ins"].includes(action)) {
  } else {
    make_action();
  }
};

const okHandeler = () => {
  make_action();
};

onMounted(() => {
  dealData("filename", "getlist");
});
</script>

<template>
  <div>
    <h1 class="center">已上传文件管理</h1>
  </div>
  <div>
    <a-spin :spinning="showSpin" size="large" tip="请稍候……">
      <a-table :columns="columns" :data-source="datarow" bordered>
        <template #customFilterDropdown="{ setSelectedKeys, selectedKeys, confirm, clearFilters, column }">
          <div style="padding: 8px">
            <a-input ref="searchInput" :placeholder="`搜索文件`" :value="selectedKeys[0]" style="width: 188px; margin-bottom: 8px; display: block" @change="(e) => setSelectedKeys(e.target.value ? [e.target.value] : [])" @pressEnter="handleSearch(selectedKeys, confirm, column.dataIndex)" />
            <a-button type="primary" size="small" style="width: 90px; margin-right: 8px" @click="handleSearch(selectedKeys, confirm, column.dataIndex)">
              <template #icon><SearchOutlined /></template>
              搜索
            </a-button>
            <a-button size="small" style="width: 90px" @click="handleReset(clearFilters)">
              <template #icon><ReloadOutlined /></template>
              重置
            </a-button>
          </div>
        </template>
        <template #customFilterIcon="{ filtered }">
          <search-outlined :style="{ color: filtered ? '#108ee9' : undefined }" />
        </template>
        <template #bodyCell="{ text, column, record }">
          <template v-if="column.dataIndex === 'ins'">
            <a-popconfirm title="确认导入？" :disabled="!!importingFilename" @confirm="okHandeler">
              <a-button
                @click="dealData(record.filename, 'ins')"
                type="primary"
                ghost
                :disabled="!!importingFilename"
                :loading="importingFilename === record.filename"
              >
                导入
              </a-button>
            </a-popconfirm>
          </template>
          <template v-if="column.dataIndex === 'del'">
            <a-popconfirm title="确认删除？" :disabled="!!importingFilename" @confirm="okHandeler">
              <a-button @click="dealData(record.filename, 'del')" type="primary" danger ghost :disabled="!!importingFilename">删除</a-button>
            </a-popconfirm>
          </template>
          <span v-if="state.searchText && state.searchedColumn === column.dataIndex">
            <template v-for="(fragment, i) in text.toString().split(new RegExp(`(?<=${state.searchText})|(?=${state.searchText})`, 'i'))">
              <mark v-if="fragment.toLowerCase() === state.searchText.toLowerCase()" :key="i" class="highlight">
                {{ fragment }}
              </mark>
              <template v-else>{{ fragment }}</template>
            </template>
          </span>
        </template>
      </a-table>
    </a-spin>
  </div>
  <a-modal v-model:open="openM" :title="moTitle" @ok="okHandeler()"></a-modal>
  <a-modal v-model:open="openP" title="导入数据库进度" :footer="null" :maskClosable="false">
    <div style="text-align: center">
      <a-progress type="circle" :percent="progressVal" />
    </div>
  </a-modal>
</template>

<style scoped>
.center {
  text-align: center;
}

.spin {
  display: flex;
  justify-content: center;
  margin-top: 120px;
}
</style>
