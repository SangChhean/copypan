<template>
  <div class="placeholder-root">
    <a-button type="link" @click="$router.push('/')">← 返回首页</a-button>
    <h2>{{ title }}</h2>
    <a-tag v-if="building" color="orange">建设中</a-tag>
    <p v-else>页面占位，Phase 2.3 接通业务组件。</p>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, default: '占位页' },
  building: { type: Boolean, default: false },
})
</script>

<style scoped>
.placeholder-root {
  padding: 24px;
}
</style>
