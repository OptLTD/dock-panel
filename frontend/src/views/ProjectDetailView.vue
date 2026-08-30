<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api/client";
import type { Project } from "../api/types";
import LogViewer from "../components/LogViewer.vue";
import { useToast } from "../composables/useToast";

const props = defineProps<{ name: string }>();
const toast = useToast();
const router = useRouter();
const project = ref<Project | null>(null);
const tab = ref<"overview" | "compose" | "logs">("overview");
const busy = ref("");
const output = ref("");
const composeYaml = ref("");
const envText = ref("");
const logText = ref("");
const follow = ref(false);
let followHandle: { close: () => void } | null = null;

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
  try {
    const data = await api.getProject(props.name);
    project.value = data;
    composeYaml.value = data.compose_yaml || "";
    envText.value = data.env_text || "";
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

async function runAction(action: "up" | "down" | "restart" | "pull" | "start" | "stop") {
  if (!project.value) return;
  if (project.value.unregistered) {
    toast.error("请先在项目列表中登记后再操作");
    return;
  }
  busy.value = action;
  output.value = "";
  const handle = api.streamProjectAction(project.value.name, action, (chunk) => {
    output.value += chunk;
  });
  try {
    await handle.done;
    toast.info(`${action} 完成`);
    await load();
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  } finally {
    busy.value = "";
  }
}

async function saveCompose() {
  if (!project.value) return;
  try {
    await api.updateProject(project.value.name, {
      compose_yaml: composeYaml.value,
      env_text: envText.value,
      notes: project.value.notes,
    });
    toast.info("已保存");
    await load();
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

async function loadLogs() {
  if (!project.value) return;
  try {
    logText.value = await api.tailLogs(project.value.name, undefined, 300);
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

function toggleFollow() {
  if (!project.value) return;
  if (follow.value) {
    followHandle?.close();
    followHandle = null;
    follow.value = false;
    return;
  }
  follow.value = true;
  followHandle = api.followLogs(project.value.name, (chunk) => {
    logText.value += chunk;
  });
}

async function destroy(removeFiles: boolean) {
  if (!project.value) return;
  const ok = window.confirm(removeFiles ? "删除项目并移除托管文件？" : "取消登记该项目？");
  if (!ok) return;
  try {
    await api.unregisterProject(project.value.name, { destroy: true, remove_files: removeFiles });
    toast.info("已移除");
    router.push("/projects");
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

onMounted(async () => {
  await load();
  await loadLogs();
});
</script>

<template>
  <div v-if="project">
    <div class="page-head">
      <div>
        <h2>{{ project.name }}</h2>
        <p class="mono">{{ project.compose_file }}</p>
      </div>
      <div class="row">
        <button class="btn primary" type="button" :disabled="Boolean(busy)" @click="runAction('up')">启动</button>
        <button class="btn" type="button" :disabled="Boolean(busy)" @click="runAction('restart')">重启</button>
        <button class="btn" type="button" :disabled="Boolean(busy)" @click="runAction('pull')">拉取</button>
        <button class="btn" type="button" :disabled="Boolean(busy)" @click="runAction('stop')">停止</button>
        <button class="btn danger" type="button" :disabled="Boolean(busy)" @click="runAction('down')">卸载</button>
      </div>
    </div>

    <div class="row" style="margin-bottom: 16px">
      <span class="badge">{{ summaryLabel(project.summary) }}</span>
      <span class="badge">{{ project.running }}/{{ project.total }} 容器</span>
      <span class="badge">{{ project.managed ? "托管项目" : "外部 Compose" }}</span>
      <span v-if="project.unregistered" class="badge warn">未登记，生命周期操作前请先导入</span>
    </div>

    <div class="tabs">
      <button type="button" :class="{ active: tab === 'overview' }" @click="tab = 'overview'">服务</button>
      <button type="button" :class="{ active: tab === 'compose' }" @click="tab = 'compose'">Compose</button>
      <button type="button" :class="{ active: tab === 'logs' }" @click="tab = 'logs'">日志</button>
    </div>

    <div v-if="tab === 'overview'" class="card" style="padding: 0">
      <table class="table">
        <thead>
          <tr>
            <th>服务</th>
            <th>镜像</th>
            <th>状态</th>
            <th>端口</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!project.services.length">
            <td colspan="4" class="empty">还没有容器。可以先启动项目。</td>
          </tr>
          <tr v-for="svc in project.services" :key="svc.id || svc.name">
            <td>
              <span class="dot" :class="svc.state"></span>
              {{ svc.service || svc.name }}
            </td>
            <td class="mono">{{ svc.image }}</td>
            <td>{{ svc.status || svc.state }}</td>
            <td class="mono">{{ svc.ports.join(", ") || "—" }}</td>
          </tr>
        </tbody>
      </table>
      <pre v-if="output" class="log-view" style="min-height: 160px; max-height: 240px; margin: 0; border: 0; border-radius: 0">{{ output }}</pre>
    </div>

    <div v-else-if="tab === 'compose'" class="grid">
      <div class="card">
        <div class="field">
          <label>compose.yaml</label>
          <textarea v-model="composeYaml" style="min-height: 320px"></textarea>
        </div>
        <div class="field" style="margin-top: 12px">
          <label>.env</label>
          <textarea v-model="envText" style="min-height: 120px"></textarea>
        </div>
        <div class="row" style="margin-top: 12px; justify-content: space-between">
          <div class="row">
            <button class="btn primary" type="button" @click="saveCompose">保存</button>
            <button class="btn" type="button" @click="router.push(`/logs/${encodeURIComponent(project.name)}`)">打开日志页</button>
          </div>
          <div class="row">
            <button class="btn danger" type="button" @click="destroy(false)">取消登记</button>
            <button v-if="project.managed" class="btn danger" type="button" @click="destroy(true)">删除托管文件</button>
          </div>
        </div>
      </div>
    </div>

    <div v-else>
      <div class="row" style="margin-bottom: 12px">
        <button class="btn" type="button" @click="loadLogs">刷新</button>
        <button class="btn" type="button" @click="toggleFollow">{{ follow ? "停止跟踪" : "跟踪" }}</button>
      </div>
      <LogViewer :value="logText" :follow="follow" />
    </div>
  </div>
</template>
