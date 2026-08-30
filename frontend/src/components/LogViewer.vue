<script setup lang="ts">
defineProps<{
  value: string;
  follow?: boolean;
}>();
</script>

<template>
  <pre class="log-view">{{ value || "暂无日志" }}</pre>
</template>
