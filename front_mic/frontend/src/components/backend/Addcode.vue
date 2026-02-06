<script setup>
import { onMounted, reactive, ref } from "vue";
import useStore from "../../store";
import { storeToRefs } from "pinia";
import axios from "axios";

const MyStore = useStore();
const store = storeToRefs(MyStore);

const roles = ["reader", "editor", "admin"];
const form = reactive({
    code: "请点击生成邀请码",
    role: "reader",
});

const text = ref("");
const ok_text = ref("");
const visible = ref(false);
const addcode = () => {
    if (form.code == "") {
        text.value = "邀请码不能为空";
        ok_text.value = "关 闭";
        visible.value = true;
        return;
    }

    let data = new FormData();
    data.append("code", form.code);
    data.append("role", form.role);

    axios.post("/api/addcode", data).then((res) => {
        let status = res.data.status;
        if (status == "invild") {
            text.value = "您无权添加邀请码";
            ok_text.value = "关 闭";
            visible.value = true;
        } else if (status == "duplicated") {
            text.value = "邀请码已存在";
            ok_text.value = "关 闭";
            visible.value = true;
        } else {
            text.value = "添加成功, 请注册";
            store.is_refresh_code.value = true;
            ok_text.value = "关 闭";
            visible.value = true;
        }
    });
};

const handleOk = () => {
    visible.value = false;
};

const genc = () => {
    axios.get("/api/getrandom").then((res) => {
        form.code = res.data.code;
        navigator.clipboard.writeText(form.code);
    });
};

onMounted(() => {
    axios.get("/api/ght_admin").then((res) => {
        let status = res.data;
        if (status != "t0") window.location.hash = "index";
    });
});
</script>

<template>
    <a-card title="添加邀请码">
        <a-form :model="form">
            <a-form-item field="code" :rules="[{ required: true, message: '邀请码必须填写' }]" :validate-trigger="['change', 'input']">
                <template #label>邀请码 <icon-user /></template>
                <a-alert type="normal" v-text="form.code" />
            </a-form-item>
            <a-form-item field="role">
                <template #label>选角色 <icon-lock /></template>
                <a-select :options="roles" placeholder="请选择角色" v-model="form.role" />
            </a-form-item>
            <a-form-item>
                <a-space>
                    <a-button type="primary" status="success" @click="genc">生成邀请码</a-button>
                    <a-button type="primary" @click="addcode">添加邀请码</a-button>
                </a-space>
            </a-form-item>
        </a-form>
    </a-card>
    <a-modal v-model:visible="visible" @ok="handleOk" hide-cancel simple :align-center="false" :ok-text="ok_text">
        <template #title>
            <h3>{{ text }}</h3>
        </template>
    </a-modal>
</template>

<style scoped>
.arco-input-disabled {
    color: black !important;
}
</style>
