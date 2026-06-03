<script setup>
defineProps({
  title: { type: String, required: true },
});

const goTools = () => {
  window.location.hash = "/tools";
};
</script>

<template>
  <header class="page-header">
    <button type="button" class="back-btn" aria-label="返回" @click="goTools">←</button>
    <div class="title-wrap">
      <h1>{{ title }}</h1>
      <p class="sub">test_B 练习 · 临时测试</p>
    </div>
  </header>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #001529;
  color: #fff;
  padding: 16px 20px;
}
.back-btn {
  width: 36px;
  height: 36px;
  font-size: 20px;
  line-height: 1;
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 6px;
  background: transparent;
  color: #fff;
  cursor: pointer;
  flex-shrink: 0;
}
.back-btn:hover {
  border-color: #55bbff;
  color: #55bbff;
}
.title-wrap {
  flex: 1;
  text-align: center;
  margin-right: 36px;
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