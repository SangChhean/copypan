<script setup>
import { storeToRefs } from "pinia";
import { useStore } from "../store/index";
import { checkSession } from "./utils";
import Header from "./Header.vue";
import Search from "./Search.vue";

const { showIndex } = storeToRefs(useStore());
checkSession();
</script>
<template>
  <div v-if="showIndex">
    <Header />
    <Search />
  </div>
</template>
<style scoped></style>
