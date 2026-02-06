<script setup>
import { onMounted, reactive, ref } from "vue";
import axios from "axios";

const form = reactive({
    username: "",
    password: "",
    newpass: "",
    newpass2: "",
});

const visible = ref(false);
const text = ref("");
const ok_text = ref("关 闭");
const change = () => {
    if (form.username == "" || form.password == "") {
        return;
    } else if (form.newpass != form.newpass2) {
        text.value = "两次输入的密码不一致";
        visible.value = true;
        return;
    }

    let data = new FormData();
    data.append("name", form.username);
    data.append("pass", form.password);
    data.append("newpass", form.newpass);

    axios.post("/api/changepass", data).then((res) => {
        let status = res.data.status;
        if (status == "invalid") {
            text.value = "用户名或密码不正确";
            visible.value = true;
        } else if (status == "ok") {
            text.value = "密码修改成功, 请重新登录";
            ok_text.value = "重新登录";
            visible.value = true;
        }
    });
};

const handleOk = () => {
    visible.value = false;
    if (text.value == "密码修改成功, 请重新登录") {
        window.location.hash = "login";
    }
};

onMounted(() => {});
</script>

<template>
    <div class="login">
        <a-card class="card-demo" title="Change Password" hoverable>
            <template #extra>
                <a-link href="#login">Sign In</a-link>
            </template>
            <a-form :model="form">
                <a-form-item field="username" label="Username" :rules="[{ required: true, message: '用户名必须填写' }]" :validate-trigger="['change', 'input']">
                    <template #label>用户名 <icon-user /></template>
                    <a-input v-model="form.username" placeholder="请输入用户名" />
                </a-form-item>
                <a-form-item field="password" label="Password" :rules="[{ required: true, message: '密码必须填写' }]" :validate-trigger="['change', 'input']">
                    <template #label>旧密码 <icon-lock /></template>
                    <a-input-password v-model="form.password" placeholder="请输入密码" />
                </a-form-item>
                <a-form-item
                    field="newpass"
                    label="newpass"
                    :rules="[
                        { required: true, message: '密码必须填写' },
                        { minLength: 8, message: '密码必须不少于 8 个字符' },
                    ]"
                    :validate-trigger="['change', 'input']"
                >
                    <template #label>新密码 <icon-lock /></template>
                    <a-input-password v-model="form.newpass" placeholder="请输入密码" />
                </a-form-item>
                <a-form-item
                    field="newpass2"
                    label="newpass2"
                    :rules="[
                        { required: true, message: '密码必须填写' },
                        { minLength: 8, message: '密码必须不少于 8 个字符' },
                    ]"
                    :validate-trigger="['change', 'input']"
                >
                    <template #label>新密码 <icon-lock /></template>
                    <a-input-password v-model="form.newpass2" placeholder="请输入密码" />
                </a-form-item>
                <a-form-item>
                    <a-button type="primary" @click="change">修改</a-button>
                </a-form-item>
            </a-form>
        </a-card>
    </div>
    <a-modal v-model:visible="visible" @ok="handleOk" hide-cancel simple :align-center="false" :ok-text="ok_text">
        <template #title>
            <h3>{{ text }}</h3>
        </template>
    </a-modal>
</template>

<style scoped>
.card-demo {
    width: 80%;
    height: 60%;
    max-width: 500px;
    max-height: 400px;
    transition-property: all;
    margin-bottom: 30vh;
}
.card-demo:hover {
    transform: translateY(-4px);
}

.login {
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100vh;
    /* 渐变背景色 */
    background: linear-gradient(30deg, #0debb3 0%, #ec12cf 100%);
}
</style>
