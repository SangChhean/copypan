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
  {
    path: "/enhanced-translate",
    component: () =>
      import("@testd/components/EnhancedTranslate.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/outline-translate-test",
    name: "OutlineTranslateTest",
    component: () => import("../components/toolbox/OutlineTranslateTest.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/test-translate-vannak",
    component: () => import("../components/toolbox/TranslateTest.vue"),
  },
  {
    path: "/zh-convert-test",
    name: "ZhConvertTest",
    component: () => import("../components/toolbox/ZhConvertTest.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/zh2tw-vannak",
    component: () => import("../components/toolbox/ZhConvert2.vue"),
  },
  {
    path: "/zh-convert",
    component: () => import("../components/toolbox/ZhConvert.vue"),
  },
  {
    path: "/article-polish",
    component: () => import("../components/toolbox/ArticlePolish.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/rough-outline",
    component: () => import("../components/toolbox/RoughOutline.vue"),
  },
  {
    path: "/feast-outline",
    component: () => import("../components/toolbox/FeastOutline.vue"),
  },
  {
    path: "/ministerialize-outline",
    name: "MinisterializeOutline",
    component: () => import("../components/toolbox/MinisterializeOutline.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/bird-view-outline",
    component: () => import("../components/toolbox/BirdViewOutline.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/feast-outline-maker",
    component: () => import("../components/toolbox/FeastOutlineMaker.vue"),
    meta: { requiresAuth: true },
  },
  { path: "/roundtable", component: () => import("../components/toolbox/RoundTable.vue") },
  { path: "/roundtable/:id", component: () => import("../components/toolbox/RoundTableDetail.vue") },
  {
    path: "/kg-rag-test",
    name: "KgRagTest",
    component: () => import("../components/toolbox/KgRagTest.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: '/practice-translate',
    component: () => import('../../../../testC/translate/frontend/OutlineTranslate_practice.vue')
  },
  {
    path: '/zh2tw-practice',
    component: () => import('../../../../testC/zh2tw/frontend/src/components/ZhConvert.vue')
  },
  {
    path: '/testb-zh2tw',
    component: () => import('../../../../test_B/zh2tw/frontend/src/components/ZhConvert.vue')
  },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

export default router;
