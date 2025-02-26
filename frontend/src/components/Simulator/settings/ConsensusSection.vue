<script setup lang="ts">
import { ref, computed } from 'vue';
import PageSection from '@/components/Simulator/PageSection.vue';
import FieldError from '@/components/global/fields/FieldError.vue';
import NumberInput from '@/components/global/inputs/NumberInput.vue';

const maxAppealRound = ref(Number(import.meta.env.VITE_MAX_APPEALS));

const isMaxAppealRoundValid = computed(() => {
  return Number.isInteger(maxAppealRound.value) && maxAppealRound.value >= 0;
});
</script>

<template>
  <PageSection>
    <template #title>Consensus</template>

    <div class="p-2">
      <div class="flex flex-wrap items-center gap-2">
        <label for="maxAppealRound" class="text-xs">Max Appeal Rounds</label>
        <NumberInput
          id="maxAppealRound"
          name="maxAppealRound"
          :min="0"
          :step="1"
          :invalid="!isMaxAppealRoundValid"
          v-model.number="maxAppealRound"
          required
          testId="input-maxAppealRound"
          :disabled="false"
          class="h-6 w-12"
          tiny
        />
      </div>

      <FieldError v-if="!isMaxAppealRoundValid"
        >Please enter a positive integer.</FieldError
      >
    </div>
  </PageSection>
</template>
