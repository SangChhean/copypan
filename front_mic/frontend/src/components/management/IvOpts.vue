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

const columns = ref([
  {
    title: "邀请码",
    dataIndex: "filename",
  },
  { title: "角色", dataIndex: "role", width: "120px", align: "center" },
  { title: "删除", dataIndex: "del", width: "120px", align: "center" },
]);

const roles = {
  t0: "管理员",
  t1: "编辑",
  t2: "读者",
};

const datarow = ref([]);

const copyText = (val: stirng) => {
  if (!val) return;
  navigator.clipboard.writeText(val);
  tip("复制成功");
};

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
  formData.append("iv", filename);
  formData.append("action", action);
  formData.append("role", rolea);

  axios.post("api/iv_opts", formData).then((res) => {
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
    <h1 class="center">邀请码管理</h1>
  </div>
  <div>
    <a-button type="primary" @click="dealData('iv', 'gen', 'no')">添加新的邀请码</a-button>
  </div>
  <a-divider :style="{ margin: '5px 0' }"></a-divider>
  <div>
    <a-spin :spinning="showSpin" size="large" tip="请稍候……">
      <a-table :columns="columns" :data-source="datarow" bordered>
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'filename'">
            <a-button type="link" @click="copyText(record.filename)">{{ record.filename }}</a-button>
          </template>
          <template v-if="column.dataIndex === 'role'">
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
