<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api/client";
import type { Project, ScanHit } from "../api/types";
import Modal from "../components/Modal.vue";
import { useToast } from "../composables/useToast";

const toast = useToast();
const router = useRouter();
const loading = ref(false);
const projects = ref<Project[]>([]);
const scans = ref<ScanHit[]>([]);
const showCreate = ref(false);
const showImport = ref(false);
const showScan = ref(false);

const createForm = ref({
  name: "",
  notes: "",
  compose_yaml: `services:
  web:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "8080:80"
    labels:
      dock-panel.project: example
`,
});

const importForm = ref({
  name: "",
  compose_file: "",
  workdir: "",
  notes: "",
});

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

function summaryClass(summary: string) {
  if (summary === "running") return "ok";
  if (summary === "partial") return "warn";
  if (summary === "error" || summary === "missing") return "danger";
  return "";
}

async function load() {
  loading.value = true;
  try {
    projects.value = await api.listProjects();
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  } finally {
    loading.value = false;
  }
}

async function createProject() {
  try {
    const created = await api.createProject({
      name: createForm.value.name,
      notes: createForm.value.notes,
      compose_yaml: createForm.value.compose_yaml,
    });
    showCreate.value = false;
    toast.info(`已创建项目 ${created.name}`);
    await load();
    router.push(`/projects/${encodeURIComponent(created.name)}`);
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

async function importProject() {
  try {
    const created = await api.registerProject(importForm.value);
    showImport.value = false;
    toast.info(`已导入 ${created.name}`);
    await load();
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

async function scan() {
  try {
    scans.value = await api.scanProjects();
    showScan.value = true;
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

async function registerScan(hit: ScanHit) {
  try {
    await api.registerProject({
      name: hit.name,
      compose_file: hit.compose_file,
      workdir: hit.workdir,
    });
    toast.info(`已登记 ${hit.name}`);
    await load();
    scans.value = scans.value.map((item) =>
      item.compose_file === hit.compose_file ? { ...item, registered: true } : item,
    );
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

onMounted(load);
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h2>项目</h2>
        <p>用 Compose 文件把一组容器当成一个项目来管理，也可以导入现有栈。</p>
      </div>
      <div class="row">
        <button class="btn" type="button" @click="scan">扫描 compose</button>
        <button class="btn" type="button" @click="showImport = true">导入</button>
        <button class="btn primary" type="button" @click="showCreate = true">新建项目</button>
      </div>
    </div>

    <div class="card" style="padding: 0; overflow: auto">
      <table class="table">
        <thead>
          <tr>
            <th>名称</th>
            <th>状态</th>
            <th>容器</th>
            <th>端口</th>
            <th>来源</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!projects.length">
            <td colspan="5" class="empty">暂无项目</td>
          </tr>
          <tr
            v-for="item in projects"
            :key="item.name"
            style="cursor: pointer"
            @click="router.push(`/projects/${encodeURIComponent(item.name)}`)"
          >
            <td>
              <strong>{{ item.name }}</strong>
              <div class="faint mono" style="font-size: 12px">{{ item.compose_file }}</div>
            </td>
            <td>
              <span class="badge" :class="summaryClass(item.summary)">
                <span class="dot" :class="item.summary"></span>
                {{ summaryLabel(item.summary) }}
              </span>
              <span v-if="item.unregistered" class="badge warn" style="margin-left: 6px">未登记</span>
            </td>
            <td>{{ item.running }}/{{ item.total }}</td>
            <td class="mono">{{ item.ports.slice(0, 4).join(", ") || "—" }}</td>
            <td>{{ item.managed ? "托管" : "外部 Compose" }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <Modal v-if="showCreate" title="新建 Compose 项目" @close="showCreate = false">
      <div class="field">
        <label>项目名</label>
        <input v-model="createForm.name" placeholder="例如 homepage" />
      </div>
      <div class="field">
        <label>备注</label>
        <input v-model="createForm.notes" />
      </div>
      <div class="field">
        <label>compose.yaml</label>
        <textarea v-model="createForm.compose_yaml" style="min-height: 260px"></textarea>
      </div>
      <template #footer>
        <span class="muted">文件会写到 /var/lib/dock-panel/projects/&lt;name&gt;/</span>
        <button class="btn primary" type="button" @click="createProject">创建</button>
      </template>
    </Modal>

    <Modal v-if="showImport" title="导入现有 Compose" @close="showImport = false">
      <div class="field">
        <label>项目名（可空，默认用目录名）</label>
        <input v-model="importForm.name" />
      </div>
      <div class="field">
        <label>compose 文件路径</label>
        <input v-model="importForm.compose_file" placeholder="/opt/app/compose.yaml" />
      </div>
      <div class="field">
        <label>工作目录（可空）</label>
        <input v-model="importForm.workdir" />
      </div>
      <template #footer>
        <span></span>
        <button class="btn primary" type="button" @click="importProject">导入</button>
      </template>
    </Modal>

    <Modal v-if="showScan" title="扫描到的 Compose 文件" @close="showScan = false">
      <table class="table">
        <thead>
          <tr>
            <th>目录</th>
            <th>文件</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!scans.length">
            <td colspan="3" class="empty">没有发现 compose 文件</td>
          </tr>
          <tr v-for="hit in scans" :key="hit.compose_file">
            <td>{{ hit.name }}</td>
            <td class="mono">{{ hit.compose_file }}</td>
            <td>
              <span v-if="hit.registered" class="muted">已登记</span>
              <button v-else class="btn" type="button" @click="registerScan(hit)">登记</button>
            </td>
          </tr>
        </tbody>
      </table>
      <template #footer>
        <span class="muted">扫描 /opt、/srv、/home、/root 等常见目录</span>
        <button class="btn" type="button" @click="showScan = false">完成</button>
      </template>
    </Modal>
  </div>
</template>
