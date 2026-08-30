import { computed, reactive } from "vue";
import { api } from "../api/client";
import type { Project } from "../api/types";

const state = reactive({
  items: [] as Project[],
  loading: false,
  loaded: false,
  error: "",
});

export function useProjects() {
  const registered = computed(() => state.items.filter((item) => !item.unregistered));

  async function refresh() {
    state.loading = true;
    state.error = "";
    try {
      state.items = await api.listProjects();
      state.loaded = true;
    } catch (error) {
      state.error = error instanceof Error ? error.message : String(error);
      throw error;
    } finally {
      state.loading = false;
    }
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

  return {
    state,
    registered,
    refresh,
    summaryLabel,
  };
}
