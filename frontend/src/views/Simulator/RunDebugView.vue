<script setup lang="ts">
import ConstructorParameters from '@/components/Simulator/ConstructorParameters.vue';
import ContractReadMethods from '@/components/Simulator/ContractReadMethods.vue';
import ContractWriteMethods from '@/components/Simulator/ContractWriteMethods.vue';
import TransactionsList from '@/components/Simulator/TransactionsList.vue';
import { useContractQueries, useConfig } from '@/hooks';
import MainTitle from '@/components/Simulator/MainTitle.vue';
import { ref, watch, computed } from 'vue';
import { useContractsStore, useNodeStore } from '@/stores';
import ContractInfo from '@/components/Simulator/ContractInfo.vue';
import BooleanField from '@/components/global/fields/BooleanField.vue';
import FieldError from '@/components/global/fields/FieldError.vue';
import NumberInput from '@/components/global/inputs/NumberInput.vue';
const contractsStore = useContractsStore();
const { isDeployed, address, contract } = useContractQueries();
const nodeStore = useNodeStore();
const leaderOnly = ref(false);

const isDeploymentOpen = ref(!isDeployed.value);
const finalityWindow = ref(Number(import.meta.env.VITE_FINALITY_WINDOW));
const { canUpdateFinalityWindow } = useConfig();

// Hide constructors by default when contract is already deployed
const setConstructorVisibility = () => {
  isDeploymentOpen.value = !isDeployed.value;
};

watch(
  [() => contract.value?.id, () => isDeployed.value, () => address.value],
  setConstructorVisibility,
);

watch(finalityWindow, (newTime) => {
  if (isFinalityWindowValid.value) {
    nodeStore.setFinalityWindowTime(newTime);
  }
});

const isFinalityWindowValid = computed(() => {
  return Number.isInteger(finalityWindow.value) && finalityWindow.value >= 0;
});
</script>

<template>
  <div class="flex max-h-[93vh] w-full flex-col overflow-y-auto">
    <MainTitle data-testid="run-debug-page-title">Run and Debug</MainTitle>

    <template
      v-if="contractsStore.currentContract && contractsStore.currentContractId"
    >
      <BooleanField
        v-model="leaderOnly"
        name="leaderOnly"
        label="Leader Only (Fast Execution)"
        class="p-2"
      />

      <div v-if="canUpdateFinalityWindow" class="p-2">
        <div class="flex flex-wrap items-center gap-2">
          <label for="finalityWindow" class="text-xs"
            >Finality Window (seconds)</label
          >
          <NumberInput
            id="finalityWindow"
            name="finalityWindow"
            :min="1"
            :step="1"
            :invalid="!isFinalityWindowValid"
            v-model.number="finalityWindow"
            required
            testId="input-finalityWindow"
            :disabled="false"
            class="w-20"
            tiny
          />
        </div>

        <FieldError v-if="!isFinalityWindowValid"
          >Please enter a positive integer.</FieldError
        >
      </div>

      <ContractInfo
        :showNewDeploymentButton="!isDeploymentOpen"
        @openDeployment="isDeploymentOpen = true"
      />
      <template v-if="nodeStore.hasAtLeastOneValidator">
        <ConstructorParameters
          id="tutorial-how-to-deploy"
          v-if="isDeploymentOpen"
          @deployedContract="isDeploymentOpen = false"
          :leaderOnly="leaderOnly"
        />

        <ContractReadMethods
          v-if="isDeployed"
          id="tutorial-read-methods"
          :leaderOnly="leaderOnly"
        />
        <ContractWriteMethods
          v-if="isDeployed"
          id="tutorial-write-methods"
          :leaderOnly="leaderOnly"
        />
        <TransactionsList
          id="tutorial-tx-response"
          :finalityWindow="finalityWindow"
        />
      </template>
    </template>

    <div
      v-else
      class="flex w-full flex-col bg-slate-100 px-2 py-2 dark:dark:bg-zinc-700"
    >
      <div class="text-sm">
        Please first select an intelligent contract in the
        <RouterLink
          :to="{ name: 'contracts' }"
          class="text-primary underline dark:text-white"
        >
          Files list.
        </RouterLink>
      </div>
    </div>
  </div>
</template>
