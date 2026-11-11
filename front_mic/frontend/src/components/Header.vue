<script setup>
import { ref, computed, onBeforeMount } from "vue";
import { h } from "vue";
import { useRouter, useRoute, isNavigationFailure } from "vue-router";
import { UserOutlined, EditOutlined, ToolOutlined, LogoutOutlined, AppstoreFilled } from "@ant-design/icons-vue";
import { storeToRefs } from "pinia";
import { useStore } from "../store/index";

const { selectedIndex, role, username } = storeToRefs(useStore());
const showMobile = ref(false);
const router = useRouter();
const route = useRoute();
const isPanai = computed(() => route.path === "/panai");

const items = [
  { key: "1", label: "圣经" },
  { key: "2", label: "生命读经" },
  { key: "3", label: "倪文集" },
  { key: "4", label: "李文集" },
  { key: "5", label: "其他" },
  { key: "6", label: "诗歌" },
  { key: "7", label: "节期纲目" },
];

const items_mo = [
  { key: "1", label: "圣经" },
  { key: "2", label: "生命读经" },
  { key: "3", label: "倪文集" },
  { key: "4", label: "李文集" },
  { key: "5", label: "其他" },
  { key: "6", label: "诗歌" },
  { key: "7", label: "节期纲目" },
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

// 统一用 router.push，好让 #/panai 的离开确认（onBeforeRouteLeave）能拦截
const open_hash = (ha) => {
  router.push(ha);
};

const goPanai = () => {
  if (isPanai.value) return;
  router.push("/panai");
};

// 菜单点击：原来 v-model 直接改 selectedIndex；现在先处理跳转，跳转成功后才切类别
const onMenuClick = ({ key }) => {
  if (key === "9") {
    // 手机版“工具箱”：只跳转，不改 selectedIndex
    router.push("/tools");
    return;
  }
  if (isPanai.value) {
    // 在纲目页点类别：先切类别再回首页（纲目页菜单不高亮，Search 的 watch 在纲目模式直接 return）；
    // 跳转被离开确认取消时恢复原类别
    const prev = [...selectedIndex.value];
    selectedIndex.value = [key];
    router.push("/").then((f) => {
      if (isNavigationFailure(f)) selectedIndex.value = prev;
    });
    return;
  }
  selectedIndex.value = [key];
};

onBeforeMount(() => {
  showMobile.value = isMobile();
});
</script>

<template>
  <a-affix :offset-top="0" v-if="showMobile">
    <div id="header_mobile">
      <div class="menu-scroll">
        <a-menu :selectedKeys="isPanai ? [] : selectedIndex" @click="onMenuClick" mode="horizontal" class="menu" :disabled-overflow="true">
          <a-menu-item key="0"><span id="logo">Pansearch-ai</span></a-menu-item>
          <a-menu-item v-for="item in items_mo" :key="item.key" v-text="item.label"></a-menu-item>
        </a-menu>
      </div>
      <button type="button" class="panai-btn panai-btn--mobile" :class="{ 'panai-btn--active': isPanai }" @click="goPanai">纲目制作</button>
    </div>
  </a-affix>

  <div id="header" v-else>
    <a-menu :selectedKeys="isPanai ? [] : selectedIndex" @click="onMenuClick" mode="horizontal" class="menu" :disabled-overflow="true">
      <a-menu-item key="0"><span id="logo">Pansearch-ai</span></a-menu-item>
      <a-menu-item v-for="item in items" :key="item.key" v-text="item.label"></a-menu-item>
    </a-menu>
    <div id="tools">
      <a-space>
        <a-divider type="vertical" :style="{ height: '50px', marginRight: '15px' }"></a-divider>
        <!-- <a-button type="primary" @click="open_hash('/map')">思路</a-button> -->
        <a-button type="primary" @click="open_hash('/tools')" :icon="h(AppstoreFilled)">工具箱</a-button>
        <a-button class="panai-btn" :class="{ 'panai-btn--active': isPanai }" @click="goPanai">纲目制作</a-button>
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
              <a href="#changePass" @click.prevent="open_hash('/changePass')"> 修改密码</a>
            </a-menu-item>
            <a-menu-item v-if="role == 't0'">
              <ToolOutlined />
              <a href="#manage" @click.prevent="open_hash('/manage')"> 后台管理</a>
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
  display: flex;
  align-items: center;
  background-color: #fff;
}
/* 手机版：菜单在这个容器里横向滚动，PanAI 按钮固定在滚动容器之外的右侧 */
#header_mobile .menu-scroll {
  flex: 1;
  min-width: 0;
}

/* PanAI 3.0 入口按钮：加 #header / #header_mobile 前缀，压过 a-button 默认的 hover/focus 颜色 */
#header .panai-btn,
#header .panai-btn:hover,
#header .panai-btn:focus,
#header .panai-btn:active,
#header_mobile .panai-btn {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  border: none;
}
#header .panai-btn:hover,
#header_mobile .panai-btn:hover {
  filter: brightness(1.08);
}
#header .panai-btn--active,
#header_mobile .panai-btn--active {
  outline: 2px solid #afa9ec;
  outline-offset: 2px;
}
#header_mobile .panai-btn--mobile {
  flex-shrink: 0;
  border-radius: 999px;
  font-size: 12px;
  padding: 4px 10px;
  margin: 0 8px;
  white-space: nowrap;
  cursor: pointer;
  line-height: 1.5;
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

/* 移动端：768px */
@media (max-width: 768px) {
  #header_mobile .menu-scroll {
    overflow-x: auto;
    overflow-y: hidden;
    -webkit-overflow-scrolling: touch;
  }
  #header_mobile .menu {
    flex-wrap: nowrap;
    min-width: min-content;
    padding: 0 8px;
  }
  #header_mobile .ant-menu-item {
    padding: 0 12px;
    white-space: nowrap;
  }
  #logo {
    font-size: 1.5em;
  }
}

/* 移动端：480px */
@media (max-width: 480px) {
  #header_mobile .ant-menu-item {
    padding: 0 10px;
    font-size: 14px;
  }
  #logo {
    font-size: 1.25em;
  }
}
</style>
