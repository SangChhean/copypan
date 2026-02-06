<script setup>
import { onMounted } from "vue";
import { reactive, ref } from "vue";
import useStore from "../../store";
import { storeToRefs } from "pinia";
import axios from "axios";
import AddCode from "./Addcode.vue";
import { watch } from "vue";

const MyStore = useStore();
const store = storeToRefs(MyStore);

watch(store.is_refresh_code, (newVal, oldVal) => {
    if (newVal) {
        get_codes();
        store.is_refresh_code.value = false;
    }
});

const api = axios.create({
    baseURL: "api/",
    headers: {
        "Content-Type": "application/json",
    },
});

const back = (r) => {
    if (r.data == "login") window.location.hash = "index";
};

const get_codes = () => {
    // 初始化 data
    data.splice(0, data.length);


    api.get("get_invCodes").then((res) => {
        for (let i = 0; i < res.data.length; i++) {
            let code = res.data[i].code;
            let role = res.data[i].role;
            if (role == "reader") role = "订阅者";
            else if (role == "writer" || role == "editor") role = "编辑";
            else if (role == "admin") role = "管理员";

            data.push({
                key: i.toString(),
                code: code,
                role: role,
            });
        }
    });
};

const deleteCode = (delete_code) => {
    let queryData = new FormData();
    queryData.append("code", delete_code);

    api.post("delete_code", queryData).then((res) => {
        back(res);
        get_codes();
    });
};

const code_update = (code, role) => {
    let data = new FormData();
    data.append("code", code);
    data.append("role", role);

    api.post("code_update", data).then((res) => {
        if (res.data == "1") modelText.value = "修改成功";
        else modelText.value = res.data;
        visible.value = true;
        get_codes();
    });
};

const status = ref([]);
const confirmEdit = (rowIndex) => {
    if (status.value.includes(rowIndex)) {
        status.value.splice(status.value.indexOf(rowIndex), 1);
        let role = data[rowIndex].role;
        if (role == "订阅者") role = "2";
        else if (role == "编辑") role = "1";
        else if (role == "管理员") role = "0";
        code_update(data[rowIndex].code, role);
    }
};

onMounted(() => {
    get_codes();
});

const data = reactive([]);
const options = ["订阅者", "编辑", "管理员"];
const columns = [
    {
        title: "邀请码",
        dataIndex: "code",
        slotName: "code",
    },
    {
        title: "角色",
        dataIndex: "role",
        slotName: "role",
    },
    {
        title: "操作",
        dataIndex: "opre",
        slotName: "opre",
    },
];

const onEdit = (rowIndex) => {
    if (!status.value.includes(rowIndex)) {
        status.value.push(rowIndex);
    }
};

const visible = ref(false);
const modelText = ref("");
const modalTitle = ref("提示");
const okText = ref("确定");
const showModal = (text) => {
    modelText.value = text;
    visible.value = true;
};

const reset_modal = () => {
    modalTitle.value = "提示";
    okText.value = "确定";
    visible.value = false;
    delete_code.value = "";
};

const delete_code = ref("");
const deleteConfirm = (rowIndex) => {
    modalTitle.value = "删除邀请码";
    okText.value = "确认删除";
    delete_code.value = data[rowIndex].code;
    showModal("确定删除邀请码 " + data[rowIndex].code + " 吗？");
};

const modalOK = () => {
    if (modalTitle.value == "删除邀请码") deleteCode(delete_code.value);
    reset_modal();
};

const copied = ref([]);
const copy = (rowIndex) => {
    navigator.clipboard.writeText(data[rowIndex].code);
    copied.value.push(rowIndex);
    setTimeout(() => {
        copied.value.splice(copied.value.indexOf(rowIndex), 1);
    }, 1000);
};
</script>

<template>
    <h3>邀请码管理</h3>
    <a-divider />
    <AddCode />
    <a-divider />
    <a-table :columns="columns" :data="data" :pagination="false" table-layout-fixed>
        <template #code="{ rowIndex }">
            <div v-text="data[rowIndex].code" />
        </template>
        <template #role="{ rowIndex }">
            <a-select v-model="data[rowIndex].role" v-if="status.includes(rowIndex)">
                <a-option v-for="value in options">{{ value }}</a-option>
            </a-select>
            <div v-text="data[rowIndex].role" v-else />
        </template>
        <template #opre="{ rowIndex }">
            <a-space>
                <a-button @click="confirmEdit(rowIndex)" v-if="status.includes(rowIndex)"
                    type="primary"><icon-check /></a-button>
                <a-button @click="onEdit(rowIndex)" v-else><icon-edit /></a-button>
                <a-button @click="deleteConfirm(rowIndex)"><icon-delete /></a-button>
                <a-button @click="copy(rowIndex)" type="primary" v-if="copied.includes(rowIndex)">
                    <icon-check />
                </a-button>
                <a-button @click="copy(rowIndex)" v-else>
                    <icon-copy />
                </a-button>
            </a-space>
        </template>
    </a-table>
    <a-modal :title="modalTitle" v-model:visible="visible" :okText="okText" @ok="modalOK" @cancel="reset_modal">
        <div>
            {{ modelText }}
        </div>
    </a-modal>
</template>
