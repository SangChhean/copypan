import { createRouter, createWebHashHistory } from "vue-router";
import MainView from "../components/MainView.vue";

const routes = [{ path: "/", name: "main", component: MainView }];

export default createRouter({
  history: createWebHashHistory(),
  routes,
});
