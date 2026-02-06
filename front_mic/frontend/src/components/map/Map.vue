<script lang="ts" setup>
import { h, ref, computed } from "vue";
import { PaperClipOutlined, FilterOutlined, SearchOutlined, CloudDownloadOutlined, ArrowLeftOutlined } from "@ant-design/icons-vue";
import axios from "axios";
import { storeToRefs } from "pinia";
import { useStore } from "../../store/index";
import ShowMsg from "../tools/ShowMsg.vue";
import { checkSession } from "../utils";
checkSession();

const { showMsgs, showMsgOpen, hilights, showIndex } = storeToRefs(useStore());

const selectedKeys = ref(["1"]);
const openKeys = ref(["sub1", "sub2", "sub3", "sub4", "sub5"]);
const input = ref("");
const filter_words = ref("");
const filename = ref("圣经经文");
const total = ref(0);
const showLoading = ref(false);

const items = ref([
  {
    key: "1",
    icon: () => h(PaperClipOutlined),
    label: "圣经经文",
    title: "verse",
  },
  {
    key: "2",
    icon: () => h(PaperClipOutlined),
    label: "圣经注解",
    title: "note",
  },
  {
    key: "3",
    icon: () => h(PaperClipOutlined),
    label: "生命读经",
    title: "life",
  },
  {
    key: "sub1",
    icon: () => h(PaperClipOutlined),
    label: "倪文集",
    title: "nee",
    children: [
      {
        key: "4",
        label: "倪文集书名",
        title: "nee_book",
      },
      {
        key: "5",
        label: "倪文集篇题",
        title: "nee_title",
      },
    ],
  },
  {
    key: "sub2",
    icon: () => h(PaperClipOutlined),
    label: "李文集",
    title: "lee",
    children: [
      {
        key: "6",
        label: "李文集书名",
        title: "lee_book",
      },
      {
        key: "7",
        label: "李文集篇题",
        title: "lee_title",
      },
    ],
  },
  {
    key: "sub3",
    icon: () => h(PaperClipOutlined),
    label: "其他",
    title: "other",
    children: [
      {
        key: "8",
        label: "新约总论书名",
        title: "other_book",
      },
      {
        key: "9",
        label: "新约总论篇题",
        title: "other_title",
      },
      {
        key: "10",
        label: "真理/生命课程、时代先见",
        title: "other_title",
      },
    ],
  },
  {
    key: "sub4",
    icon: () => h(PaperClipOutlined),
    label: "节期纲目",
    title: "feasts",
    children: [
      {
        key: "11",
        label: "节期纲目书名",
        title: "feasts_book",
      },
      {
        key: "12",
        label: "节期纲目篇题",
        title: "feasts_title",
      },
    ],
  },
  {
    key: "sub5",
    icon: () => h(PaperClipOutlined),
    label: "主恢复的清明上河图",
    title: "map",
    children: [
      {
        key: "13",
        label: "上河图书名",
        title: "pano_book",
      },
      {
        key: "14",
        label: "上河图篇题",
        title: "pano_title",
      },
    ],
  },
  {
    key: "15",
    icon: () => h(PaperClipOutlined),
    label: "诗歌",
    title: "hym",
  },
]);

const raws = ref([]);
const goBack = () => {
  window.history.back();
};

const showColumns = computed(() => {
  let cols;
  let index = selectedKeys.value[0];
  if (index == "1") {
    cols = [
      {
        title: "出处",
        dataIndex: "source",
        sorter: (a, b) => a.sn - b.sn,
        defaultSortOrder: "ascend",
        width: "120px",
      },
      { title: "经文", dataIndex: "text" },
    ];
  } else {
    cols = [
      { title: "题目", dataIndex: "text", sorter: (a, b) => a.sn - b.sn, defaultSortOrder: "ascend" },
      { title: "出处", dataIndex: "source", width: "50%" },
      { title: "查看", dataIndex: "lab", align: "center", width: "100px" },
    ];
  }
  return cols;
});

const onSearch = (value: string) => {
  raws.value = [];
  showLoading.value = true;
  let fwds = filter_words.value;
  let inputVar = input.value;
  let index = selectedKeys.value[0];

  inputVar = inputVar.trim();
  if (!inputVar) {
    showLoading.value = false;
    return;
  } else {
    hilights.value = inputVar.split(/ +/g);
  }

  let token = localStorage.getItem("token") || null;
  axios.defaults.headers.common["Authorization"] = `Bearer ${token}`;

  let formData = new FormData();
  formData.append("input", inputVar);
  formData.append("fwds", fwds ? fwds : " ");
  formData.append("index", index);
  axios.post("/api/map", formData).then((res) => {
    let data = res.data;
    raws.value = data;
    total.value = data.length;
    showLoading.value = false;
  });
};

function onChange(pagination, filters, sorter, extra) {}

const pagination = computed(() => ({
  pageSizeOptions: ["10", "20", "30", "40", "50"],
  showTotal: (total) => `共 ${total} 条`,
}));

const downloadTxt = (filename: string, text: string) => {
  var element = document.createElement("a");
  element.setAttribute("href", "data:text/plain;charset=utf-8," + encodeURIComponent(text));
  element.setAttribute("download", filename);
  element.style.display = "none";
  document.body.appendChild(element);
  element.click();
  document.body.removeChild(element);
};

const disDownload = computed(() => {
  return raws.value.length == 0;
});

const getClearRaw = () => {
  let res = [];
  for (let i = 0; i < raws.value.length; i++) {
    let item = raws.value[i];
    item.text = item.text.replace(/<[^>]+>/g, "");
    res.push(item);
  }
  return res;
};

const exportRes = () => {
  let fname = filename.value + ".json";
  let text = JSON.stringify(getClearRaw(), null, 2);
  downloadTxt(fname, text);
};

const navClick = (item: any) => {
  filename.value = item.item.originItemValue.label;
  onSearch("");
};

const openMsg = (msg) => {
  showMsgs.value = msg;
  showMsgOpen.value = true;
};
</script>

<template>
  <div v-if="showIndex">
    <div class="header-pg">
      <div @click="goBack" class="back"><ArrowLeftOutlined /></div>
      <div style="text-align: center; width: 100%">思路工具</div>
    </div>
    <a-divider :style="{ margin: '10px 0' }"></a-divider>
    <a-row :wrap="false">
      <a-col flex="250px">
        <div>
          <a-menu v-model:openKeys="openKeys" v-model:selectedKeys="selectedKeys" style="width: 240px" mode="inline" :items="items" :forceSubMenuRender="true" @select="navClick" />
          <br />
        </div>
      </a-col>
      <a-col flex="auto" class="res">
        <div class="content">
          <div class="search_bar">
            <div style="width: 80%; max-width: 1000px">
              <a-input-search v-model:value="input" placeholder="请输入搜索词，多词以空格隔开" enter-button @search="onSearch">
                <template #prefix>
                  <SearchOutlined />
                </template>
              </a-input-search>
              <div style="margin: 10px"></div>
              <a-input v-model:value="filter_words" placeholder="请输入过滤词，多词以空格隔开" @pressEnter="onSearch">
                <template #prefix>
                  <FilterOutlined />
                </template>
              </a-input>
            </div>
          </div>
          <a-divider :style="{ margin: '10px 0' }"></a-divider>
          <div style="margin-bottom: 10px">
            <a-button type="primary" @click="exportRes" :disabled="disDownload" :icon="h(CloudDownloadOutlined)">下载结果 (共 {{ total }} 条)</a-button>
          </div>
          <div class="spin" v-if="showLoading">
            <a-spin tip="加载中……" size="large" />
          </div>
          <div class="search_res" v-else>
            <a-table :columns="showColumns" :data-source="raws" v-model:pagination="pagination" @change="onChange" bordered>
              <template #bodyCell="{ column, record }">
                <template v-if="column.dataIndex === 'text'">
                  <div v-html="record[column.dataIndex]"></div>
                </template>
                <template v-else-if="column.dataIndex === 'lab'">
                  <a-button @click="openMsg(record.msg)">{{ record[column.dataIndex] }}</a-button>
                </template>
              </template>
            </a-table>
          </div>
        </div>
      </a-col>
    </a-row>
    <div style="margin-bottom: 100px"></div>
    <ShowMsg />
  </div>
</template>

<style scoped>
.header-pg {
  margin: 10px 20px;
  display: flex;
  flex-direction: row;
  font-size: large;
  font-weight: bold;
  color: #1677ff;
}

.back {
  cursor: pointer;
}

.back:hover {
  color: #1677ff;
  transform: scale(1.8);
  transition: 0.2s;
}

.spin {
  text-align: center;
}

.search_bar {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
}

ul.ant-menu {
  margin-left: 10px;
  border-radius: 10px;
  box-shadow: 0 2px 8px 0 rgba(2, 24, 42, 0.1);
}

.content {
  padding: 0 30px;
  min-width: none;
}

.ant-table-column-sort {
  background-color: aqua;
}

.search_res {
  box-shadow: 0 2px 8px 0 rgba(2, 24, 42, 0.1);
  border-radius: 10px;
  margin-bottom: 20px;
  background-color: #fafafa;
}
</style>
