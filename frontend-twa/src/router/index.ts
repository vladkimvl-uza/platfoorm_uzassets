import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import { useTwaAuth } from "@/composables/useTwaAuth";

const routes: RouteRecordRaw[] = [
  { path: "/twa/login", name: "twa-login", component: () => import("@/views/TwaLogin.vue") },
  { path: "/twa/", name: "twa-home", component: () => import("@/views/TwaHome.vue"), meta: { requiresAuth: true } },
  { path: "/twa/tasks", name: "twa-tasks", component: () => import("@/views/TwaTaskList.vue"), meta: { requiresAuth: true } },
  { path: "/twa/approve/:id", name: "twa-approval", component: () => import("@/views/TwaApproval.vue"), meta: { requiresAuth: true } },
  { path: "/twa/procurement/:id", name: "twa-procurement", component: () => import("@/views/TwaProcurementReview.vue"), meta: { requiresAuth: true } },
  { path: "/twa/error", name: "twa-error", component: () => import("@/views/TwaError.vue") },
  { path: "/:pathMatch(.*)*", redirect: "/twa/" },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to) => {
  const auth = useTwaAuth();
  if (to.meta.requiresAuth && !auth.token.value) {
    return { name: "twa-login", query: { next: to.fullPath } };
  }
  return true;
});
