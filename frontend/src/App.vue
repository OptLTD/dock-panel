<script setup lang="ts">
import { computed } from "vue";
import { RouterLink, RouterView } from "vue-router";
import { Boxes, FileKey2, LayoutDashboard, ScrollText } from "lucide-vue-next";
import { useToast } from "../composables/useToast";
import { hasCockpit } from "../api/cockpit";

const toast = useToast();
const cockpitReady = computed(() => hasCockpit());
</script>

<template>
  <div class="shell">
    <aside class="side">
      <div class="brand">
        <div class="brand-mark">
          <Boxes :size="18" />
        </div>
        <div>
          <h1>Dock Panel</h1>
          <p>Compose · 证书 · 日志</p>
        </div>
      </div>
      <nav class="nav">
        <RouterLink to="/">
          <LayoutDashboard :size="16" /> 概览
        </RouterLink>
        <RouterLink to="/projects">
          <Boxes :size="16" /> 项目
        </RouterLink>
        <RouterLink to="/certs">
          <FileKey2 :size="16" /> 证书
        </RouterLink>
        <RouterLink to="/logs">
          <ScrollText :size="16" /> 日志
        </RouterLink>
      </nav>
      <div class="side-foot">
        通过 Cockpit 调用本机 Docker Compose。需要 docker 权限或管理员提权。
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
  </div>
</template>
