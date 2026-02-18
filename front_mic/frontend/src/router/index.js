import { createRouter, createWebHashHistory } from "vue-router";

const routes = [
  {
    path: "/",
    component: () => import("../components/Index.vue"),
  },
  {
    path: "/login",
    component: () => import("../components/user/Login.vue"),
  },
  {
    path: "/signup",
    component: () => import("../components/user/Signup.vue"),
  },
  {
    path: "/forgot",
    component: () => import("../components/user/Forgot.vue"),
  },
  {
    path: "/changepass",
    component: () => import("../components/user/ChangePass.vue"),
  },
  {
    path: "/manage",
    component: () => import("../components/management/ManaIndex.vue"),
  },
  {
    path: "/test",
    component: () => import("../components/test/Test.vue"),
  },
  {
    path: "/pg403",
    component: () => import("../components/status/Pg403.vue"),
  },
  {
    path: "/tools",
    component: () => import("../components/toolbox/ToolBox.vue"),
  },
  {
    path: "/bibco",
    component: () => import("../components/toolbox/BibleCo.vue"),
  },
  {
    path: "/cws",
    component: () => import("../components/toolbox/Cwws.vue"),
  },
  {
    path: "/info-retrieval",
    component: () => import("../components/toolbox/InfoRetrieval.vue"),
  },
  {
    path: "/outline-translate",
    component: () => import("../components/toolbox/OutlineTranslate.vue"),
  },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

export default router;
