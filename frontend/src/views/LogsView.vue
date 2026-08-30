<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { api } from "../api/client";
import type { Project } from "../api/types";
import LogViewer from "../components/LogViewer.vue";
import { useToast } from "../composables/useToast";

const props = defineProps<{ name?: string }>();
const toast = useToast();
const projects = ref<Project[]>([]);
const projectName = ref(props.name || "");
const serviceName = ref("");
const lines = ref(200);
const logText = ref("");
const following = ref(false);
let handle: { close: () => void; done: Promise<string> } | null = null;

const current = () => projects.value.find((item) => item.name === projectName.value) || null;

async function loadProjects() {
  try {
    projects.value = (await api.listProjects()).filter((item) => !item.unregistered);
    if (!projectName.value && projects.value[0]) {
      projectName.value = projects.value[0].name;
    }
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

async function loadTail() {
  if (!projectName.value) return;
  try {
    logText.value = await api.tailLogs(projectName.value, serviceName.value || undefined, lines.value);
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

function stopFollow() {
  handle?.close();
  handle = null;
  following.value = false;
}

function startFollow() {
  if (!projectName.value) return;
  stopFollow();
  following.value = true;
  handle = api.followLogs(
    projectName.value,
    (chunk) => {
      logText.value += chunk;
    },
    serviceName.value || undefined,
    lines.value,
  );
  handle.done.catch((error: unknown) => {
    following.value = false;
    const err = error as { message?: string; exit_status?: number; toString?: () => string };
    const msg =
      (err && (err.message || (typeof err.toString === "function" ? err.toString() : ""))) ||
      String(error);
    toast.error(msg || "跟踪日志失败");
  });
}

watch(
  () => props.name,
  (value) => {
    if (value) projectName.value = value;
  },
);

watch(projectName, () => {
  serviceName.value = "";
  stopFollow();
  loadTail();
});

onMounted(async () => {
  await loadProjects();
  await loadTail();
});

onBeforeUnmount(stopFollow);
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h2>日志</h2>
        <p>查看并跟踪 Compose 项目日志，可按服务过滤。</p>
      </div>
      <div class="row">
        <button class="btn" type="button" @click="loadTail">刷新</button>
        <button class="btn primary" type="button" @click="following ? stopFollow() : startFollow()">
          {{ following ? "停止跟踪" : "跟踪" }}
        </button>
      </div>
    </div>

    <div class="card" style="margin-bottom: 14px">
      <div class="row">
        <div class="field" style="min-width: 200px">
          <label>项目</label>
          <select v-model="projectName">
            <option value="">选择项目</option>
            <option v-for="item in projects" :key="item.name" :value="item.name">{{ item.name }}</option>
          </select>
        </div>
        <div class="field" style="min-width: 180px">
          <label>服务</label>
          <select v-model="serviceName">
            <option value="">全部服务</option>
            <option
              v-for="svc in current()?.services || []"
              :key="svc.service || svc.name"
              :value="svc.service || svc.name"
            >
              {{ svc.service || svc.name }}
            </option>
          </select>
        </div>
        <div class="field" style="width: 120px">
          <label>行数</label>
          <input v-model.number="lines" type="number" min="50" max="2000" />
        </div>
      </div>
    </div>

    <LogViewer :value="logText" :follow="following" />
  </div>
</template>
