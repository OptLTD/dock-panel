<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api } from "../api/client";
import type { Certificate, Project } from "../api/types";
import Modal from "../components/Modal.vue";
import { useToast } from "../composables/useToast";

const toast = useToast();
const certs = ref<Certificate[]>([]);
const projects = ref<Project[]>([]);
const showUpload = ref(false);
const showGenerate = ref(false);
const assignName = ref("");
const assignTarget = ref("");

const uploadForm = ref({
  name: "",
  cert_pem: "",
  key_pem: "",
  chain_pem: "",
  notes: "",
  overwrite: false,
});

const generateForm = ref({
  name: "",
  cn: "",
  sans: "",
  days: 365,
  notes: "",
  overwrite: false,
});

const selected = computed(() => certs.value.find((item) => item.name === assignName.value) || null);
const linkedProjects = computed(() =>
  selected.value ? projects.value.filter((item) => item.certs?.includes(selected.value!.name)) : [],
);

function expiryClass(cert: Certificate) {
  if (cert.expired) return "danger";
  if (cert.days_left !== null && cert.days_left <= 30) return "warn";
  return "ok";
}

function expiryText(cert: Certificate) {
  if (cert.expired) return "已过期";
  if (cert.days_left === null) return "未知";
  return `剩余 ${cert.days_left} 天`;
}

async function load() {
  try {
    const [c, p] = await Promise.all([api.listCerts(), api.listProjects()]);
    certs.value = c;
    projects.value = p.filter((item) => !item.unregistered);
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

async function importCert() {
  try {
    await api.importCert({
      ...uploadForm.value,
      source: "upload",
    });
    showUpload.value = false;
    toast.info("证书已导入");
    await load();
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

async function generate() {
  try {
    await api.generateCert(generateForm.value);
    showGenerate.value = false;
    toast.info("已生成自签证书");
    await load();
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

async function remove(name: string) {
  if (!window.confirm(`删除证书 ${name}？`)) return;
  try {
    await api.deleteCert(name);
    toast.info("已删除");
    await load();
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

async function assign(projectName: string, unassign = false) {
  if (!assignName.value) return;
  try {
    await api.assignCert(assignName.value, projectName, unassign);
    toast.info(unassign ? "已取消关联" : `已关联到 ${projectName}`);
    await load();
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
        <h2>证书</h2>
        <p>维护 TLS 证书，查看过期时间，并挂到项目目录的 certs/ 下供 Compose 挂载。</p>
      </div>
      <div class="row">
        <button class="btn" type="button" @click="showUpload = true">导入 PEM</button>
        <button class="btn primary" type="button" @click="showGenerate = true">生成自签证书</button>
      </div>
    </div>

    <div class="grid" style="grid-template-columns: 1.4fr 0.8fr">
      <div class="card" style="padding: 0">
        <table class="table">
          <thead>
            <tr>
              <th>名称</th>
              <th>主题</th>
              <th>到期</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!certs.length">
              <td colspan="4" class="empty">还没有证书</td>
            </tr>
            <tr
              v-for="item in certs"
              :key="item.name"
              :style="{ cursor: 'pointer', background: assignName === item.name ? 'var(--bg-hover)' : '' }"
              @click="assignName = item.name"
            >
              <td>
                <strong>{{ item.name }}</strong>
                <div class="faint">{{ item.source || "upload" }}{{ item.self_signed ? " · 自签" : "" }}</div>
              </td>
              <td class="mono">{{ item.subject || "—" }}</td>
              <td>
                <span class="badge" :class="expiryClass(item)">{{ expiryText(item) }}</span>
              </td>
              <td>
                <button class="btn danger" type="button" @click.stop="remove(item.name)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card">
        <h3 style="margin: 0 0 12px; font-size: 16px">详情 / 关联项目</h3>
        <div v-if="!selected" class="muted">选择左侧一张证书。</div>
        <template v-else>
          <p class="mono" style="font-size: 12px">{{ selected.fingerprint }}</p>
          <p class="muted">SAN：{{ selected.sans.join(", ") || "无" }}</p>
          <p class="muted">证书路径：<span class="mono">{{ selected.path }}</span></p>
          <p class="muted">私钥：{{ selected.has_key ? selected.key_path : "未提供" }}</p>
          <div class="field" style="margin-top: 14px">
            <label>挂到项目</label>
            <div class="row">
              <select v-model="assignTarget" style="flex: 1">
                <option value="">选择项目</option>
                <option v-for="item in projects" :key="item.name" :value="item.name">{{ item.name }}</option>
              </select>
              <button class="btn primary" type="button" :disabled="!assignTarget" @click="assign(assignTarget)">关联</button>
            </div>
          </div>
          <div style="margin-top: 12px">
            <div class="muted" style="margin-bottom: 6px">已关联</div>
            <div v-for="item in linkedProjects" :key="item.name" class="row" style="margin-bottom: 6px">
              <span>{{ item.name }}</span>
              <button class="btn ghost" type="button" @click="assign(item.name, true)">取消</button>
            </div>
          </div>
        </template>
      </div>
    </div>

    <Modal v-if="showUpload" title="导入证书" @close="showUpload = false">
      <div class="field">
        <label>名称</label>
        <input v-model="uploadForm.name" placeholder="例如 lab.local" />
      </div>
      <div class="field">
        <label>证书 PEM</label>
        <textarea v-model="uploadForm.cert_pem" placeholder="-----BEGIN CERTIFICATE-----"></textarea>
      </div>
      <div class="field">
        <label>私钥 PEM（可选）</label>
        <textarea v-model="uploadForm.key_pem" placeholder="-----BEGIN PRIVATE KEY-----"></textarea>
      </div>
      <div class="field">
        <label>中间证书链（可选）</label>
        <textarea v-model="uploadForm.chain_pem" style="min-height: 100px"></textarea>
      </div>
      <label class="row">
        <input v-model="uploadForm.overwrite" type="checkbox" />
        覆盖同名证书
      </label>
      <template #footer>
        <span></span>
        <button class="btn primary" type="button" @click="importCert">导入</button>
      </template>
    </Modal>

    <Modal v-if="showGenerate" title="生成自签证书" @close="showGenerate = false">
      <div class="field">
        <label>名称</label>
        <input v-model="generateForm.name" placeholder="lab.local" />
      </div>
      <div class="field">
        <label>CN</label>
        <input v-model="generateForm.cn" placeholder="默认与名称相同" />
      </div>
      <div class="field">
        <label>SAN（逗号分隔，可含 DNS 与 IP）</label>
        <input v-model="generateForm.sans" placeholder="lab.local, *.lab.local, 10.0.0.2" />
      </div>
      <div class="field">
        <label>有效期（天）</label>
        <input v-model.number="generateForm.days" type="number" min="1" max="3650" />
      </div>
      <template #footer>
        <span class="muted">使用本机 openssl 生成 RSA 2048</span>
        <button class="btn primary" type="button" @click="generate">生成</button>
      </template>
    </Modal>
  </div>
</template>
