<script setup>
defineProps({
  title: { type: String, required: true },
});
</script>

<template>
  <header class="page-header">
    <h1>{{ title }}</h1>
    <p class="sub">testA 独立练习环境 · 不用于生产</p>
  </header>
</template>

<style scoped>
.page-header {
  background: #001529;
  color: #fff;
  padding: 16px 20px;
  text-align: center;
}
.page-header h1 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
}
.sub {
  margin: 6px 0 0;
  font-size: 0.85rem;
  color: rgba(255, 255, 255, 0.65);
}
</style>
