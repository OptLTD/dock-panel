import { createRouter, createWebHashHistory } from "vue-router";
import DashboardView from "./views/DashboardView.vue";
import ProjectsView from "./views/ProjectsView.vue";
import ProjectDetailView from "./views/ProjectDetailView.vue";
import CertificatesView from "./views/CertificatesView.vue";
import LogsView from "./views/LogsView.vue";

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", name: "dashboard", component: DashboardView },
    { path: "/projects", name: "projects", component: ProjectsView },
    { path: "/projects/:name", name: "project", component: ProjectDetailView, props: true },
    { path: "/certs", name: "certs", component: CertificatesView },
    { path: "/logs", name: "logs", component: LogsView },
    { path: "/logs/:name", name: "project-logs", component: LogsView, props: true },
  ],
});
