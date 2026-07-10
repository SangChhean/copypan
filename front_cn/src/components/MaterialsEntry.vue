<template>
  <MaterialsPage v-if="route.query.type" />
  <MaterialsLanding v-else />
</template>

<script setup>
import { useRoute } from 'vue-router'
import MaterialsPage from './MaterialsPage.vue'
import MaterialsLanding from './MaterialsLanding.vue'

const route = useRoute()
</script>
