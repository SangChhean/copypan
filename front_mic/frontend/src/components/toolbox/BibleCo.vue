<script setup>
import ToolsHeader from "./ToolsHeader.vue";
import { ref } from "vue";
import axios from "axios";

const input = ref("");
const showData = ref([]);

const search = () => {
  if (!input.value.trim()) {
    showData.value = [];
    return;
  }
  let formData = new FormData();
  formData.append("input", input.value);
  let token = localStorage.getItem("token") || null;
  if (!token) window.location.hash = "/login";
  axios.defaults.headers.common["Authorization"] = `Bearer ${token}`;
  axios.post("/api/getvers", formData).then((res) => {
    showData.value = res.data;
  });
};
</script>

<template>
  <ToolsHeader title="经文汇集" />
  <div class="box">
    <a-textarea v-model:value="input" placeholder="请输入内容" :rows="12" />
    <a-divider :style="{ margin: '5px 0' }"></a-divider>
    <a-space>
      <a-button type="primary" @click="input = ''" danger>清空</a-button>
      <a-button type="primary" @click="search">汇集</a-button>
    </a-space>
    <a-divider :style="{ margin: '5px 0' }"></a-divider>
    <div class="res">
      <div v-for="item in showData">
        <div v-text="item.text" class="outline" v-if="item.text.trim()"></div>
        <div v-for="ver in item.vers">
          <span class="ver_s">{{ ver.source }}　</span>
          <span class="ver_t">{{ ver.text }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.box {
  padding: 1em;
}

.outline {
  padding: 1em;
  margin: 1em 0;
  border-radius: 5px;
  background: #fff;
  font-weight: bold;
}

.ver_s {
  font-weight: bold;
  color: tomato;
}
</style>
