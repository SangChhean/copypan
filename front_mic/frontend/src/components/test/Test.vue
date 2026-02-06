<!-- ProgressBar.vue -->
<script setup>
import axios from "axios";
let ws;
// 连接到 WebSocket 服务器
const connectWebSocket = () => {
  ws = new WebSocket("ws://localhost:8000/ws/progress");
  ws.onmessage = function (event) {
    const progressData = JSON.parse(event.data);
    console.log(progressData.progress);
    document.getElementById("progress").innerText = `Progress: ${progressData.progress}%`;
  };
  ws.onclose = function () {
    console.log("WebSocket closed.");
  };
};

// 启动后台进程
const startProcess = async () => {
  connectWebSocket();
  await axios.get("/api/process");
};
</script>

<template>
  <h1>Processing Progress</h1>
  <div id="progress">Waiting for progress...</div>
  <button @click="startProcess()">Start Process</button>
</template>

<style scoped>
progress {
  width: 100%;
  height: 30px;
}
</style>
