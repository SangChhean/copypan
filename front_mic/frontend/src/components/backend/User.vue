<script setup>
import { onMounted } from "vue";
import { reactive, ref } from "vue";
import axios from "axios";

const api = axios.create({
    baseURL: "api/",
    headers: {
        "Content-Type": "application/json",
    },
});

const back = (r) => {
    if (r.data == "login") window.location.hash = "index";
};

const get_users = () => {
    // 初始化 data
    data.splice(0, data.length);
    api.get("get_users").then((res) => {
        back(res);
        for (let i = 0; i < res.data.length; i++) {
            let user = res.data[i].username;
            let role = res.data[i].role;
            if (role == "reader") role = "订阅者";
            else if (role == "writer" || role == "editor") role = "编辑";
            else if (role == "admin") role = "管理员";

            data.push({
                key: i.toString(),
                username: user,
                role: role,
            });
        }
    });
};

const deleteUser = (delete_username) => {
    let queryData = new FormData();
    queryData.append("username", delete_username);

    api.post("user_del", queryData).then((res) => {
        back(res);
        get_users();
    });
};

const user_update = (username, role) => {
    let data = new FormData();
    data.append("username", username);
    data.append("role", role);

    api.post("role_update", data).then((res) => {
        if (res.data == "1") modelText.value = "修改成功";
        else modelText.value = res.data;
        visible.value = true;
        get_users();
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
        user_update(data[rowIndex].username, role);
    }
};

onMounted(() => {
    get_users();
});

const data = reactive([]);
const options = ["订阅者", "编辑", "管理员"];
const columns = [
    {
        title: "用户名",
        dataIndex: "username",
        slotName: "username",
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
    delete_username.value = "";
};

const delete_username = ref("");
const deleteConfirm = (rowIndex) => {
    modalTitle.value = "删除用户";
    okText.value = "确认删除";
    delete_username.value = data[rowIndex].username;
    showModal("确定删除用户 " + data[rowIndex].username + " 吗？");
};

const modalOK = () => {
    if (modalTitle.value == "删除用户") deleteUser(delete_username.value);
    reset_modal();
};
</script>

<template>
    <h3>用户管理</h3>
    <a-divider />
    <a-table :columns="columns" :data="data" :pagination="false" table-layout-fixed>
        <template #username="{ rowIndex }">
            <div v-text="data[rowIndex].username" />
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
            </a-space>
        </template>
    </a-table>
    <a-modal :title="modalTitle" v-model:visible="visible" :okText="okText" @ok="modalOK" @cancel="reset_modal">
        <div>
            {{ modelText }}
        </div>
    </a-modal>
</template>
