<script setup lang="ts">
import { useClipboard } from '@vueuse/core';
import { Clipboard, ClipboardCheck } from 'lucide-vue-next';

const props = defineProps<{
  text: string;
}>();

const { copy, copied, isSupported } = useClipboard({
  source: props.text,
});
</script>

<template>
  <button
    v-if="isSupported"
    @click.stop="copy(text)"
    class="shrink-0 text-gray-400 transition-all hover:text-gray-500 dark:text-gray-400 dark:hover:text-gray-400"
  >
    <Clipboard v-if="!copied" class="h-4 w-4" />
    <ClipboardCheck v-else class="h-4 w-4 rotate-12" />
  </button>
</template>
