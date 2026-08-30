<script setup lang="ts">
defineProps<{
  title: string;
}>();

const emit = defineEmits<{
  close: [];
}>();
</script>

<template>
  <div class="modal-mask" @click.self="emit('close')">
    <div class="modal">
      <header>
        <h3>{{ title }}</h3>
        <button class="btn ghost" type="button" @click="emit('close')">关闭</button>
      </header>
      <div class="body">
        <slot />
      </div>
      <footer>
        <slot name="footer" />
      </footer>
    </div>
  </div>
</template>
