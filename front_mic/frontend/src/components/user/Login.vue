<script lang="ts" setup>
import { reactive, computed } from "vue";
import { UserOutlined, LockOutlined } from "@ant-design/icons-vue";
import axios from "axios";
import { showErr } from "../utils";

interface FormState {
  username: string;
  password: string;
  remember: boolean;
}

const formState = reactive<FormState>({
  username: "",
  password: "",
  remember: true,
});

const setCookie = (cname, cvalue, exdays) => {
  var d = new Date();
  d.setTime(d.getTime() + exdays * 24 * 60 * 60 * 1000);
  var expires = "expires=" + d.toGMTString();
  document.cookie = cname + "=" + cvalue + "; " + expires;
};

const set_token = (token: string) => {
  localStorage.setItem("token", token);
  setCookie("session", token, 30);
  window.location.href = "/";
};

const onFinish = (values: any) => {
  let formData = new FormData();
  formData.append("username", values.username);
  formData.append("password", values.password);
  formData.append("remember", String(values.remember));
  axios
    .post("/api/token", formData)
    .then((res) => {
      let data = res.data;
      if (data) {
        let token = data.access_token;
        set_token(token);
      } else {
        showErr("密码或用户名错误");
      }
    })
    .catch((err) => {
      showErr("密码或用户名错误");
    });
};

const onFinishFailed = (errorInfo: any) => {};

const disabled = computed(() => {
  let username = formState.username.trim();
  let password = formState.password.trim();
  if (username.length < 3 || username.length > 16 || /^[a-zA-Z0-9_]+$/.test(username) == false || password.length < 6 || password.length > 16 || /^[a-zA-Z0-9_]+$/.test(password) == false) {
    return true;
  }
  return false;
});
</script>

<template>
  <div id="login">
    <div id="form">
      <a-card :hoverable="true">
        <div id="title">登录</div>
        <a-divider></a-divider>
        <a-form :model="formState" name="normal_login" class="login-form" @finish="onFinish" @finishFailed="onFinishFailed">
          <a-form-item
            label="用户名"
            name="username"
            :rules="[
              { required: true, message: '请输入您的用户名!' },
              { min: 3, message: '密码不能少于3位' },
              { max: 16, message: '密码不能超过16位' },
              { pattern: /^[a-zA-Z0-9_]+$/, message: '密码只能包含字母、数字、下划线' },
            ]"
          >
            <a-input v-model:value="formState.username">
              <template #prefix>
                <UserOutlined class="site-form-item-icon" />
              </template>
            </a-input>
          </a-form-item>

          <a-form-item
            label="密　码"
            name="password"
            :rules="[
              { required: true, message: '请输入您的密码!' },
              { min: 6, message: '密码不能少于6位' },
              { max: 16, message: '密码不能超过16位' },
              { pattern: /^[a-zA-Z0-9_]+$/, message: '密码只能包含字母、数字、下划线' },
            ]"
          >
            <a-input-password v-model:value="formState.password">
              <template #prefix>
                <LockOutlined class="site-form-item-icon" />
              </template>
            </a-input-password>
          </a-form-item>

          <a-form-item>
            <a-form-item name="remember" no-style>
              <a-checkbox v-model:checked="formState.remember">30天内免登录</a-checkbox>
            </a-form-item>
          </a-form-item>

          <a-form-item>
            <a-button :disabled="disabled" type="primary" html-type="submit" class="login-form-button"> 登录 </a-button>
            <span>还没有账号？</span>
            <a-button type="primary" href="#signup">注册</a-button>
          </a-form-item>
        </a-form>
      </a-card>
    </div>
  </div>
</template>

<style scoped>
#login {
  width: 100%;
  height: 100vh;
  background: linear-gradient(217deg, rgba(255, 0, 0, 0.8), rgba(255, 0, 0, 0) 70.71%), linear-gradient(127deg, rgba(0, 255, 0, 0.8), rgba(0, 255, 0, 0) 70.71%), linear-gradient(336deg, rgba(0, 0, 255, 0.8), rgba(0, 0, 255, 0) 70.71%);
  display: flex;
  align-items: center;
  justify-content: center;
}
.login-form {
  width: 600px;
  height: 260px;
}
.login-form-forgot {
  float: right;
}
.login-form-button {
  width: 100%;
  margin-bottom: 20px;
}
#title {
  text-align: center;
  font-weight: bold;
  font-size: large;
}
#form {
  transition: transform 0.3s ease;
}
#form:hover {
  transform: translateY(-10px);
}
</style>
