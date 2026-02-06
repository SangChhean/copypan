<script lang="ts" setup>
import axios from "axios";
import { ref, onMounted, reactive } from "vue";
import { SearchOutlined, ReloadOutlined, DownOutlined } from "@ant-design/icons-vue";
import { tip } from "../utils";

const showSpin = ref(false);
const openM = ref(false);
const moTitle = ref("");
const filenamev = ref("");
const actionv = ref("");
const isLoading = ref(false);
const rolev = ref("");

const state = reactive({
  searchText: "",
  searchedColumn: "",
});

const searchInput = ref();

const columns = ref([
  {
    title: "用户名",
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
  { title: "角色", dataIndex: "role", width: "120px", align: "center" },
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

const roles = {
  t0: "管理员",
  t1: "编辑",
  t2: "读者",
};

const datarow = ref([]);

const make_action = () => {
  let filename = filenamev.value;
  let action = actionv.value;
  let rolea = rolev.value;

  if (action == "getlist" || action == "role") {
    showSpin.value = true;
  } else if (action == "ins") {
    isLoading.value = true;
  }

  let formData = new FormData();
  formData.append("username", filename);
  formData.append("action", action);
  formData.append("role", rolea);

  axios.post("api/usr_opts", formData).then((res) => {
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

const dealData = (filename, action, role = "nobody") => {
  filenamev.value = filename;
  actionv.value = action;
  rolev.value = role;
  if (action !== "del") {
    make_action();
  }
};

const okHandeler = () => {
  make_action();
};

const changeRole = (role, usename) => {
  dealData(usename, "cgrole", role);
};

onMounted(() => {
  dealData("filename", "getlist");
});
</script>

<template>
  <div>
    <h1 class="center">用户管理</h1>
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
          <template v-if="column.dataIndex === 'role'">
            <!-- <a-button @click="dealData(record.filename, 'role')" type="primary" ghost>修改</a-button> -->
            <a-dropdown :trigger="['click']">
              <template #overlay>
                <a-menu>
                  <a-menu-item key="t0" @click="changeRole('t0', record.filename)">管理员</a-menu-item>
                  <a-menu-item key="t1" @click="changeRole('t1', record.filename)">编辑</a-menu-item>
                  <a-menu-item key="t2" @click="changeRole('t2', record.filename)">读者</a-menu-item>
                </a-menu>
              </template>
              <a-button>
                {{ roles[record.role] }}
                <DownOutlined />
              </a-button>
            </a-dropdown>
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
