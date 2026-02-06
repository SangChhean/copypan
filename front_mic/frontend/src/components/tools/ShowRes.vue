<script setup>
import { watch, computed, ref, onMounted, onUnmounted, nextTick } from "vue";
import { storeToRefs } from "pinia";
import { useStore } from "../../store/index";
import axios from "axios";

const { showMsgs, showMsgOpen, hilights, refid, openMsg } = storeToRefs(useStore());
const leftWidth = ref(50);
const rightWidth = ref(50);
const isDragging = ref(false);
const isHeading = ref(true);
const hideEng = ref(false);
const showOutlineOpen = ref(false);
const outlines = ref([]);

const handleOk = () => {
  showMsgOpen.value = false;
  showOutlineOpen.value = false;
};

const resData = ref("");

const showData = computed(() => {
  if (!resData.value) {
    return {
      bread: [],
      zh: [["", ""]],
      en: [["", ""]],
    };
  }

  let res = resData.value;

  if (!res.en) {
    hideEng.value = true;
  } else hideEng.value = false;

  if (isHeading.value) {
    let en = res.en;
    let zh = res.zh;

    if (!en) en = [];

    let arr = {
      en: en.filter((item) => {
        return ["heading", "ot1", "bible_reading", "b_read", "title", "bookname"].includes(item[1]);
      }),
      zh: zh.filter((item) => {
        return ["heading", "ot1", "bible_reading", "b_read", "title", "bookname"].includes(item[1]);
      }),
      type: res.type,
      refid: res.refid,
      bread: res.bread,
      showButtons: res.showButtons,
    };
    return arr;
  } else return resData.value;
});

const getMsg = () => {
  let formdata = new FormData();
  formdata.append("refid", refid.value);

  let token = localStorage.getItem("token") || null;
  axios.defaults.headers.common["Authorization"] = `Bearer ${token}`;
  axios
    .post("/api/reading", formdata)
    .then((res) => {
      let data = res.data["_source"];
      resData.value = data;
      showMsgOpen.value = true;
      nextTick(() => {
        let el = document.querySelector(".full-modal-res");
        el.scrollTop = 0;
      });
    })
    .catch((err) => {});
};

const getOutline = () => {
  let formdata = new FormData();
  formdata.append("refid", refid.value);
  let token = localStorage.getItem("token") || null;
  axios.defaults.headers.common["Authorization"] = `Bearer ${token}`;

  axios.post("/api/outline", formdata).then((res) => {
    console.log(res.data);
    if (res.data) {
      outlines.value = res.data;
      showOutlineOpen.value = true;
    } else return;
  });
  console.log(refid.value);
};

const get_res = () => {
  if (!refid.value) {
    return;
  }

  if (refid.value.includes("heading")) {
    refid.value = refid.value.replace("-heading", "");
    isHeading.value = true;
    getMsg();
  } else if (refid.value.includes("outline")) {
    refid.value = refid.value.replace("-outline", "");
    getOutline();
  } else {
    isHeading.value = false;
    getMsg();
  }
};

watch(openMsg, () => {
  showMsgOpen.value = false;
  get_res();
});

const hiLight = (text) => {
  hilights.value.forEach((item) => {
    text = text.replaceAll(item, `<em>${item}</em>`);
  });
  return text;
};

const search = (val) => {
  refid.value = val;
  get_res();
};

const startDrag = (event) => {
  isDragging.value = true;
  document.addEventListener("mousemove", onDrag);
  document.addEventListener("mouseup", stopDrag);
};

const onDrag = (event) => {
  if (isDragging.value) {
    const containerWidth = document.querySelector(".rowbox").clientWidth;
    const newLeftWidth = (event.clientX / containerWidth) * 100;
    leftWidth.value = newLeftWidth - 3;
    rightWidth.value = 100 - newLeftWidth;
  }
};

const stopDrag = () => {
  isDragging.value = false;
  document.removeEventListener("mousemove", onDrag);
  document.removeEventListener("mouseup", stopDrag);
};

onMounted(() => {
  document.addEventListener("mouseup", stopDrag);
});

onUnmounted(() => {
  document.removeEventListener("mouseup", stopDrag);
});
</script>

<template>
  <a-modal v-model:open="showOutlineOpen" width="80%">
    <template #footer>
      <a-button key="back" @click="handleOk" type="primary">关闭</a-button>
    </template>
    <div class="modal-root">
      <div v-for="item in outlines.msg" :class="item.type" v-html="item.text"></div>
    </div>
  </a-modal>

  <a-modal v-model:open="showMsgOpen" width="100%" wrap-class-name="full-modal-res">
    <template #footer>
      <a-button key="back" @click="handleOk" type="primary">关闭</a-button>
    </template>
    <div>
      <a-breadcrumb>
        <a-breadcrumb-item v-for="item in showData.bread">
          <a v-if="item.refid" @click="search(item.refid)">{{ item.text }}</a>
          <span v-else>{{ item.text }}</span>
        </a-breadcrumb-item>
      </a-breadcrumb>
    </div>
    <div v-if="showData.showButtons == '1'">
      <a-divider style="margin: 10px 0"></a-divider>
      <a-space>
        <a-button @click="isHeading = false" :type="isHeading ? 'default' : 'primary'">查看整篇</a-button>
        <a-button @click="isHeading = true" :type="isHeading ? 'primary' : 'default'">只看标题</a-button>
      </a-space>
    </div>

    <a-divider style="margin: 10px 0"></a-divider>
    <div v-if="showData.cells">
      <a-space wrap>
        <a-button v-for="item in showData.cells" v-text="item.text" @click="search(item.refid)" type="primary"></a-button>
      </a-space>
    </div>
    <div v-else-if="showData.toc">
      <div v-for="item in showData.toc" v-html="hiLight(item.text)" :class="item.type" @click="search(item.refid)"></div>
    </div>
    <div v-else>
      <div class="onlyZh" v-if="hideEng">
        <div v-for="item in showData.zh" v-html="hiLight(item[0])" :class="item[1]"></div>
      </div>
      <div class="rowbox" v-else>
        <div class="col" :style="{ width: leftWidth + '%' }">
          <div v-for="item in showData.zh" v-html="hiLight(item[0])" :class="item[1]"></div>
        </div>
        <div class="divider" @mousedown="startDrag"></div>
        <div class="col" :style="{ width: rightWidth + '%' }">
          <div v-for="item in showData.en" v-html="hiLight(item[0])" :class="item[1]"></div>
        </div>
      </div>
    </div>
  </a-modal>
</template>

<style lang="less">
.modal-root {
  margin-top: 1em;
}
.rowbox {
  display: flex;
  width: 100%;
  min-height: 50vh;
  .col {
    background-color: #f0f0f0;
    padding: 10px;
    box-sizing: border-box;
    border-radius: 10px;
  }
  .divider {
    width: 5px;
    background-color: #8d8d8d;
    cursor: ew-resize;
    height: auto;
    margin: 0 20px;
    border-radius: 3px;
  }
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

.onlyZh {
  background-color: #f0f0f0;
  padding: 1em;
  width: 100%;
  border-radius: 10px;
}

.full-modal-res {
  .ant-modal {
    max-width: 100%;
    top: 0;
    padding-bottom: 0;
    margin: 0;
  }
  .ant-modal-content {
    display: flex;
    flex-direction: column;
    height: auto;
    min-height: 80vh;
  }
  .ant-modal-body {
    flex: 1;
  }
}

div.ver,
div.text {
  text-align: justify;
  // text-indent: -5em;
  padding: 5px;
  background: #fff;
  border-radius: 5px;
  margin-bottom: 5px;
}

div.toc {
  cursor: pointer;
  padding: 5px;
  background: #f0f0f0;
  border-radius: 5px;
  margin-bottom: 5px;
}

div.toc:hover {
  font-weight: bold;
  color: #fff;
  background-color: #1677ff;
}

.bookname {
  text-align: center;
  font-weight: bold;
  font-size: x-large;
  color: #0b6108;
}

div.title {
  color: #1677ff;
  font-weight: bold;
  font-size: large;
  text-align: center;
  margin-bottom: 1em;
}

div.heading {
  color: #1677ff;
  font-weight: bold;
  text-align: center;
}
</style>
