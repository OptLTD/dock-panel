<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api/client";
import type { Certificate, Project } from "../api/types";
import LogViewer from "../components/LogViewer.vue";
import Modal from "../components/Modal.vue";
import { useProjects } from "../composables/useProjects";
import { useToast } from "../composables/useToast";

const props = defineProps<{ name: string }>();
const toast = useToast();
const router = useRouter();
const { refresh, summaryLabel } = useProjects();

const project = ref<Project | null>(null);
const tab = ref<"services" | "logs" | "certs" | "compose" | "env">("compose");
const busy = ref("");
const output = ref("");
const composeYaml = ref("");
const envText = ref("");
const logText = ref("");
const follow = ref(false);
const logService = ref("");
const logKeyword = ref("");
let followHandle: { close: () => void; done: Promise<string> } | null = null;

const certs = ref<Certificate[]>([]);
const showUpload = ref(false);
const showGenerate = ref(false);
const uploadForm = ref({
  name: "",
  cert_pem: "",
  key_pem: "",
  chain_pem: "",
  overwrite: false,
});
const generateForm = ref({
  name: "",
  cn: "",
  sans: "",
  days: 365,
  overwrite: false,
});

const linkedCerts = computed(() => {
  const names = new Set(project.value?.certs || []);
  return certs.value.filter((item) => names.has(item.name));
});

const otherCerts = computed(() => {
  const names = new Set(project.value?.certs || []);
  return certs.value.filter((item) => !names.has(item.name));
});

const displayedLogText = computed(() => {
  const kw = logKeyword.value.trim();
  if (!kw) return logText.value;
  const lower = kw.toLowerCase();
  return logText.value
    .split("\n")
    .filter((line) => line.toLowerCase().includes(lower))
    .join("\n");
});

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

async function loadCerts() {
  try {
    certs.value = await api.listCerts();
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

async function runAction(action: "up" | "down" | "restart" | "pull" | "start" | "stop") {
  if (!project.value) return;
  if (project.value.unregistered) {
    toast.error("请先导入登记后再操作");
    return;
  }
  busy.value = action;
  output.value = "";
  tab.value = "services";
  const handle = api.streamProjectAction(project.value.name, action, (chunk) => {
    output.value += chunk;
  });
  try {
    await handle.done;
    toast.info(`${action} 完成`);
    await load();
    await refresh();
  } catch (error) {
    const err = error as { message?: string; toString?: () => string };
    toast.error(err?.message || (typeof err?.toString === "function" ? err.toString() : String(error)));
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
    toast.info("Compose 已保存");
    await load();
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

async function saveEnv() {
  if (!project.value) return;
  try {
    await api.updateProject(project.value.name, {
      compose_yaml: composeYaml.value,
      env_text: envText.value,
      notes: project.value.notes,
    });
    toast.info("环境信息已保存");
    await load();
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

async function loadLogs() {
  if (!project.value) return;
  try {
    logText.value = await api.tailLogs(
      project.value.name,
      logService.value || undefined,
      300,
    );
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

function stopFollow() {
  followHandle?.close();
  followHandle = null;
  follow.value = false;
}

function toggleFollow() {
  if (!project.value) return;
  if (follow.value) {
    stopFollow();
    return;
  }
  follow.value = true;
  followHandle = api.followLogs(
    project.value.name,
    (chunk) => {
      logText.value += chunk;
    },
    logService.value || undefined,
  );
  followHandle.done.catch((error: unknown) => {
    follow.value = false;
    const err = error as { message?: string; toString?: () => string };
    toast.error(err?.message || (typeof err?.toString === "function" ? err.toString() : "跟踪失败"));
  });
}

async function destroy(removeFiles: boolean) {
  if (!project.value) return;
  const ok = window.confirm(removeFiles ? "删除项目并移除托管文件？" : "取消登记该项目？");
  if (!ok) return;
  try {
    await api.unregisterProject(project.value.name, { destroy: true, remove_files: removeFiles });
    toast.info("已移除");
    await refresh();
    await router.push("/");
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

function expiryText(cert: Certificate) {
  if (cert.expired) return "已过期";
  if (cert.days_left === null) return "未知";
  return `剩余 ${cert.days_left} 天`;
}

function expiryClass(cert: Certificate) {
  if (cert.expired) return "danger";
  if (cert.days_left !== null && cert.days_left <= 30) return "warn";
  return "ok";
}

async function assignCert(certName: string, unassign = false) {
  if (!project.value) return;
  try {
    await api.assignCert(certName, project.value.name, unassign);
    toast.info(unassign ? "已取消关联" : `已关联 ${certName}`);
    await Promise.all([load(), loadCerts(), refresh()]);
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

async function importCert() {
  if (!project.value) return;
  try {
    const name = uploadForm.value.name || `${project.value.name}-cert`;
    await api.importCert({ ...uploadForm.value, name, source: "upload" });
    await api.assignCert(name, project.value.name, false);
    showUpload.value = false;
    toast.info("证书已导入并关联");
    await Promise.all([load(), loadCerts()]);
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

async function generateCert() {
  if (!project.value) return;
  try {
    const name = generateForm.value.name || project.value.name;
    await api.generateCert({
      ...generateForm.value,
      name,
      cn: generateForm.value.cn || name,
    });
    await api.assignCert(name, project.value.name, false);
    showGenerate.value = false;
    toast.info("已生成并关联自签证书");
    await Promise.all([load(), loadCerts()]);
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

watch(
  () => props.name,
  async () => {
    stopFollow();
    tab.value = "services";
    output.value = "";
    logText.value = "";
    logService.value = "";
    logKeyword.value = "";
    await load();
  },
);

watch(tab, async (value) => {
  if (value === "logs" && !logText.value) await loadLogs();
  if (value === "certs") await loadCerts();
});

onMounted(async () => {
  await load();
});

onBeforeUnmount(stopFollow);
</script>

<template>
  <div v-if="project">
    <div class="page-head">
      <div>
        <div class="row" style="align-items: center; gap: 10px">
          <h2>{{ project.name }}</h2>
          <span
            class="badge"
            :class="{
              ok: project.summary === 'running',
              warn: project.summary === 'partial',
              danger: project.summary === 'error' || project.summary === 'missing',
            }"
          >{{ summaryLabel(project.summary) }}</span>
          <span class="badge">{{ project.running }}/{{ project.total }} 容器</span>
          <span class="badge">{{ project.managed ? "托管项目" : "外部 Compose" }}</span>
          <span v-if="project.error" class="badge danger">{{ project.error }}</span>
        </div>
      </div>
      <div class="row">
        <button class="btn primary" type="button" :disabled="Boolean(busy)" @click="runAction('up')">启动</button>
        <button class="btn" type="button" :disabled="Boolean(busy)" @click="runAction('restart')">重启</button>
        <button class="btn" type="button" :disabled="Boolean(busy)" @click="runAction('pull')">拉取</button>
        <button class="btn" type="button" :disabled="Boolean(busy)" @click="runAction('stop')">停止</button>
        <button class="btn danger" type="button" :disabled="Boolean(busy)" @click="runAction('down')">卸载</button>
      </div>
    </div>

    <div class="tabs">
      <button type="button" :class="{ active: tab === 'compose' }" @click="tab = 'compose'">Compose</button>
      <button type="button" :class="{ active: tab === 'services' }" @click="tab = 'services'">服务</button>
      <button type="button" :class="{ active: tab === 'logs' }" @click="tab = 'logs'">日志</button>
      <button type="button" :class="{ active: tab === 'certs' }" @click="tab = 'certs'">证书</button>
      <button type="button" :class="{ active: tab === 'env' }" @click="tab = 'env'">环境信息</button>
    </div>

    <div v-if="tab === 'services'" class="card" style="padding: 0">
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
      <pre
        v-if="output"
        class="log-view"
        style="min-height: 160px; max-height: 240px; margin: 0; border: 0; border-radius: 0"
      >{{ output }}</pre>
    </div>

    <div v-else-if="tab === 'logs'">
      <div class="row" style="margin: 12px 0">
        <div class="field" style="min-width: 180px">
          <!-- <label>服务</label> -->
          <select v-model="logService">
            <option value="">全部 / 自动</option>
            <option
              v-for="svc in project.services"
              :key="svc.service || svc.name"
              :value="svc.service || svc.name"
            >
              {{ svc.service || svc.name }}
            </option>
          </select>
        </div>
        <div class="field" style="min-width: 200px; flex: 1">
          <input v-model="logKeyword" type="search" placeholder="关键词筛选" />
        </div>
        <button class="btn" type="button" @click="loadLogs">刷新</button>
        <button class="btn primary" type="button" @click="toggleFollow">
          {{ follow ? "停止跟踪" : "跟踪" }}
        </button>
      </div>
      <LogViewer :value="displayedLogText" :follow="follow" />
    </div>

    <div v-else-if="tab === 'certs'" class="grid">
      <div class="card">
        <div class="row" style="justify-content: space-between; margin-bottom: 12px">
          <h3 style="margin: 0; font-size: 16px">已关联证书</h3>
          <div class="row">
            <button class="btn" type="button" @click="showUpload = true">导入 PEM</button>
            <button class="btn primary" type="button" @click="showGenerate = true">生成自签</button>
          </div>
        </div>
        <table class="table">
          <thead>
            <tr>
              <th>名称</th>
              <th>到期</th>
              <th>路径</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!linkedCerts.length">
              <td colspan="4" class="empty">尚未关联证书。挂载示例：./certs/&lt;name&gt;/cert.pem</td>
            </tr>
            <tr v-for="item in linkedCerts" :key="item.name">
              <td>{{ item.name }}</td>
              <td><span class="badge" :class="expiryClass(item)">{{ expiryText(item) }}</span></td>
              <td class="mono">{{ item.path }}</td>
              <td>
                <button class="btn ghost" type="button" @click="assignCert(item.name, true)">取消</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="otherCerts.length" class="card">
        <h3 style="margin: 0 0 12px; font-size: 16px">可关联的其它证书</h3>
        <div v-for="item in otherCerts" :key="item.name" class="row" style="margin-bottom: 8px">
          <span>{{ item.name }}</span>
          <button class="btn" type="button" @click="assignCert(item.name)">关联到本项目</button>
        </div>
      </div>
    </div>

    <div v-else-if="tab === 'compose'" class="card">
      <div class="field">
        <label class="mono">{{ project.compose_file }}</label>
        <textarea v-model="composeYaml" style="min-height: 420px"></textarea>
      </div>
      <div class="row" style="margin-top: 12px; justify-content: space-between">
        <button class="btn primary" type="button" @click="saveCompose">保存 Compose</button>
        <div class="row">
          <button class="btn danger" type="button" @click="destroy(false)">取消登记</button>
          <button v-if="project.managed" class="btn danger" type="button" @click="destroy(true)">
            删除托管文件
          </button>
        </div>
      </div>
    </div>

    <div v-else-if="tab === 'env'" class="card">
      <div class="field">
        <label>.env 环境变量</label>
        <textarea v-model="envText" style="min-height: 420px" placeholder="KEY=value"></textarea>
      </div>
      <div class="row" style="margin-top: 12px">
        <button class="btn primary" type="button" @click="saveEnv">保存环境信息</button>
      </div>
    </div>

    <Modal v-if="showUpload" title="导入证书到本项目" @close="showUpload = false">
      <div class="field">
        <label>名称</label>
        <input v-model="uploadForm.name" :placeholder="project.name" />
      </div>
      <div class="field">
        <label>证书 PEM</label>
        <textarea v-model="uploadForm.cert_pem"></textarea>
      </div>
      <div class="field">
        <label>私钥 PEM</label>
        <textarea v-model="uploadForm.key_pem"></textarea>
      </div>
      <template #footer>
        <span></span>
        <button class="btn primary" type="button" @click="importCert">导入并关联</button>
      </template>
    </Modal>

    <Modal v-if="showGenerate" title="生成自签证书" @close="showGenerate = false">
      <div class="field">
        <label>名称</label>
        <input v-model="generateForm.name" :placeholder="project.name" />
      </div>
      <div class="field">
        <label>CN</label>
        <input v-model="generateForm.cn" placeholder="app.example.com" />
      </div>
      <div class="field">
        <label>SAN</label>
        <input v-model="generateForm.sans" placeholder="app.example.com, *.example.com" />
      </div>
      <template #footer>
        <span></span>
        <button class="btn primary" type="button" @click="generateCert">生成并关联</button>
      </template>
    </Modal>
  </div>
  <div v-else class="empty">加载中…</div>
</template>
