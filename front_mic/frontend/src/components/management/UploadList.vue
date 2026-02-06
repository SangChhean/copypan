<script lang="ts" setup>
import axios from "axios";
import { ref, onMounted, reactive } from "vue";
import { SearchOutlined, ReloadOutlined } from "@ant-design/icons-vue";
import { tip, showMsg } from "../utils";

const showSpin = ref(false);
const openM = ref(false);
const openP = ref(false);
const moTitle = ref("");
const filenamev = ref("");
const actionv = ref("");
const isLoading = ref(false);
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

let ws;

function connectWebSocket() {
  return new Promise((resolve, reject) => {
    ws = new WebSocket("wss://pansearch.org/ws/progress");

    // 当 WebSocket 连接成功时，触发 resolve
    ws.onopen = () => {
      console.log("WebSocket connection established.");
      resolve(ws); // 返回 WebSocket 对象
    };

    // 如果连接失败，触发 reject
    ws.onerror = (error) => {
      console.error("WebSocket connection failed.", error);
      reject(error);
    };

    ws.onmessage = function (event) {
      const progressData = JSON.parse(event.data);
      progressVal.value = progressData.progress;
    };

    ws.onclose = function () {
      console.log("WebSocket closed.");
    };

    // 可以在 socket 上添加更多事件处理器，例如 onmessage, onclose 等
  });
}

const startProcess = async (formData) => {
  try {
    const socket = await connectWebSocket();
    progressVal.value = 0;
    openP.value = true;
    const apost = axios.create({
      timeout: 1000 * 60 * 10,
    });
    await apost.post("/api/process", formData).then((res) => {
      if (res.data.tip) {
        showMsg(res.data.tip);
        isLoading.value = false;
      }
      ws.close();
      showSpin.value = false;
    });
  } catch (error) {
    console.error("Failed to connect WebSocket, cannot start the process.", error);
  }
};

const make_action = async () => {
  let filename = filenamev.value;
  let action = actionv.value;
  let formData = new FormData();
  formData.append("filename", filename);
  formData.append("action", action);

  if (action == "ins") {
    isLoading.value = false;
    showSpin.value = false;
    startProcess(formData);
  } else {
    showSpin.value = true;
    axios.post("api/upopt", formData).then((res) => {
      let data = res.data;
      if (data.msg == "datalist") {
        datarow.value = data.datalist;
      }
      if (data.tip) {
        showMsg(data.tip);
        isLoading.value = false;
      }
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
            <a-popconfirm title="确认导入？" @confirm="okHandeler">
              <a-button @click="dealData(record.filename, 'ins')" type="primary" ghost>导入</a-button>
            </a-popconfirm>
          </template>
          <template v-if="column.dataIndex === 'del'">
            <a-popconfirm title="确认删除？" @confirm="okHandeler">
              <a-button @click="dealData(record.filename, 'del')" type="primary" danger ghost>删除</a-button>
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
