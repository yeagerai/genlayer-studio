<script setup lang="ts">
import PageSection from '@/components/Simulator/PageSection.vue';
import { CheckCircleIcon } from '@heroicons/vue/24/outline';
import EmptyListPlaceholder from '@/components/Simulator/EmptyListPlaceholder.vue';
import { useNodeStore } from '@/stores';
import { useContractQueries, useShortAddress } from '@/hooks';
import { UploadIcon } from 'lucide-vue-next';

const nodeStore = useNodeStore();
const { shorten } = useShortAddress();

defineProps<{
  showNewDeploymentButton: boolean;
}>();

const emit = defineEmits(['openDeployment']);
const { isDeployed, address, contract } = useContractQueries();
</script>

<template>
  <PageSection>
    <template #title
      >Contract
      <div data-testid="current-contract-name" class="opacity-50">
        {{ contract?.name }}
      </div></template
    >

    <div
      v-if="isDeployed"
      data-testid="deployed-contract-info"
      class="flex flex-row items-center gap-1 text-xs"
    >
      <CheckCircleIcon class="h-4 w-4 shrink-0 text-emerald-400" />

      Deployed at

      <div class="font-semibold">
        {{ shorten(address) }}
      </div>

      <CopyTextButton :text="address" />
    </div>

    <EmptyListPlaceholder v-else>Not deployed yet.</EmptyListPlaceholder>

    <Alert
      warning
      v-if="
        !nodeStore.isLoadingValidatorData && !nodeStore.hasAtLeastOneValidator
      "
    >
      You need at least one validator before you can deploy or interact with a
      contract.

      <RouterLink :to="{ name: 'settings' }"
        ><Btn secondary tiny class="mt-1">Go to settings</Btn></RouterLink
      >
    </Alert>

    <Btn
      secondary
      tiny
      class="inline-flex w-auto shrink grow-0"
      v-else-if="showNewDeploymentButton"
      @click="emit('openDeployment')"
      :icon="UploadIcon"
    >
      Deploy new instance
    </Btn>
  </PageSection>
</template>
