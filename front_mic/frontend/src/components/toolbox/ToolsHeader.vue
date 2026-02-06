<script setup>
import { ArrowLeftOutlined } from "@ant-design/icons-vue";
const go = (val = "/tools") => {
  window.location.hash = val;
};

defineProps({
  title: String,
});
</script>

<template>
  <div class="header-pg">
    <div @click="go()" class="back"><ArrowLeftOutlined /></div>
    <div style="text-align: center; width: 100%">{{ title }}</div>
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
  margin-bottom: 30px;
}
.back {
  cursor: pointer;
}

.back:hover {
  color: #1677ff;
  transform: scale(1.8);
  transition: 0.2s;
}
</style>
