import { reactive } from "vue";

interface ToastItem {
  id: number;
  text: string;
  type: "info" | "error";
}

const state = reactive({
  items: [] as ToastItem[],
});

let seq = 1;

export function useToast() {
  function push(text: string, type: ToastItem["type"] = "info") {
    const id = seq++;
    state.items.push({ id, text, type });
    window.setTimeout(() => {
      const index = state.items.findIndex((item) => item.id === id);
      if (index >= 0) {
        state.items.splice(index, 1);
      }
    }, 4200);
  }

  return {
    state,
    info: (text: string) => push(text, "info"),
    error: (text: string) => push(text, "error"),
  };
}
