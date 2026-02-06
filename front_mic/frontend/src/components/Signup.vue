<script setup>
import { onMounted, reactive, ref } from "vue";
import axios from "axios";

const form = reactive({
    name: "",
    post: "",
    post2: "",
    code: "",
});

const text = ref("");
const ok_text = ref("");
const visible = ref(false);
const signup = () => {
    if (form.name == "" || form.post == "" || form.post2 == "" || form.code == "") {
        return;
    } else if (form.post != form.post2) {
        text.value = "两次密码不一致，请重新输入";
        ok_text.value = "关 闭";
        visible.value = true;
        return;
    }

    let data = new FormData();
    data.append("name", form.name);
    data.append("pass", form.post);
    data.append("code", form.code);

    axios.post("/api/signup", data).then((res) => {
        let status = res.data.status;
        if (status == "invild") {
            text.value = "邀请码无效，请联系管理员";
            ok_text.value = "关 闭";
            visible.value = true;
        } else if (status == "success") {
            text.value = "注册成功, 请登录";
            ok_text.value = "登 录";
            visible.value = true;
        } else {
            text.value = "用户名或密码包含特殊符号，请重新输入";
            ok_text.value = "登 录";
            visible.value = true;
        }
    });
};

const handleOk = () => {
    visible.value = false;
    if (ok_text.value == "登 录") {
        window.location.hash = "login";
    }
};

onMounted(() => {});
</script>

<template>
    <div class="login">
        <a-card class="card-demo" title="Sign Up" hoverable>
            <template #extra>
                <a-link href="#login">Sign In</a-link>
            </template>
            <a-form :model="form">
                <a-form-item
                    field="name"
                    :rules="[
                        { required: true, message: '用户名必须填写' },
                        { minLength: 5, message: '用户名必须不少于 5 个字符' },
                    ]"
                    :validate-trigger="['change', 'input']"
                >
                    <template #label>用户名 <icon-user /></template>
                    <a-input v-model="form.name" placeholder="请输入用户名" />
                </a-form-item>
                <a-form-item
                    field="post"
                    label="Password"
                    :rules="[
                        { required: true, message: '密码必须填写' },
                        { minLength: 8, message: '密码必须不少于 8 个字符' },
                    ]"
                    :validate-trigger="['change', 'input']"
                >
                    <template #label>密　码 <icon-lock /></template>
                    <a-input-password v-model="form.post" placeholder="请输入密码" />
                </a-form-item>
                <a-form-item
                    field="post2"
                    label="Password2"
                    :rules="[
                        { required: true, message: '密码必须填写' },
                        { minLength: 8, message: '密码必须不少于 8 个字符' },
                    ]"
                    :validate-trigger="['change', 'input']"
                >
                    <template #label>密　码 <icon-lock /></template>
                    <a-input-password v-model="form.post2" placeholder="请再次输入密码" />
                </a-form-item>
                <a-form-item field="code" :rules="[{ required: true, message: '邀请码必须填写' }]" :validate-trigger="['change', 'input']">
                    <template #label>邀请码 <icon-code-square /></template>
                    <a-input v-model="form.code" placeholder="请输入邀请码" />
                </a-form-item>
                <a-form-item>
                    <a-button type="primary" @click="signup">注册</a-button>
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
    background: linear-gradient(30deg, #ec12cf 0%, #0debb3 100%);
}
</style>
