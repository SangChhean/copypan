<script setup>
import { onMounted, reactive, ref } from "vue";
import axios from "axios";

const form = reactive({
  username: "",
  password: "",
});

const visible = ref(false);
const signin = () => {
  if (form.username == "" || form.password == "") {
    return;
  }

  let data = new FormData();
  data.append("name", form.username);
  data.append("pass", form.password);

  axios.post("/api/login", data).then(res => {
    let status = res.data.status;
    if (status == "login") {
      visible.value = true;
    } else window.location.hash = "";
  });
};

onMounted(() => {
  console.log("login_mounted");
});
</script>

<template>
  <div class="login">
    <a-card class="card-demo" title="Sign In" hoverable>
      <template #extra>
        <a-link href="#signup">Sign Up</a-link>
      </template>
      <a-form :model="form">
        <a-form-item field="username" label="Username" :rules="[{ required: true, message: '用户名必须填写' }]" :validate-trigger="['change', 'input']">
          <template #label>
            用户名
            <icon-user />
          </template>
          <a-input v-model="form.username" placeholder="请输入用户名" />
        </a-form-item>
        <a-form-item field="password" label="Password" :rules="[{ required: true, message: '密码必须填写' }]" :validate-trigger="['change', 'input']">
          <template #label>
            密　码
            <icon-lock />
          </template>
          <a-input-password v-model="form.password" placeholder="请输入密码" />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" @click="signin">登录</a-button>
        </a-form-item>
      </a-form>
    </a-card>
  </div>
  <a-modal v-model:visible="visible" @ok="handleOk" hide-cancel simple :align-center="false" ok-text="关闭">
    <template #title><h3>用户名或密码不正确</h3></template>
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
