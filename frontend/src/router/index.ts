/**
 * Vue Router 配置 — 简化版,2 个路由够 demo。
 */

import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";

import HomeView from "../views/HomeView.vue";
import ScreenplayEditorView from "../views/ScreenplayEditorView.vue";

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    name: "home",
    component: HomeView,
  },
  {
    path: "/novels/:id/editor",
    name: "screenplay-editor",
    component: ScreenplayEditorView,
    props: true,
  },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});
