<script lang="ts" setup>
import { reactive, computed } from "vue";
import { UserOutlined, LockOutlined } from "@ant-design/icons-vue";
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

const onFinish = (values: any) => {};

const onFinishFailed = (errorInfo: any) => {};

const disabled = computed(() => {
  return !(formState.username && formState.password);
});
</script>

<template>
  <div id="login">
    <div>
      <a-card :hoverable="true">
        <div id="title">忘记密码</div>
        <a-divider></a-divider>
        <a-form :model="formState" name="normal_login" class="login-form" @finish="onFinish" @finishFailed="onFinishFailed">
          <a-form-item label="用户名" name="username" :rules="[{ required: true, message: '请输入您的用户名!' }]">
            <a-input v-model:value="formState.username">
              <template #prefix>
                <UserOutlined class="site-form-item-icon" />
              </template>
            </a-input>
          </a-form-item>

          <a-form-item label="密　钥" name="password" :rules="[{ required: true, message: '请输入您的密码!' }]">
            <a-input-password v-model:value="formState.key">
              <template #prefix>
                <LockOutlined class="site-form-item-icon" />
              </template>
            </a-input-password>
          </a-form-item>

          <a-form-item label="新密码" name="password" :rules="[{ required: true, message: '请输入您的密码!' }]">
            <a-input-password v-model:value="formState.password" :maxlength="16">
              <template #prefix>
                <LockOutlined class="site-form-item-icon" />
              </template>
            </a-input-password>
          </a-form-item>

          <a-form-item>
            <a-button :disabled="disabled" type="primary" html-type="submit" class="login-form-button"> 重置密码 </a-button>
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
  height: 210px;
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
</style>
