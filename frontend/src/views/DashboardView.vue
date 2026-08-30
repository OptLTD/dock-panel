<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api/client";
import type { Certificate, HealthInfo, Project } from "../api/types";
import { useToast } from "../composables/useToast";

const toast = useToast();
const router = useRouter();
const loading = ref(true);
const health = ref<HealthInfo | null>(null);
const projects = ref<Project[]>([]);
const certs = ref<Certificate[]>([]);

const running = computed(() => projects.value.filter((item) => item.summary === "running").length);
const expiring = computed(() => certs.value.filter((item) => item.days_left !== null && item.days_left <= 30).length);

function summaryClass(summary: string) {
  if (summary === "running") return "ok";
  if (summary === "partial") return "warn";
  if (summary === "error" || summary === "missing") return "danger";
  return "";
}

function summaryLabel(summary: string) {
  const map: Record<string, string> = {
    running: "运行中",
    stopped: "已停止",
    partial: "部分运行",
    empty: "无容器",
    missing: "缺少文件",
    error: "异常",
  };
  return map[summary] || summary;
}

async function load() {
  loading.value = true;
  try {
    const [h, p, c] = await Promise.all([api.health(), api.listProjects(), api.listCerts()]);
    health.value = h;
    projects.value = p;
    certs.value = c;
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h2>概览</h2>
        <p>按项目管理 Docker Compose、证书与容器日志。</p>
      </div>
      <button class="btn" type="button" :disabled="loading" @click="load">刷新</button>
    </div>

    <div v-if="health && !health.engine.docker" class="warn-banner">
      未检测到 Docker 引擎{{ health.engine.error ? `：${health.engine.error}` : "" }}
    </div>

    <div class="grid stats">
      <div class="card">
        <div class="stat-label">项目</div>
        <div class="stat-value">{{ projects.length }}</div>
      </div>
      <div class="card">
        <div class="stat-label">运行中</div>
        <div class="stat-value">{{ running }}</div>
      </div>
      <div class="card">
        <div class="stat-label">证书</div>
        <div class="stat-value">{{ certs.length }}</div>
      </div>
      <div class="card">
        <div class="stat-label">即将过期</div>
        <div class="stat-value">{{ expiring }}</div>
      </div>
    </div>

    <div class="page-head" style="margin-top: 28px">
      <div>
        <h2 style="font-size: 18px">项目</h2>
        <p>点击卡片进入 Compose 管理。</p>
      </div>
    </div>

    <div v-if="!projects.length" class="card empty">还没有项目。去「项目」页导入 compose 或新建。</div>
    <div v-else class="grid cards">
      <div
        v-for="item in projects"
        :key="item.name"
        class="card clickable"
        @click="router.push(`/projects/${encodeURIComponent(item.name)}`)"
      >
        <div class="row" style="justify-content: space-between">
          <strong>{{ item.name }}</strong>
          <span class="badge" :class="summaryClass(item.summary)">
            <span class="dot" :class="item.summary"></span>
            {{ summaryLabel(item.summary) }}
          </span>
        </div>
        <p class="muted" style="margin: 10px 0 0">{{ item.running }}/{{ item.total }} 个容器</p>
        <p class="faint mono" style="margin: 8px 0 0; font-size: 12px">
          {{ item.ports.slice(0, 3).join("  ") || "未发布端口" }}
        </p>
      </div>
    </div>
  </div>
</template>
