<script setup>
import { IconCaretRight, IconCaretLeft } from "@arco-design/web-vue/es/icon";
import { ref, onMounted, onBeforeMount } from "vue";
import axios from "axios";
import User from "./User.vue";
import InviteCode from "./InviteCode.vue";
import { useRouter } from "vue-router";

const router = useRouter();

const mkey = ref("1_1");
const onClickMenuItem = (key) => {
  mkey.value = key;
};

const back = (res) => {
  if (!["t0", "t1"].includes(res)) window.location.hash = "index";
};

const show_back = ref(false);
onBeforeMount(() => {
  axios.get("/api/ght_admin").then((res) => {
    let status = res.data;
    back(status);
    status == "t0" ? (show_back.value = true) : (show_back.value = false);
  });
});

const visible = ref(false);
const model_text = ref("");
const okText = ref("确定");
const modelTitle = ref("提示");
const modelWidth = ref({ width: "50%", maxHeight: "80%", overflow: "auto" });
const openModel = (title, text, ok, style) => {
  modelTitle.value = title;
  model_text.value = text;
  okText.value = ok;
  modelWidth.value = style;
  visible.value = true;
};

const msg = ref();
const add_msg = () => {
  let msg_form = new FormData();
  msg_form.append("msg", msg.value);
  axios.post("/api/add_msg", msg_form).then((res) => {
    console.log("add_msg", res.data);
    openModel("提示", res.data, "确定", { width: "50%" });
  });
};

const paras = ref("");
const add_paras = () => {
  let paras_form = new FormData();
  paras_form.append("paras", paras.value);

  axios.post("/api/add_paras", paras_form).then((res) => {
    openModel("提示", res.data, "确定", { width: "50%" });
  });
};

const okHandle = () => {
  if (okText.value == "确认删除") {
    let data = new FormData();
    data.append("id", cid.value);
    axios.post("/api/msg_del", data).then((res) => {
      openModel("提示", res.data, "确定", { width: "50%" });
    });
  } else {
    files.value = [];
  }
};

const cid = ref("");
const delete_msg = () => {
  let data = new FormData();
  data.append("id", cid.value);

  axios.post("/api/get_html_byid", data).then((res) => {
    if (res.data == "0") openModel("提示", "此章内容不存在", "确定", { width: "50%" });
    else openModel("确认删除", res.data, "确认删除", { width: "90%", maxHeight: "80%", overflow: "auto" });
  });
};

const pids = ref("");
const delete_paras = () => {
  let data = new FormData();
  data.append("pids", pids.value);
  axios.post("/api/paras_del", data).then((res) => {
    openModel("提示", res.data, "确定", { width: "50%" });
  });
};

const files = ref([]);
const update_json = (val) => {
  axios.get("/api/update_json").then((res) => {
    openModel("提示", res.data, "确定", { width: "50%" });
  });
};
</script>

<template>
  <a-layout class="layout">
    <a-layout-header>
      <a-space>
        <div class="logo" @click="router.push('/')">Pansearch</div>
        <div style="font-size: large; color: var(--color-text-2)">后台管理面板</div>
      </a-space>
    </a-layout-header>
    <a-layout style="margin-top: 16px">
      <a-layout-sider collapsible breakpoint="xl">
        <a-menu :default-open-keys="['1']" :default-selected-keys="['1_1']" :style="{ width: '100%' }" @menu-item-click="onClickMenuItem">
          <a-sub-menu key="1">
            <template #title>
              <icon-storage />
              数据库管理
            </template>
            <a-menu-item key="1_1">
              <icon-plus-circle-fill />
              新增整篇
            </a-menu-item>
            <a-menu-item key="1_2">
              <icon-plus-circle-fill />
              新增批量
            </a-menu-item>
            <a-menu-item key="1_3">
              <icon-close-circle-fill />
              删除整篇
            </a-menu-item>
            <a-menu-item key="1_4">
              <icon-close-circle-fill />
              删除批量
            </a-menu-item>
            <a-menu-item key="1_5">
              <icon-close-circle-fill />
              上传JSON
            </a-menu-item>
          </a-sub-menu>
          <a-menu-item key="2" v-if="show_back">
            <template #icon><icon-user /></template>
            用户管理
          </a-menu-item>
          <a-menu-item key="3" v-if="show_back">
            <template #icon><icon-safe /></template>
            邀请码管理
          </a-menu-item>
        </a-menu>
        <!-- trigger -->
        <template #trigger="{ collapsed }">
          <IconCaretRight v-if="collapsed"></IconCaretRight>
          <IconCaretLeft v-else></IconCaretLeft>
        </template>
      </a-layout-sider>
      <a-layout>
        <a-layout style="padding: 0 16px">
          <a-layout-content>
            <a-scrollbar style="height: 90vh; overflow: auto">
              <div style="padding: 1em" v-if="mkey == '1_1'">
                <h3>新增内容（整篇）</h3>
                <a-divider />
                <a-textarea
                  v-model:model-value="msg"
                  placeholder="请输入内容"
                  :auto-size="{
                    minRows: 7,
                    maxRows: 20,
                  }"
                />
                <div style="margin-top: 20px"></div>
                <!-- options -->
                <a-space>
                  <a-button type="primary" @click="add_msg">整篇添加</a-button>
                </a-space>
                <a-divider></a-divider>
                <pre>
{
    "meta": {
        "book_id": "ls_1",
        "chapter_id": "ls_1#151",
        "book_name_zh": "创世记生命读经",
        "book_name_en": "Life-study of Genesis",
        "chapter_name_zh": "第一百五十一篇　创世记—总纲与中心思想（测试数据）",
        "chapter_name_en": "Message 151 Genesis—the General Sketch and Central Thought (Test Data)",
        "source_zh": "创世记生命读经，第一百五十一篇（测试数据）",
        "source_en": "Life-study of Genesis, msg. 1 (Test Data)"
    },
    "contents": [
        {
            "chinese": "（测试数据）第一百五十一篇　创世记—总纲与中心思想",
            "english": "(Test Data) Message 151 Genesis—the General Sketch and Central Thought",
            "type": "title",
            "id": "pan_ls-ls_1#151_1"
        },
        {
            "chinese": "（测试数据）我们为着圣经赞美主！",
            "english": "(Test Data) Praise the Lord for the Bible!",
            "type": "text",
            "id": "pan_ls-ls_1#151_2"
        },
        {
            "chinese": "（测试数据）一本奇妙的书",
            "english": "(Test Data) A wonderful book",
            "type": "heading",
            "id": "pan_ls-ls_1#151_3"
        }
    ]
}
                                </pre
                >
              </div>
              <div style="padding: 1em" v-if="mkey == '1_2'">
                <h3>新增/修改段落（批量）</h3>
                <a-divider />
                <a-textarea
                  v-model:model-value="paras"
                  placeholder="请输入内容"
                  :auto-size="{
                    minRows: 7,
                    maxRows: 20,
                  }"
                />
                <div style="margin-top: 20px"></div>
                <!-- options -->
                <a-space>
                  <a-button type="primary" @click="add_paras">批量添加</a-button>
                </a-space>
                <a-divider></a-divider>
                <pre>
[
    {
        "book_id": "ls_1",
        "chapter_id": "ls_1#151",
        "book_name_zh": "创世记生命读经",
        "book_name_en": "Life-study of Genesis",
        "chapter_name_zh": "第一百五十一篇　创世记—总纲与中心思想（测试数据）",
        "chapter_name_en": "Message 151 Genesis—the General Sketch and Central Thought (Test Data)",
        "source_zh": "创世记生命读经，第一百五十一篇（测试数据）",
        "source_en": "Life-study of Genesis, msg. 1 (Test Data)",
        "zh": "（测试数据）圣经是一本奇妙的书，它是书中之书，历经一千六百年才完成，开始于神最大的申言者摩西，结束于使徒约翰。",
        "en": "(Test Data) The Bible is a wonderful book. It is \"The Book\" among all books! It took 1600 years to complete, starting with Moses, the greatest prophet of God, and ending with the Apostle John. ",
        "type": "text",
        "para_id": "pan_ls-ls_1#151_4",
        "para_num": "4"

    },
    {
        "book_id": "ls_1",
        "chapter_id": "ls_1#151",
        "book_name_zh": "创世记生命读经",
        "book_name_en": "Life-study of Genesis",
        "chapter_name_zh": "第一百五十一篇　创世记—总纲与中心思想（测试数据）",
        "chapter_name_en": "Message 151 Genesis—the General Sketch and Central Thought (Test Data)",
        "source_zh": "创世记生命读经，第一百五十一篇（测试数据）",
        "source_en": "Life-study of Genesis, msg. 1 (Test Data)",
        "zh": "（测试数据）接下去，在改教时，神用路德马丁解开圣经的锁禁。同时印刷术也发明了，使圣经得以印刷出版。",
        "en": "(Test Data) Then, in the Reformation, God used Martin Luther to unlock the Bible. At the same time, printing was invented, allowing the Bible to be printed. ",
        "type": "text",
        "para_id": "pan_ls-ls_1#151_5",
        "para_num": "5"
    }
]
                                </pre
                >
              </div>
              <div style="padding: 1em" v-if="mkey == '1_3'">
                <h3>删除内容（整篇）</h3>
                <a-divider />
                <a-space>
                  <a-input placeholder="请输入篇章序列" v-model:model-value="cid" />
                  <a-button type="primary" @click="delete_msg">删除</a-button>
                </a-space>
              </div>
              <div style="padding: 1em" v-if="mkey == '1_4'">
                <h3>删除内容（批量）</h3>
                <a-divider />
                <a-textarea
                  placeholder="请输入段落序列"
                  v-model:model-value="pids"
                  :auto-size="{
                    minRows: 7,
                    maxRows: 20,
                  }"
                />
                <div style="margin-top: 20px"></div>
                <a-button type="primary" @click="delete_paras">删除</a-button>
                <a-divider />
                <pre>
[
    {
        "chapter_id": "ls_1#151",
        "pids":["pan_ls-ls_1#151_1", "pan_ls-ls_1#151_2", "pan_ls-ls_1#151_3", "pan_ls-ls_1#151_4", "pan_ls-ls_1#151_5"]
    },
    {
        "chapter_id": "ls_1#152",
        "pids":["pan_ls-ls_1#152_18"] 
    }
]
                                </pre
                >
              </div>
              <div style="padding: 1em" v-if="mkey == '1_5'">
                <h3>上传JSON文档</h3>
                <a-divider />
                <a-upload action="/api/upload_json" accept=".json" :limit="1" v-model:file-list="files" />
                <div style="margin-top: 20px"></div>
                <a-divider />
                <a-button type="primary" @click="update_json">更新</a-button>
              </div>
              <div style="padding: 1em" v-if="mkey == '2'">
                <User />
              </div>
              <div style="padding: 1em" v-if="mkey == '3'">
                <InviteCode />
              </div>
            </a-scrollbar>
          </a-layout-content>
        </a-layout>
      </a-layout>
    </a-layout>
  </a-layout>
  <div style="max-height: 80%; overflow-y: auto">
    <a-modal v-model:visible="visible" :ok-text="okText" @ok="okHandle" :modal-style="modelWidth" :align-center="false" :top="70">
      <template #title>{{ modelTitle }}</template>
      <div v-html="model_text" />
    </a-modal>
  </div>
</template>

<style scoped>
p {
  color: var(--color-text-2);
}

.layout {
  height: 99.8vh;
  background: var(--color-fill-2);
  border: 1px solid var(--color-border);
}
.layout :deep(.arco-layout-sider) .logo {
  height: 32px;
  margin: 12px 8px;
  background: rgba(255, 255, 255, 0.2);
}
.layout :deep(.arco-layout-header) .logo {
  cursor: pointer;
  background: #3f9dfd;
  font-family: "pans";
  font-size: xx-large;
  color: whitesmoke;
  /* text-align: center; */
  line-height: 32px;
  padding: 10px 10px 0px 10px;
  margin-left: 22px;
  border-radius: 5px;
}
.layout :deep(.arco-layout-header) {
  height: 64px;
  line-height: 64px;
  background: var(--color-bg-3);
}
.layout :deep(.arco-layout-footer) {
  height: 48px;
  color: var(--color-text-2) !important;
  font-weight: 400;
  font-size: 14px;
  line-height: 48px;
}
.layout :deep(.arco-layout-content) {
  color: var(--color-text-2) !important;
  font-weight: 400;
  font-size: 14px;
  background: var(--color-bg-3);
}
.layout :deep(.arco-layout-footer),
.layout :deep(.arco-layout-content) {
  display: flex;
  flex-direction: column;
  justify-content: center;
  /* color: var(--color-white); */
  font-size: 16px;
  font-stretch: condensed;
  /* text-align: center; */
}
pre {
  color: darkgrey;
}
</style>
