<script setup>
import { nextTick, reactive, ref, watch } from "vue";
import useStore from "../../store";
import { storeToRefs } from "pinia";
import axios from "axios";
import { onMounted } from "vue";

const MyStore = useStore();
const store = storeToRefs(MyStore);

const searchFiledOptions = {
  a: { lab: "全部", val: "a" },
  b: { lab: "篇题", val: "b" },
  c: { lab: "标题", val: "c" },
  d: { lab: "大纲", val: "d" },
  e: { lab: "摘录", val: "e" },
  f: { lab: "大本", val: "f" },
  g: { lab: "补充", val: "g" },
  h: { lab: "新歌", val: "h" },
  i: { lab: "儿童", val: "i" },
  j: { lab: "经文", val: "j" },
  k: { lab: "注解", val: "k" },
  l: { lab: "书报", val: "l" },
  m: { lab: "书名", val: "m" },
  n: { lab: "总题", val: "n" },
};

const getFileds = (val) => {
  let listOfFileds = [];
  for (let i in val) {
    listOfFileds.push(searchFiledOptions[val[i]]);
  }
  return listOfFileds;
};

const searchFiledItems = ref([
  { lab: "全部", val: "a" },
  { lab: "书名", val: "m" },
  { lab: "篇题", val: "b" },
  { lab: "标题", val: "c" },
]);

const searchModel = ref("match_or");

const radioOptions = [
  { label: "模糊模式", value: "match_or" },
  { label: "平衡模式", value: "match_and" },
  { label: "完全匹配", value: "match_all" },
];

const searchFiled = ref(searchFiledItems.value[0].lab);

const searchFiledSelected = (val) => {
  store.searchFiled.value = val;
  searchFiled.value = searchFiledOptions[val].lab;
  pagination.current = 1;
  search();
};

watch(store.index, (val) => {
  let chars = "mbc";
  if (val == "0") chars = "ambc";
  else if (val == "1") chars = "jk";
  else if (val == "2") chars = "abc";
  else if (val == "3") chars = "ambc";
  else if (val == "4") chars = "ambc";
  else if (val == "5") chars = "anbd";
  else if (val == "6") chars = "abcde";
  else if (val == "7") chars = "abc";
  else if (val == "10") chars = "f";

  searchFiledItems.value = getFileds(chars);
  searchFiled.value = searchFiledItems.value[0].lab;
  store.searchFiled.value = searchFiledItems.value[0]["val"];

  if (input.value) search();
});

const input = ref();
const search_res = ref();
const show_res = ref();
const total = ref(0);
const show_footer = ref(false);
const show_id = ref(false);
const loading = ref(false);
const not_bible = ref(true);
const hide_info = ref(true);
const search = () => {
  if (input.value.replace(/\s/g, "") == "") return;
  hide_info.value = false;
  let data = new FormData();
  data.append("keyword", input.value);
  data.append("searchM", searchModel.value);
  data.append("index", store.index.value);
  data.append("searchF", store.searchFiled.value);
  data.append("page", pagination.current);
  data.append("pageSize", pagination.pageSize);
  data.append("searchGroup", store.searchGroup.value);
  loading.value = true;
  const url = "/api/search";

  if (store.index.value == "1") not_bible.value = false;
  else not_bible.value = true;

  axios.post(url, data).then((res) => {
    if (res.data.status == "login") window.location.hash = "login";
    else {
      search_res.value = res.data;
      console.log(search_res.value);
      show_res.value = res.data["msgs"];
      total.value = res.data["total"];
      if (total.value == "10000+") total.value = 10000;
      show_footer.value = true;
      res.data["role"] == "pass" ? (show_id.value = true) : (show_id.value = false);
      loading.value = false;
    }
  });
};

const visible = ref(false);

const closeAlart = () => {
  setTimeout(() => {
    let el = document.querySelector(".arco-alert-banner");
    if (el) el.style.display = "none";
  }, 5000);
};

const handleClick = () => {
  visible.value = true;
  closeAlart();
};

const handleOk = () => {
  visible.value = false;
};

const backTOP = () => {
  let el = document.querySelector(".arco-modal-body");
  el.scrollTop = 0;
};

const read_more_msg = ref({ zh: "", en: "" });
const fenci = ref([]);
const show_reading = ref(false);
const show_english = ref(true);
const read_more = (book_id, type) => {
  show_reading.value = true;
  let data = new FormData();
  data.append("book_id", book_id);
  data.append("type", type);
  data.append("keywords", search_res.value["keywords"]);
  data.append("mode", search_res.value["mode"]);
  read_more_msg.value = ref({ zh: "", en: "" });
  axios.post("/api/read_more", data).then((res) => {
    if (res.data.status == "login") window.location.hash = "login";
    else {
      read_more_msg.value = res.data["msg"];
      console.log(read_more_msg.value);
      if (read_more_msg.value["en"][0].text) {
        show_english.value = true;
      } else {
        show_english.value = false;
      }

      fenci.value = res.data["fenci"];
    }
    show_reading.value = false;
  });

  handleClick();
  nextTick(() => {
    backTOP();
  });
};

const window_width = () => {
  let w = window.innerWidth;
  if (w % 2 == 0) return (w / 2).toString() + "px";
  else return ((w - 1) / 2).toString() + "px";
};

const pagination = reactive({
  current: 1,
  pageSize: 10,
});

const onPageChange = () => {
  search();
  // 返回顶部
  document.body.scrollTop = 0;
  document.documentElement.scrollTop = 0;
};

const show_model2 = ref(false);
const model2_values = reactive({
  zh: "中文",
  en: "英文",
  id: "",
  cid: "",
});
const get_fenci = () => {
  let data = new FormData();
  data.append("keywords", search_res.value["keywords"]);
  data.append("mode", search_res.value["mode"]);

  axios.post("/api/fenci", data).then((res) => {
    fenci.value = res.data;
  });
};
const edit = (id, zh, en, cid) => {
  model2_values.zh = zh.replace(/<\/?em>/g, "");
  model2_values.en = en.replace(/<\/?em>/g, "");
  model2_values.id = id;
  model2_values.cid = cid;
  show_model2.value = true;
};
const edit_this = () => {
  let data = new FormData();
  data.append("id", model2_values.id);
  data.append("zh", model2_values.zh);
  data.append("en", model2_values.en);
  data.append("cid", model2_values.cid);

  if (fenci.value == 0) get_fenci();

  axios.post("/api/edit_para", data).then((res) => {
    if (res.data == "1") {
      for (let item of show_res.value) {
        if (item["id"] == model2_values.id) {
          let chi = model2_values.zh;
          let eng = model2_values.en;
          for (let idx in fenci.value) {
            let t = fenci.value[idx];
            chi = chi.replace(t, `<em>${t}</em>`);
          }
          item["zh"] = chi;
          item["en"] = eng;
        }
      }
    }
  });
};

const copied = ref([]);
const copy = (id, text) => {
  text = text.replace(/<\/?[a-z]+>/g, "");
  navigator.clipboard.writeText(text);
  copied.value.push(id);
  setTimeout(() => {
    copied.value = copied.value.filter((item) => item != id);
  }, 1000);
};

const searchGroupItems = {
  a: {
    lab: "A类",
    val: "a",
  },
  b: {
    lab: "B类",
    val: "b",
  },
  c: {
    lab: "C类",
    val: "c",
  },
};

const searchGroupText = ref("A类");
const searchGroupSelected = (val) => {
  store.searchGroup.value = val;
  searchGroupText.value = searchGroupItems[val].lab;
  pagination.current = 1;
  search();
};

const redioChange = (val) => {
  pagination.current = 1;
  search();
};

onMounted(() => {
  store.index.value = "0";
});
</script>

<template>
  <a-row>
    <a-col :xs="0" :lg="4"></a-col>
    <a-col :xs="24" :lg="16">
      <a-input-search placeholder="输入关键字，按回车搜索" show-word-limit button-text="Search" allow-clear search-button size="large" v-model="input" @search="search" @press-enter="search">
        <template #prepend>
          <a-dropdown trigger="hover" @select="searchGroupSelected" v-if="store.index.value == '0'">
            <div style="cursor: pointer">{{ searchGroupText }}</div>
            <template #content>
              <a-doption v-for="item in searchGroupItems" :key="item.val" v-text="item.lab" :value="item.val"></a-doption>
            </template>
          </a-dropdown>
          <icon-oblique-line v-if="store.index.value == '0'" />
          <a-dropdown trigger="hover" @select="searchFiledSelected">
            <div style="cursor: pointer">{{ searchFiled }}</div>
            <template #content>
              <a-doption v-for="item in searchFiledItems" :key="item.val" v-text="item.lab" :value="item.val"></a-doption>
            </template>
          </a-dropdown>
        </template>
      </a-input-search>
    </a-col>
    <a-col :xs="0" :lg="4"></a-col>
  </a-row>
  <a-space></a-space>
  <a-row>
    <a-col :xs="0" :lg="4"></a-col>
    <a-col :xs="24" :lg="16">
      <a-radio-group type="button" v-model="searchModel" :options="radioOptions" @change="redioChange"></a-radio-group>
    </a-col>
    <a-col :xs="0" :lg="4"></a-col>
  </a-row>
  <a-space></a-space>
  <a-row>
    <a-col :xs="0" :lg="4"></a-col>
    <a-col :xs="24" :lg="16">
      <a-alert v-if="hide_info && store.index.value == '0'">
        <ul>
          <li>A类：经文、注解、生命读经、倪文集、李文集、其他</li>
          <li>B类：A类、诗歌、节期</li>
          <li>C类：B类、上河图</li>
        </ul>
      </a-alert>
    </a-col>
    <a-col :xs="0" :lg="4"></a-col>
  </a-row>
  <a-space></a-space>

  <div v-if="loading" style="margin-top: 150px; text-align: center">
    <a-spin :size="32" tip="搜索中……" />
  </div>

  <div id="res" v-else>
    <a-alert v-if="show_footer">为您找到 {{ search_res["total"] }} 条结果，耗时 {{ search_res["time"] }} 秒</a-alert>
    <a-card class="res_card" v-for="item in show_res" :key="item['id']" :bordered="false">
      <a-space>
        <a-tag color="#86909c" v-for="tag in item['tags']">
          <template #icon>
            <span style="color: #fff"><icon-pushpin /></span>
          </template>
          {{ tag }}
        </a-tag>
      </a-space>

      <p>
        <span v-html="item[item['up']]"></span>
        <span>
          <a-button size="mini" @click="copy(item['id'] + 'up', item[item['up']])" v-if="copied.includes(item['id'] + 'up')" type="primary">
            <icon-check />
          </a-button>
          <a-button type="outline" size="mini" @click="copy(item['id'] + 'up', item[item['up']])" v-else>
            <icon-copy />
          </a-button>
        </span>
      </p>
      <div v-if="item[item['down']] && item[item['down']] != '无'">
        <a-divider />
        <p>
          <span v-html="item[item['down']]"></span>
          <span>
            <a-button size="mini" @click="copy(item['id'] + 'down', item[item['down']])" v-if="copied.includes(item['id'] + 'down')" type="primary">
              <icon-check />
            </a-button>
            <a-button type="outline" size="mini" @click="copy(item['id'] + 'down', item[item['down']])" v-else>
              <icon-copy />
            </a-button>
          </span>
        </p>
      </div>

      <div v-if="['书名', '总题'].includes(searchFiled)">
        <a-divider />
        <a-button type="outline" @click="read_more(item.id, 'bookname')">
          <icon-eye />
          查看目录
        </a-button>
      </div>
      <div v-if="not_bible && item.show">
        <a-divider />
        <a-space>
          <a-button type="outline" @click="read_more(item.chapter_id, 'all')">
            <icon-eye />
            查看整篇
          </a-button>
          <a-button type="outline" @click="read_more(item.chapter_id, 'title')" :disabled="item['id'].includes('hymn')">
            <icon-eye />
            只看标题
          </a-button>
          <a-button type="outline" v-if="show_id" @click="edit(item.id, item.zh, item.en, item.chapter_id)">
            <icon-edit />
            修改
          </a-button>
        </a-space>
        <a-divider />

        <ul class="ul">
          <li v-if="show_id">本段序列：{{ item["id"] }}</li>
          <li v-if="show_id">本篇序列：{{ item["chapter_id"] }}</li>
          <li>中文出处：{{ item["source_zh"] }}</li>
          <li>中文篇题：{{ item["chapter_name_zh"] }}</li>
          <li>
            完整出处：（{{ item["source_zh"] }}，第{{ item["para"] }}段）
            <a-button status="danger" size="mini" @click="copy(item['id'] + 'zc', `（${item['source_zh']}，第${item['para']}段）`)" v-if="copied.includes(item['id'] + 'zc')" type="primary">
              <icon-check />
            </a-button>
            <a-button type="outline" size="mini" @click="copy(item['id'] + 'zc', `（${item['source_zh']}，第${item['para']}段）`)" v-else>
              <icon-copy />
            </a-button>
          </li>
          <li>
            英文出处：({{ item["source_en"] }})
            <a-button status="danger" size="mini" @click="copy(item['id'] + 'ec', `(${item['source_en']})`)" v-if="copied.includes(item['id'] + 'ec')" type="primary">
              <icon-check />
            </a-button>
            <a-button type="outline" size="mini" @click="copy(item['id'] + 'ec', `(${item['source_en']})`)" v-else>
              <icon-copy />
            </a-button>
          </li>
          <li v-if="item.chapter_name_en">英文篇题：{{ item["chapter_name_en"] }}</li>
        </ul>
      </div>
    </a-card>
    <div v-if="show_footer">
      <a-divider />
      <div v-if="total != 0" id="footer">
        <a-pagination :total="total" v-model:current="pagination.current" v-model:page-size="pagination.pageSize" show-total show-jumper show-page-size @change="onPageChange" />
      </div>
    </div>
  </div>

  <div id="modals">
    <a-modal v-model:visible="visible" @ok="handleOk" ok-text="关闭" fullscreen hide-cancel>
      <template #title>
        <a-space>
          <a-alert closable :banner="true">1. 用鼠标拖拽分割条，可以快速灵活的调整宽度; 2. 按 ESC 键可快速关闭窗口</a-alert>
          <a-button @click="backTOP" status="danger">回顶部</a-button>
        </a-space>
      </template>
      <div style="float: left" v-if="show_english">
        <a-resize-box
          :directions="['right']"
          :style="{
            width: window_width(),
            maxWidth: '98%',
            height: '50000px',
          }"
        >
          <p v-for="item in read_more_msg.zh" :class="item.type + ' left'" v-html="item.text"></p>
          <div v-if="show_reading" style="margin-top: 150px; text-align: center">
            <a-spin :size="32" tip="读取中……" />
          </div>
        </a-resize-box>
      </div>
      <div v-else>
        <p v-for="item in read_more_msg.zh" :class="item.type + ' left'" v-html="item.text"></p>
        <div v-if="show_reading" style="margin-top: 150px; text-align: center">
          <a-spin :size="32" tip="读取中……" />
        </div>
      </div>
      <div style="">
        <p v-for="item in read_more_msg.en" :class="item.type + ' right'" v-html="item.text"></p>
        <div v-if="show_reading" style="margin-top: 150px; text-align: center">
          <a-spin :size="32" tip="读取中……" />
        </div>
      </div>
    </a-modal>

    <a-modal draggable v-model:visible="show_model2" title="编辑本段" @ok="edit_this" :modal-style="{ width: '80%' }" :align-center="false" :top="70" ok-text="修改">
      <a-textarea
        v-model:model-value="model2_values.zh"
        :auto-size="{
          minRows: 7,
          maxRows: 12,
        }"
      />
      <a-textarea
        v-model:model-value="model2_values.en"
        :auto-size="{
          minRows: 7,
          maxRows: 12,
        }"
      />
    </a-modal>
  </div>
  <div style="margin-bottom: 7em"></div>
</template>

<style>
#footer {
  margin-top: 1em;
}

.ul {
  color: var(--color-neutral-10) !important;
}

.res_card {
  transition-property: all;
  margin-top: 1em;
}

p.left {
  padding-right: 12px;
}

#res {
  width: 98%;
  margin: 0 auto;
}

p.verse {
  margin-top: 2em;
}
p.chorus {
  color: blue;
  margin-top: -1em;
}

p {
  text-align: justify;
  color: var(--color-neutral-10);
}
</style>
