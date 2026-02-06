<script setup>
import { onMounted, ref, watch } from "vue";
import { IconSunFill, IconMoonFill, IconUser, IconPenFill, IconImport, IconCommand } from "@arco-design/web-vue/es/icon";
import useStore from "../../store";
import axios from "axios";

const MyStore = useStore();

const themeModle = ref();
const themeIconSun = ref(false);
const bodyBgC = "background-color: #fff";

const themeModleChange = () => {
  themeModle.value == "d" ? (themeModle.value = "l") : (themeModle.value = "d");
};

watch(themeModle, val => {
  localStorage.themeModle = val;
  if (val == "d") {
    document.body.setAttribute("arco-theme", "dark");
    document.body.setAttribute("style", "background-color: #151515");
    document.querySelector("header").setAttribute("style", "background-color: #232324");
    themeIconSun.value = true;
  } else {
    document.body.removeAttribute("arco-theme");
    document.body.setAttribute("style", bodyBgC);
    document.querySelector("header").setAttribute("style", "background-color: #fff");
    themeIconSun.value = false;
  }
});

const jump = url => {
  window.location.hash = url;
};

const menuClick = index => {
  if (index == "8") jump("map");
  else if (index == "9") jump("tools");
  else MyStore.index = index;
};

onMounted(() => {
  if (localStorage.hasOwnProperty("themeModle")) {
    themeModle.value = localStorage.themeModle;
  } else {
    localStorage.themeModle = "l";
    themeModle.value = "l";
  }
});

const editPass = () => {
  window.location.hash = "changepass";
};

const show_back = ref(false);
const enterBackend = () => {
  axios.get("/api/ght_admin").then(res => {
    let status = res.data;
    if (status == "t0" || status == "t1") window.location.hash = "back_ad";
    else if (status == "login") window.location.hash = "login";
    else window.location.hash = "";
  });
};

const logout = () => {
  axios.get("/api/logout").then(res => {
    if (res.data.status == "ok") {
      window.location.hash = "login";
    }
  });
};

onMounted(() => {
  axios.get("/api/ght_admin").then(res => {
    let status = res.data;
    if (["t0", "t1"].includes(status)) show_back.value = true;
    else show_back.value = false;
  });
});
</script>

<template>
  <a-row justify="space-between">
    <a-col :xs="16" :sm="20">
      <a-menu mode="horizontal" :default-selected-keys="['0']" @menu-item-click="menuClick">
        <a-menu-item key="0" :style="{ padding: 0, marginRight: '1em' }">
          <div class="logo">Pansearch</div>
        </a-menu-item>
        <a-menu-item key="1">圣经</a-menu-item>
        <a-menu-item key="2">生命读经</a-menu-item>
        <a-menu-item key="4">倪文集</a-menu-item>
        <a-menu-item key="3">李文集</a-menu-item>
        <a-menu-item key="7">其他</a-menu-item>
        <a-menu-item key="10">诗歌</a-menu-item>
        <a-menu-item key="5">节期</a-menu-item>
        <a-menu-item key="9" style="background-color: var(--color-neutral-4)" @click="jump('tools')" disabled>工具</a-menu-item>
      </a-menu>
    </a-col>
    <a-col :xs="8" :sm="4">
      <div class="header_left">
        <a-space style="margin: 1em">
          <a-dropdown trigger="hover">
            <a-button shape="circle"><icon-user size="22" /></a-button>
            <template #content>
              <a-doption @click="editPass">
                <icon-pen-fill />
                修改密码
              </a-doption>
              <a-doption @click="enterBackend" v-if="show_back">
                <icon-command />
                管理系统
              </a-doption>
              <a-doption @click="logout">
                <icon-import />
                退出登录
              </a-doption>
            </template>
          </a-dropdown>
          <a-button @click="themeModleChange" shape="circle" v-if="themeIconSun"><icon-sun-fill size="22" /></a-button>
          <a-button @click="themeModleChange" shape="circle" v-else><icon-moon-fill size="22" /></a-button>
        </a-space>
      </div>
    </a-col>
  </a-row>
</template>

<style scoped>
.logo {
  font-family: "pans";
  font-size: xx-large;
  color: #3f9dfd;
}
</style>
