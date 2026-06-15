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
    path: "/enhanced-translate",
    component: () =>
      import("@testd/components/EnhancedTranslate.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/enhanced-translate-official",
    component: () => import("@/features/enhanced_translate/EnhancedTranslate.vue"),
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
    path: "/generate-outline-vannak",
    component: () => import("@/components/toolbox/GenerateOutline.vue"),
  },
  {
    path: "/article-polish-vannak",
    component: () => import("@/components/toolbox/ArticlePolishA.vue"),
  },
  {
    path: "/feast-outline-a",
    component: () => import("@/components/toolbox/FeastOutlineA.vue"),
  },
  {
    path: "/bird-view-a",
    component: () => import("@/components/toolbox/BirdViewA.vue"),
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
  {
    path: '/practice-translate',
    component: () => import('../../../../testC/translate/frontend/OutlineTranslate_practice.vue')
  },
  {
    path: '/zh2tw-practice',
    component: () => import('../../../../testC/zh2tw/frontend/src/components/ZhConvert.vue')
  },
  {
    path: '/practice-kg-rag',
    component: () => import('../components/toolbox/KgRagPractice.vue'),
  },
  {
    path: '/testb-zh2tw',
    component: () => import('../../../../test_B/zh2tw/frontend/src/components/ZhConvert.vue')
  },
  {
    path: '/panai2-test',
    component: () => import('../components/toolbox/PanAI2Test.vue')
  },
  {
    path: '/article-polish-c',
    component: () => import('../components/toolbox/ArticlePolishTestC.vue'),
  },
  {
    path: '/article-polish-b',
    component: () => import('../components/toolbox/ArticlePolishB.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/article-polish-hub',
    component: () => import('../components/toolbox/ArticlePolishHub.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/bird-view-c',
    component: () => import('../components/toolbox/BirdViewC.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/bird-view-b',
    component: () => import('../components/toolbox/BirdViewB.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/feast-outline-b',
    component: () => import('../components/toolbox/FeastOutlineB.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/feast-outline-c',
     component: () => import('../components/toolbox/FeastOutlineC.vue'),
     meta: { requiresAuth: true },
},
  {
    path: '/rough-outline-c',
     component: () => import('../components/toolbox/RoughOutlineC.vue'),
     meta: { requiresAuth: true },
  },
  {
    path: '/rough-outline-b',
     component: () => import('../components/toolbox/RoughOutlineB.vue'),
     meta: { requiresAuth: true },
},
  {
    path: '/ministerialize-b',
     component: () => import('../components/toolbox/MinisterializeB.vue'),
     meta: { requiresAuth: true },
  },
  {
    path: '/ministry-qa-b',
    component: () => import('../components/toolbox/MinistryQaB.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/enhanced-translate-b',
    component: () => import('../components/toolbox/EnhancedTranslateB.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/rough-outline-a',
     component: () => import('../components/toolbox/RoughOutlineA.vue'),
     meta: { requiresAuth: true },
  },
  {
    path: '/ministerialize-a',
     component: () => import('../components/toolbox/MinisterializeA.vue'),
     meta: { requiresAuth: true },
  },
  {
    path: '/qa-simple-a',
    component: () => import('../components/toolbox/QaSimpleA.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/enhanced-translate-a',
    component: () => import('../components/toolbox/EnhancedTranslateA.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/ministerialize-c',
    component: () => import('../components/toolbox/MinisterializeC.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/qa-practice-c',
    component: () => import('../components/toolbox/QaPracticeC.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/enhanced-translate-c',
    component: () => import('../components/toolbox/EnhancedTranslateC.vue'),
    meta: { requiresAuth: true },
},
    {
        path: '/bible-co-c',
        component: () => import('../components/toolbox/BibleCoC.vue'),
        meta: { requiresAuth: true },
    },
    {
        path: '/bible-co-a',
        component: () => import('../components/toolbox/BibleCoA.vue'),
        meta: { requiresAuth: true },
    },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

export default router;
