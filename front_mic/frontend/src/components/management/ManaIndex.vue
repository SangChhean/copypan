<script lang="ts" setup>
import { h, ref } from "vue";
import { DatabaseOutlined, TeamOutlined, ArrowLeftOutlined, FileAddOutlined, UserOutlined, CodeOutlined, InboxOutlined, CloudUploadOutlined } from "@ant-design/icons-vue";
import { storeToRefs } from "pinia";
import { useStore } from "../../store/index";
import ShowMsg from "../tools/ShowMsg.vue";
import { message } from "ant-design-vue";
import type { UploadChangeParam } from "ant-design-vue";
import { checkSession } from "../utils";
import DataList from "./DataList.vue";
import UserOpts from "./UserOpts.vue";
checkSession("t0");

const fileList = ref([]);
const dragOver = ref(false);
const { showIndex } = storeToRefs(useStore());

const handleChange = (info: UploadChangeParam) => {
  const status = info.file.status;
  if (status !== "uploading") {
  }
  if (status === "done") {
    message.success(`${info.file.name} 上传成功`);
  } else if (status === "error") {
    message.error(`${info.file.name} 上传失败`);
  }
};

function handleDrop(e: DragEvent) {}

const key = ref("1");

const goBack = () => {
  window.location.hash = "/";
};

const selectedKeys = ref(["1"]);
const openKeys = ref(["sub1", "sub2", "sub3", "sub4", "sub5"]);

const items = ref([
  {
    key: "sub1",
    icon: () => h(DatabaseOutlined),
    label: "数据库管理",
    title: "database",
    children: [
      {
        icon: () => h(FileAddOutlined),
        key: "1",
        label: "上传文件",
        title: "upload",
      },
      {
        icon: () => h(DatabaseOutlined),
        key: "2",
        label: "已传文件",
        title: "uplist",
      },
      {
        icon: () => h(DatabaseOutlined),
        key: "3",
        label: "数据库",
        title: "datalist",
      },
    ],
  },
  {
    key: "sub2",
    icon: () => h(TeamOutlined),
    label: "用户管理",
    title: "users",
    children: [
      {
        icon: () => h(UserOutlined),
        key: "4",
        label: "用户",
        title: "user",
      },
      {
        icon: () => h(CodeOutlined),
        key: "5",
        label: "邀请码",
        title: "ivcode",
      },
    ],
  },
]);

const navClick = (item: any) => {
  key.value = item.key;
};
</script>

<template>
  <div v-if="showIndex">
    <div class="header-pg">
      <div @click="goBack" class="back"><ArrowLeftOutlined /></div>
      <div style="text-align: center; width: 100%">后台管理</div>
    </div>
    <a-row :wrap="false">
      <a-col flex="250px">
        <div>
          <a-menu v-model:openKeys="openKeys" v-model:selectedKeys="selectedKeys" style="width: 240px" mode="inline" :items="items" :forceSubMenuRender="true" @select="navClick" theme="dark" />
          <br />
        </div>
      </a-col>
      <a-col flex="auto" class="res">
        <div class="content">
          <div v-if="key === '1'" id="drag_area">
            <h1 class="center">文件上传</h1>
            <a-upload-dragger v-model:fileList="fileList" name="file" :multiple="true" action="api/upload" @change="handleChange" @drop="handleDrop">
              <p class="ant-upload-drag-icon">
                <CloudUploadOutlined v-if="dragOver" />
                <inbox-outlined v-else></inbox-outlined>
              </p>
              <p class="ant-upload-text">点击或拖拽文件到此区域上传</p>
              <p class="ant-upload-hint">支持多文件上传</p>
            </a-upload-dragger>
          </div>
          <div v-if="key === '2'">
            <UploadList />
          </div>
          <div v-if="key === '3'">
            <DataList />
          </div>
          <div v-if="key === '4'">
            <UserOpts />
          </div>
          <div v-if="key === '5'">
            <IvOpts />
          </div>
        </div>
      </a-col>
    </a-row>
    <div style="margin-bottom: 100px"></div>
    <ShowMsg />
  </div>
</template>

<style scoped>
.header-pg {
  padding: 10px 20px;
  display: flex;
  flex-direction: row;
  font-size: large;
  font-weight: bold;
  color: #55bbff;
  background-color: #001529;
}

.highlight {
  background-color: #1677ff;
}

.center {
  text-align: center;
}

.back {
  cursor: pointer;
}

.back:hover {
  color: #1677ff;
  transform: scale(1.8);
  transition: 0.2s;
}

.spin {
  text-align: center;
}

.search_bar {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
}

ul.ant-menu {
  /* margin-left: 10px;

  box-shadow: 0 2px 8px 0 rgba(2, 24, 42, 0.1); */
  height: 82vh;
  border-radius: 0 0 25px 0;
}

.content {
  padding: 30px 30px 30px 20px;
  min-width: none;
  max-width: 1000px;
  margin: auto;
}

.ant-table-column-sort {
  background-color: aqua;
}

.search_res {
  box-shadow: 0 2px 8px 0 rgba(2, 24, 42, 0.1);
  border-radius: 10px;
  margin-bottom: 20px;
  background-color: #fafafa;
}
</style>
