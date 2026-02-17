<script setup>
import { ArrowLeftOutlined, SearchOutlined, ToolOutlined } from "@ant-design/icons-vue";

const go = (val = "/") => {
  window.location.hash = val;
};
</script>

<template>
  <div class="header-pg">
    <div @click="go()" class="back"><ArrowLeftOutlined /></div>
    <div style="text-align: center; width: 100%">工具箱</div>
  </div>

  <div class="contents">
    <div class="cards">
      <a-card>
        <template #title>
          <div class="card_title"><SearchOutlined /> 定制搜索</div>
        </template>
        <a-card-grid class="card c1" @click="go('/cws')"><span class="card_text">新约职事的词典搜索</span></a-card-grid>
      </a-card>
    </div>
    <br />
    <br />
    <div class="cards">
      <a-card>
        <template #title>
          <div class="card_title"><ToolOutlined /> 工具</div>
        </template>
        <a-card-grid class="card c2" @click="go('/bibco')"><span class="card_text">经文汇集</span></a-card-grid>
        <a-card-grid class="card c2" @click="go('/info-retrieval')"><span class="card_text">信息检索</span></a-card-grid>
      </a-card>
    </div>
  </div>
</template>

<style scoped>
.contents {
  padding: 1em;
}

.card_title {
  font-weight: bold;
  font-size: 1.3em;
  color: #555;
}
.card,
.card_text {
  cursor: pointer;
}

.card:hover {
  border-radius: 10px;
}

.cards {
  margin: auto;
  max-width: 1200px;
}
.card_text {
  font-weight: bold;
  font-size: large;
}
/* 覆盖 a-card-grid 默认 33.33% 宽度；:deep 使样式作用到子组件根节点 */
:deep(.c1) {
  width: 100% !important;
  max-width: 100% !important;
}
.c2 {
  width: 25%;
}
.card {
  text-align: center;
}
.center {
  text-align: center;
}
.header-pg {
  padding: 10px 20px;
  display: flex;
  flex-direction: row;
  font-size: large;
  font-weight: bold;
  color: #55bbff;
  background-color: #001529;
  margin-bottom: 100px;
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
