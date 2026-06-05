<script setup>
import { ref } from "vue";
import ArticlePolishB from "./ArticlePolishB.vue";
import GravePolishB from "./GravePolishB.vue";
import ChurchPolishB from "./ChurchPolishB.vue";

const activeTab = ref("polish");
</script>

<template>
  <div class="tab-bar">
    <button
      type="button"
      class="tab-btn"
      :class="{ active: activeTab === 'polish' }"
      @click="activeTab = 'polish'"
    >
      通用润色
    </button>
    <button
      type="button"
      class="tab-btn"
      :class="{ active: activeTab === 'grave' }"
      @click="activeTab = 'grave'"
    >
      润色恩典陵园
    </button>
    <button
      type="button"
      class="tab-btn"
      :class="{ active: activeTab === 'church' }"
      @click="activeTab = 'church'"
    >
      召会通讯及见证类
    </button>
  </div>

  <div v-show="activeTab === 'polish'">
    <ArticlePolishB />
  </div>
  <div v-show="activeTab === 'grave'">
    <GravePolishB />
  </div>
  <div v-show="activeTab === 'church'">
    <ChurchPolishB />
  </div>
</template>

<style scoped>
.tab-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: center;
  padding: 16px 1em 0;
  max-width: 900px;
  margin: 0 auto;
}

.tab-btn {
  padding: 8px 20px;
  font-size: 15px;
  font-weight: 500;
  color: #555;
  background: #fafafa;
  border: 2px solid #d9d9d9;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}

.tab-btn:hover {
  border-color: #1890ff;
  color: #1890ff;
}

.tab-btn.active {
  background: #1890ff;
  border-color: #1890ff;
  color: #fff;
}
</style>
