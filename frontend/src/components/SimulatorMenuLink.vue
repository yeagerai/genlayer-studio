<script setup lang="ts">
import { defineProps, defineEmits } from 'vue';

defineProps({
  href: { type: String, default: '' },
});

const emit = defineEmits(['click']);
</script>

<template>
  <component
    :is="href ? 'a' : 'button'"
    :href="href || undefined"
    target="_blank"
    @click="emit('click')"
    class="group p-3"
  >
    <div
      class="h-4 w-4 fill-primary opacity-50 group-hover:opacity-70 dark:fill-white"
    >
      <slot />
    </div>
  </component>
</template>
