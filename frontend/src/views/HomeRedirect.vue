<script setup lang="ts">
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { useProjects } from "../composables/useProjects";
import { useToast } from "../composables/useToast";

const router = useRouter();
const { state, registered, refresh } = useProjects();
const toast = useToast();

onMounted(async () => {
  try {
    if (!state.loaded) await refresh();
    const first = registered.value[0] || state.items[0];
    if (first) {
      await router.replace(`/p/${encodeURIComponent(first.name)}`);
    } else {
      await router.replace("/empty");
    }
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
    await router.replace("/empty");
  }
});
</script>

<template>
  <div class="empty">正在加载项目…</div>
</template>
