<script setup>
import { useRouter } from 'vue-router'

defineProps({
  title: String,
})

const router = useRouter()

function goBack() {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/')
  }
}
</script>

<template>
  <div class="cn-page-header">
    <button type="button" class="cn-back" @click="goBack">← 返回</button>
    <span class="cn-page-title">{{ title }}</span>
  </div>
</template>
