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
    component: () => import("@/features/bible_co/BibleCo.vue"),
  },
  {
    path: "/cws",
    component: () => import("../components/toolbox/Cwws.vue"),
  },
  {
    path: "/info-retrieval",
    component: () => import("@/features/info_retrieval/InfoRetrieval.vue"),
  },
  {
    path: "/outline-translate",
    component: () => import("@/features/outline_translate/OutlineTranslate.vue"),
  },
  {
    path: "/enhanced-translate-official",
    component: () => import("@/features/enhanced_translate/EnhancedTranslate.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/progress-outline",
    component: () => import("@/features/progress_outline/ProgressOutline.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/es-claude-test",
    component: () => import("@/features/es_claude_test/EsClaudeTest.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/zh-convert",
    component: () => import("@/features/zh_convert/ZhConvert.vue"),
  },
  {
    path: "/article-polish",
    component: () => import("@/features/article_polish/ArticlePolish.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/rough-outline",
    component: () => import("@/features/rough_outline/RoughOutline.vue"),
  },
  {
    path: "/feast-outline",
    component: () => import("@/features/feast_outline/FeastOutline.vue"),
  },
  {
    path: "/ministerialize-outline",
    name: "MinisterializeOutline",
    component: () => import("@/features/outline_translate/MinisterializeOutline.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/bird-view-outline",
    component: () => import("@/features/outline_translate/BirdViewOutline.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/feast-outline-maker",
    component: () => import("@/features/feast_outline_maker/FeastOutlineMaker.vue"),
    meta: { requiresAuth: true },
  },
  { path: "/roundtable", component: () => import("@/features/roundtable/RoundTable.vue") },
  { path: "/roundtable/:id", component: () => import("@/features/roundtable/RoundTableDetail.vue") },
  {
    path: "/kg-rag-test",
    name: "KgRagTest",
    component: () => import("../components/toolbox/KgRagTest.vue"),
    meta: { requiresAuth: true },
  },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

export default router;
