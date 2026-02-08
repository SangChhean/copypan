<script setup>
import { ref, onBeforeMount, watch } from "vue";
import { h } from "vue";
import { UserOutlined, EditOutlined, ToolOutlined, LogoutOutlined, AppstoreFilled } from "@ant-design/icons-vue";
import { storeToRefs } from "pinia";
import { useStore } from "../store/index";

const { selectedIndex, role, username } = storeToRefs(useStore());
const showMobile = ref(false);

const items = [
  { key: "1", label: "圣经" },
  { key: "2", label: "生命读经" },
  { key: "3", label: "倪文集" },
  { key: "4", label: "李文集" },
  { key: "5", label: "其他" },
  { key: "6", label: "诗歌" },
  { key: "7", label: "节期" },
];

const items_mo = [
  { key: "1", label: "圣经" },
  { key: "2", label: "生命读经" },
  { key: "3", label: "倪文集" },
  { key: "4", label: "李文集" },
  { key: "5", label: "其他" },
  { key: "6", label: "诗歌" },
  { key: "7", label: "节期" },
  { key: "9", label: "工具箱" },
];

const isMobile = () => {
  let op1 = /Mobi|Android|iPhone/i.test(navigator.userAgent);
  let op2 = window.screen.width < 760;
  let op3 = window.matchMedia("only screen and (max-width: 760px)").matches;
  return op1 || op2 || op3;
};

const logout = () => {
  localStorage.removeItem("token");
  window.location.href = "/";
};

const open_hash = (ha) => {
  window.location.hash = ha;
};

onBeforeMount(() => {
  showMobile.value = isMobile();
});

watch(selectedIndex, () => {
  if (selectedIndex.value == "9") {
    open_hash("/tools");
  }
});
</script>

<template>
  <a-affix :offset-top="0" v-if="showMobile">
    <div id="header_mobile">
      <a-menu v-model:selectedKeys="selectedIndex" mode="horizontal" class="menu">
        <a-menu-item key="0"><span id="logo">Pansearch</span></a-menu-item>
        <a-menu-item v-for="item in items_mo" :key="item.key" v-text="item.label"></a-menu-item>
      </a-menu>
    </div>
  </a-affix>

  <div id="header" v-else>
    <a-menu v-model:selectedKeys="selectedIndex" mode="horizontal" class="menu">
      <a-menu-item key="0"><span id="logo">Pansearch</span></a-menu-item>
      <a-menu-item v-for="item in items" :key="item.key" v-text="item.label"></a-menu-item>
    </a-menu>
    <div id="tools">
      <a-space>
        <a-divider type="vertical" :style="{ height: '50px', marginRight: '15px' }"></a-divider>
        <!-- <a-button type="primary" @click="open_hash('/map')">思路</a-button> -->
        <a-button type="primary" @click="open_hash('/tools')" :icon="h(AppstoreFilled)">工具箱</a-button>
        <a-divider type="vertical" :style="{ height: '50px', marginLeft: '15px' }"></a-divider>
      </a-space>
    </div>

    <div id="login">
      <a-dropdown>
        <a-button shape="circle" type="primary" :icon="h(UserOutlined)" />
        <template #overlay>
          <a-menu>
            <a-menu-item>
              <UserOutlined /><span>&nbsp;{{ username }}</span>
            </a-menu-item>
            <a-divider style="margin: 4px 0"></a-divider>
            <a-menu-item>
              <EditOutlined />
              <a href="#changePass"> 修改密码</a>
            </a-menu-item>
            <a-menu-item v-if="role == 't0'">
              <ToolOutlined />
              <a href="#manage"> 后台管理</a>
            </a-menu-item>
            <a-menu-item>
              <LogoutOutlined />
              <span @click="logout"> 退出登录</span>
            </a-menu-item>
          </a-menu>
        </template>
      </a-dropdown>
      <span style="margin-left: 2em"></span>
    </div>
  </div>
</template>

<style scoped>
#header {
  box-shadow: 0 2px 8px 0 rgba(2, 24, 42, 0.1);
  display: flex;
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  z-index: 1000;
  background-color: #fff;
}
#header_mobile {
  box-shadow: 0 2px 8px 0 rgba(2, 24, 42, 0.1);
  width: 100%;
}

#tools {
  align-content: center;
}
#logo {
  font-family: pan;
  font-size: 2em;
  color: #1677ff;
}
#login {
  flex-grow: 1;
  align-content: center;
  text-align: right;
}
.ant-menu-horizontal {
  border-bottom: none;
}
</style>
