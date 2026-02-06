<script setup>
import zhCN from "ant-design-vue/es/locale/zh_CN";
import { ConfigProvider } from "ant-design-vue";
</script>
<template>
  <ConfigProvider :locale="zhCN">
    <router-view></router-view>
  </ConfigProvider>
  <a-back-top type="primary" />
</template>
<style scoped></style>
