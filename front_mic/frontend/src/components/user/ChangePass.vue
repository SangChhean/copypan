<script lang="ts" setup>
import { reactive, computed } from "vue";
import { UserOutlined, LockOutlined } from "@ant-design/icons-vue";
import axios from "axios";
import { showErr, showSuccess } from "../utils";

interface FormState {
  username: string;
  old_password: string;
  new_password: string;
}

const formState = reactive<FormState>({
  username: "",
  old_password: "",
  new_password: "",
});

const onFinish = (values: any) => {
  let formData = new FormData();
  formData.append("username", values.username);
  formData.append("old_pass", values.old_password);
  formData.append("new_pass", values.new_password);
  axios
    .post("/api/changePass", formData)
    .then((res) => {
      let data = res.data;
      if (data) {
        if (data.code == "0") showErr(data.msg);
        else showSuccess(data.msg, "/login");
      } else {
        alert("密码或用户名错误");
      }
    })
    .catch((err) => {
      alert("密码或用户名错误");
    });
};

const onFinishFailed = (errorInfo: any) => {};

const disabled = computed(() => {
  let username = formState.username.trim();
  let password = formState.old_password.trim();
  let new_password = formState.new_password.trim();
  if (username.length < 3 || username.length > 16 || /^[a-zA-Z0-9_]+$/.test(username) == false || password.length < 6 || password.length > 16 || /^[a-zA-Z0-9_]+$/.test(password) == false || new_password.length < 6 || new_password.length > 16 || /^[a-zA-Z0-9_]+$/.test(new_password) == false) {
    return true;
  }
  return false;
});
</script>

<template>
  <div id="login">
    <div id="form">
      <a-card :hoverable="true">
        <div id="title">修改密码</div>
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
            label="原密码"
            name="old_password"
            :rules="[
              { required: true, message: '请输入您的原密码!' },
              { min: 6, message: '密码不能少于6位' },
              { max: 16, message: '密码不能超过16位' },
              { pattern: /^[a-zA-Z0-9_]+$/, message: '密码只能包含字母、数字、下划线' },
            ]"
          >
            <a-input-password v-model:value="formState.old_password">
              <template #prefix>
                <LockOutlined class="site-form-item-icon" />
              </template>
            </a-input-password>
          </a-form-item>

          <a-form-item
            label="新密码"
            name="new_password"
            :rules="[
              { required: true, message: '请输入您的新密码!' },
              { min: 6, message: '密码不能少于6位' },
              { max: 16, message: '密码不能超过16位' },
              { pattern: /^[a-zA-Z0-9_]+$/, message: '密码只能包含字母、数字、下划线' },
            ]"
          >
            <a-input-password v-model:value="formState.new_password">
              <template #prefix>
                <LockOutlined class="site-form-item-icon" />
              </template>
            </a-input-password>
          </a-form-item>

          <a-form-item>
            <a-button :disabled="disabled" type="primary" html-type="submit" class="login-form-button"> 提交 </a-button>
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
