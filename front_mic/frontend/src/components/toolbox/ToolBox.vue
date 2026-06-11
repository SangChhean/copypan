<script setup>
import { ArrowLeftOutlined, SearchOutlined, ToolOutlined, ApartmentOutlined, FileTextOutlined } from "@ant-design/icons-vue";

const go = (val = "/") => {
  window.location.hash = val;
};

const openZh2tw = () => {
  go('/zh2tw-vannak');
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
        <a-card-grid class="card c2" @click="go('/outline-translate')"><span class="card_text">纲目翻译</span></a-card-grid>
        <a-card-grid class="card c2" @click="go('/enhanced-translate-official')"><span class="card_text">增强式翻译</span></a-card-grid>
        <a-card-grid class="card c2" @click="go('/zh-convert')"><span class="card_text">简繁互转</span></a-card-grid>
        <a-card-grid class="card c2" @click="go('/article-polish')"><span class="card_text">文章润色</span></a-card-grid>
        <a-card-grid class="card c2" @click="go('/roundtable')">
          <span class="card_text">AI圆桌</span>
        </a-card-grid>
        <a-card-grid class="card c2" @click="go('/feast-outline-maker')">
          <span class="card_text">节期-数据制作</span>
        </a-card-grid>
      </a-card>
    </div>
    <br />
    <br />
    <div class="cards">
      <a-card>
        <template #title>
          <div class="card_title"><FileTextOutlined /> 纲目</div>
        </template>
        <a-card-grid class="card c2" @click="go('/rough-outline')"><span class="card_text">毛胚纲目</span></a-card-grid>
        <a-card-grid class="card c2" @click="go('/feast-outline')"><span class="card_text">节期纲目</span></a-card-grid>
        <a-card-grid class="card c2" @click="go('/ministerialize-outline')"><span class="card_text">纲目职事化</span></a-card-grid>
        <a-card-grid class="card c2" @click="go('/bird-view-outline')"><span class="card_text">词典-鸟瞰纲目</span></a-card-grid>
      </a-card>
    </div>
    <br />
    <br />
    <div class="cards">
      <a-card>
        <template #title>
          <div class="card_title"><ApartmentOutlined /> 图谱测试</div>
        </template>
        <a-card-grid class="card c2" @click="go('/kg-rag-test')"><span class="card_text">KG-RAG 测试工作台</span></a-card-grid>
      </a-card>
    </div>
    <br />
    <br />
    <div class="cards">
      <a-card>
        <template #title>
          <div class="card_title">Vichhet &amp; Chom Pei 测试</div>
        </template>
        <a-card-grid class="card c2" @click="go('/practice-translate')"><span class="card_text">纲目翻译练习</span></a-card-grid>
        <a-card-grid class="card c2" @click="go('/zh2tw-practice')"><span class="card_text">简繁互转练习</span></a-card-grid>
        <a-card-grid class="card c2" @click="go('/practice-kg-rag')">
          <span class="card_text">AI纲目制作练习</span>
        </a-card-grid>
        <a-card-grid class="card c2" @click="go('/article-polish-c')"><span class="card_text">文章润色练习</span></a-card-grid>
        <a-card-grid class="card c2" @click="go('/bird-view-c')">
          <span class="card_text">词典-鸟瞰纲目练习</span>
        </a-card-grid>
        <a-card-grid class="card c2" @click="go('/feast-outline-c')">
          <span class="card_text">节期纲目制作练习</span>
        </a-card-grid>
        <a-card-grid class="card c2" @click="go('/rough-outline-c')">
          <span class="card_text">毛胚纲目制作练习</span>
        </a-card-grid>
        <a-card-grid class="card c2" @click="go('/ministerialize-c')">
          <span class="card_text">纲目职事化练习</span>
        </a-card-grid>
      </a-card>
    </div>
    <br />
    <br />
    <div class="cards">
      <a-card>
        <template #title>
          <div class="card_title">Vannak &amp; Sila 测试</div>
        </template>
        <a-card-grid class="card c2" @click="go('/test-translate-vannak')"><span class="card_text">翻译工具</span></a-card-grid>
        <a-card-grid class="card c2" @click="go('/bird-view-a')">
          <span class="card_text">鸟瞰纲目</span>
        </a-card-grid>
        <a-card-grid class="card c2" @click="openZh2tw()"><span class="card_text">简繁互转</span></a-card-grid>
        <a-card-grid class="card c2" @click="go('/generate-outline-vannak')">
          <span class="card_text">PanAI 纲目生成</span>
        </a-card-grid>
        <a-card-grid class="card c2" @click="go('/article-polish-vannak')">
          <span class="card_text">文章润色</span>
        </a-card-grid>
        <a-card-grid class="card c2" @click="go('/feast-outline-a')">
          <span class="card_text">节期纲目</span>
        </a-card-grid>
        <a-card-grid class="card c2" @click="go('/rough-outline-a')">
          <span class="card_text">毛胚纲目</span>
        </a-card-grid>
        <a-card-grid class="card c2" @click="go('/ministerialize-a')">
          <span class="card_text">纲目职事化</span>
        </a-card-grid>
      </a-card>
    </div>
    <br />
    <br />
    <div class="cards">
      <a-card>
        <template #title>
          <div class="card_title">Piseth &amp; Sopheap 测试</div>
        </template>
        <a-card-grid class="card c2" @click="go('/outline-translate-test')">
          <span class="card_text">纲目翻译测试</span>
        </a-card-grid>
        <a-card-grid class="card c2" @click="go('/testb-zh2tw')">
          <span class="card_text">简繁互转测试</span>
        </a-card-grid>
        <a-card-grid class="card c2" @click="go('/panai2-test')">
          <span class="card_text">AI纲目制作</span>
        </a-card-grid>
        <a-card-grid class="card c2" @click="go('/article-polish-hub')">
          <span class="card_text">文章润色测试</span>
        </a-card-grid>
        <a-card-grid class="card c2" @click="go('/bird-view-b')">
          <span class="card_text">词典-鸟瞰纲目测试</span>
        </a-card-grid>
        <a-card-grid class="card c2" @click="go('/feast-outline-b')">
          <span class="card_text">节期纲目测试</span>
        </a-card-grid>
        <a-card-grid class="card c2" @click="go('/rough-outline-b')">
          <span class="card_text">毛胚纲目测试</span>
        </a-card-grid>
        <a-card-grid class="card c2" @click="go('/ministerialize-b')">
          <span class="card_text">职事化测试</span>
        </a-card-grid>
        <a-card-grid class="card c2" @click="go('/ministry-qa-b')">
          <span class="card_text">职事问答测试</span>
        </a-card-grid>
      </a-card>
    </div>
    <br />
    <br />
    <div class="cards">
      <a-card>
        <template #title>
          <div class="card_title">Sotchea 测试</div>
        </template>
        <a-card-grid class="card c2" @click="go('/enhanced-translate')">
          <span class="card_text">增强式翻译</span>
        </a-card-grid>
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
