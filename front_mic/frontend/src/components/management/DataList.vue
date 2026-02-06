<script setup>
import axios from "axios";
import { ref, onMounted, reactive } from "vue";
import { SearchOutlined, ReloadOutlined } from "@ant-design/icons-vue";
import { tip } from "../utils";

const showSpin = ref(false);
const openM = ref(false);
const moTitle = ref("");
const filenamev = ref("");
const actionv = ref("");
const isLoading = ref(false);

const columns = ref([
  {
    title: "数据库",
    dataIndex: "indexname",
    sorter: (a, b) => a.indexname.toLowerCase().localeCompare(b.indexname.toLowerCase()),
    defaultSortOrder: "ascend",
    customFilterDropdown: true,
    onFilter: (value, record) => record.indexname.toString().toLowerCase().includes(value.toLowerCase()),
    onFilterDropdownOpenChange: (visible) => {
      if (visible) {
        setTimeout(() => {
          searchInput.value.focus();
        }, 100);
      }
    },
  },
  { title: "清空数据", dataIndex: "del", width: "240px", align: "center" },
]);

const datarow = ref([]);

const make_action = () => {
  let filename = filenamev.value;
  let action = actionv.value;
  if (action == "del") {
    showSpin.value = true;
  } else if (action == "ins") {
    isLoading.value = true;
  }
  let formData = new FormData();
  formData.append("index", filename);
  formData.append("opt", action);
  axios.post("api/datalist", formData).then((res) => {
    let data = res.data;
    if (data.msg == "datalist") {
      datarow.value = data.datalist;
    }
    if (data.tip) {
      tip(data.tip);
      isLoading.value = false;
    }
    showSpin.value = false;
  });
};

const state = reactive({
  searchText: "",
  searchedColumn: "",
});

const searchInput = ref();

const dealData = (filename, action) => {
  filenamev.value = filename;
  actionv.value = action;
  if (["del"].includes(action)) {
  } else {
    make_action();
  }
};

const okHandeler = () => {
  make_action();
};

const handleSearch = (selectedKeys, confirm, dataIndex) => {
  confirm();
  state.searchText = selectedKeys[0];
  state.searchedColumn = dataIndex;
};

const handleReset = (clearFilters) => {
  clearFilters({ confirm: true });
  state.searchText = "";
};

onMounted(() => {
  dealData("filename", "getlist");
});
</script>

<template>
  <div>
    <h1 class="center">数据库管理（请谨慎操作）</h1>
  </div>
  <div>
    <a-spin :spinning="showSpin" size="large" tip="请稍候……">
      <a-table :columns="columns" :data-source="datarow" bordered :pagination="false" :scroll="{ y: 580 }">
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
          <template v-if="column.dataIndex === 'del'">
            <a-popconfirm title="确认清空数据？" @confirm="okHandeler">
              <a-button @click="dealData(record.indexname, 'del')" type="primary" danger ghost>清空数据</a-button>
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
