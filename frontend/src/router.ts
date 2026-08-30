import { createRouter, createWebHashHistory } from "vue-router";
import HomeRedirect from "./views/HomeRedirect.vue";
import ProjectDetailView from "./views/ProjectDetailView.vue";
import EmptyProjectsView from "./views/EmptyProjectsView.vue";

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", name: "home", component: HomeRedirect },
    { path: "/empty", name: "empty", component: EmptyProjectsView },
    {
      path: "/p/:name",
      name: "project",
      component: ProjectDetailView,
      props: true,
    },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});
