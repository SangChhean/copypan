<script setup>
import { ref } from "vue";
import { storeToRefs } from "pinia";
import { useStore } from "../../store/index";
const { showMsgs, showMsgOpen, hilights } = storeToRefs(useStore());

const handleOk = () => {
  showMsgOpen.value = false;
};

const hiLight = (text) => {
  hilights.value.forEach((item) => {
    text = text.replaceAll(item, `<em>${item}</em>`);
  });
  return text;
};
</script>

<template>
  <a-modal v-model:open="showMsgOpen" width="100%" wrap-class-name="full-modal">
    <template #footer>
      <a-button key="back" @click="handleOk" type="primary">关闭</a-button>
    </template>
    <div v-for="item in showMsgs" v-html="hiLight(item.text)" :class="item.type"></div>
  </a-modal>
</template>

<style lang="less">
.full-modal {
  .ant-modal {
    max-width: 94%;
    top: 0;
    padding-bottom: 0;
    margin: 3%;
    // margin-bottom: 100px;
  }
  .ant-modal-content {
    display: flex;
    flex-direction: column;
  }
  .ant-modal-body {
    flex: 1;
  }
}

.bookname,
.title {
  text-align: center;
  font-weight: bold;
  font-size: x-large;
}

.bookname {
  color: #0b5311;
}

.title {
  font-size: large;
  color: #1677ff;
  margin-bottom: 1em;
  border-bottom: 1px solid #eee;
  padding-bottom: 10px;
}

.map_title {
  font-weight: bold;
  // text-align: center;
  color: #1677ff;
  font-size: large;
}

.ot1 {
  font-weight: bold;
  font-size: large;
}

.ot1,
.ot2 {
  text-indent: -2em;
  padding-left: 2em;
}

.ot3 {
  text-indent: -1.5em;
  padding-left: 1.5em;
}

.map_heading,
.map_bib {
  font-weight: bold;
  font-size: large;
  color: #300b53;
  padding-left: 4em;
  text-indent: -2em;
}

.map_bib {
  color: #000;
}
</style>
