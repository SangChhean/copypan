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
    </div>
  </header>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #001529;
  color: #55bbff;
  padding: 10px 20px;
  margin-bottom: 30px;
}
.back-btn {
  width: 36px;
  height: 36px;
  font-size: 20px;
  line-height: 1;
  border: 1px solid rgba(85, 187, 255, 0.4);
  border-radius: 6px;
  background: transparent;
  color: #55bbff;
  cursor: pointer;
  flex-shrink: 0;
}
.back-btn:hover {
  border-color: #1677ff;
  color: #1677ff;
}
.title-wrap {
  flex: 1;
  text-align: center;
  margin-right: 36px;
}
.page-header h1 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: bold;
  color: #55bbff;
}
</style>