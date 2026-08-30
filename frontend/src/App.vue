<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import { FolderPlus, Plus, RefreshCw } from "lucide-vue-next";
import { api } from "./api/client";
import Modal from "./components/Modal.vue";
import { hasCockpit } from "./api/cockpit";
import { useProjects } from "./composables/useProjects";
import { useToast } from "./composables/useToast";

const toast = useToast();
const route = useRoute();
const router = useRouter();
const { state, refresh, summaryLabel } = useProjects();
const cockpitReady = computed(() => hasCockpit());

const showCreate = ref(false);
const showImport = ref(false);

const createForm = ref({
  name: "",
  notes: "",
  compose_yaml: `services:
  web:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "8080:80"
`,
});

const importForm = ref({
  name: "",
  compose_file: "",
  workdir: "",
  notes: "",
});

const activeName = computed(() => {
  const raw = route.params.name;
  return typeof raw === "string" ? raw : "";
});

async function loadList() {
  try {
    await refresh();
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
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
    toast.info(`已创建 ${created.name}`);
    await refresh();
    await router.push(`/p/${encodeURIComponent(created.name)}`);
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

async function importProject() {
  try {
    const created = await api.registerProject(importForm.value);
    showImport.value = false;
    toast.info(`已导入 ${created.name}`);
    await refresh();
    await router.push(`/p/${encodeURIComponent(created.name)}`);
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

onMounted(loadList);

watch(
  () => state.items.length,
  async (len) => {
    if (route.name === "empty" && len > 0) {
      const first = state.items[0];
      if (first) await router.replace(`/p/${encodeURIComponent(first.name)}`);
    }
  },
);
</script>

<template>
  <div class="shell">
    <aside class="side">
      <div class="side-top">
        <span class="side-title">项目</span>
        <button class="btn ghost icon-btn" type="button" title="刷新列表" :disabled="state.loading" @click="loadList">
          <RefreshCw :size="14" />
        </button>
      </div>

      <nav class="nav project-nav">
        <div v-if="!state.items.length && state.loaded" class="nav-empty muted">暂无项目</div>
        <RouterLink
          v-for="item in state.items"
          :key="item.name"
          class="project-link"
          :class="{ active: activeName === item.name }"
          :to="`/p/${encodeURIComponent(item.name)}`"
        >
          <span class="dot" :class="item.summary"></span>
          <span class="project-meta">
            <strong>{{ item.name }}</strong>
            <small>{{ summaryLabel(item.summary) }} · {{ item.running }}/{{ item.total }}</small>
          </span>
        </RouterLink>
      </nav>

      <div class="side-actions">
        <button class="btn" type="button" @click="showImport = true">
          <FolderPlus :size="14" /> 导入
        </button>
        <button class="btn primary" type="button" @click="showCreate = true">
          <Plus :size="14" /> 新建
        </button>
      </div>
    </aside>

    <main class="main">
      <div v-if="!cockpitReady" class="warn-banner">
        当前为本地预览模式。完整功能请安装到 Cockpit 后打开。
      </div>
      <RouterView />
    </main>

    <div class="toast-host">
      <div v-for="item in toast.state.items" :key="item.id" class="toast" :class="item.type">
        {{ item.text }}
      </div>
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
        <span class="muted">写入 /var/lib/dock-panel/projects/&lt;name&gt;/</span>
        <button class="btn primary" type="button" @click="createProject">创建</button>
      </template>
    </Modal>

    <Modal v-if="showImport" title="导入现有 Compose" @close="showImport = false">
      <div class="field">
        <label>项目名（可空，优先读 compose 内 name:）</label>
        <input v-model="importForm.name" placeholder="duolali-prod" />
      </div>
      <div class="field">
        <label>compose 文件路径</label>
        <input v-model="importForm.compose_file" placeholder="/data/compose.yaml" />
      </div>
      <div class="field">
        <label>工作目录（可空）</label>
        <input v-model="importForm.workdir" placeholder="/data" />
      </div>
      <template #footer>
        <span></span>
        <button class="btn primary" type="button" @click="importProject">导入</button>
      </template>
    </Modal>
  </div>
</template>
