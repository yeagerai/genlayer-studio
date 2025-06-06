<script setup lang="ts">
import ConstructorParameters from '@/components/Simulator/ConstructorParameters.vue';
import ContractReadMethods from '@/components/Simulator/ContractReadMethods.vue';
import ContractWriteMethods from '@/components/Simulator/ContractWriteMethods.vue';
import TransactionsList from '@/components/Simulator/TransactionsList.vue';
import { useContractQueries, useConfig } from '@/hooks';
import MainTitle from '@/components/Simulator/MainTitle.vue';
import { ref, watch, computed } from 'vue';
import {
  useContractsStore,
  useNodeStore,
  useConsensusStore,
  useUIStore,
} from '@/stores';

import ContractInfo from '@/components/Simulator/ContractInfo.vue';
import BooleanField from '@/components/global/fields/BooleanField.vue';
import FieldError from '@/components/global/fields/FieldError.vue';
import NumberInput from '@/components/global/inputs/NumberInput.vue';

const uiStore = useUIStore();
const contractsStore = useContractsStore();
const { isDeployed, address, contract } = useContractQueries();
const nodeStore = useNodeStore();
const consensusStore = useConsensusStore();
const leaderOnly = ref(false);

const isDeploymentOpen = ref(!isDeployed.value);
const finalityWindow = computed({
  get: () => consensusStore.finalityWindow,
  set: (newTime) => {
    if (isFinalityWindowValid(newTime)) {
      consensusStore.setFinalityWindowTime(newTime);
    }
  },
});
const isLoading = computed(() => consensusStore.isLoading);
const { canUpdateFinalityWindow } = useConfig();

// Hide constructors by default when contract is already deployed
const setConstructorVisibility = () => {
  isDeploymentOpen.value = !isDeployed.value;
};

watch(
  [() => contract.value?.id, () => isDeployed.value, () => address.value],
  setConstructorVisibility,
);

function isFinalityWindowValid(value: number) {
  return Number.isInteger(value) && value >= 0;
}

const consensusMaxRotations = computed(() => consensusStore.maxRotations);
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

      <div v-if="isLoading">Loading finality window...</div>
      <div v-else>
        <div v-if="canUpdateFinalityWindow" class="p-2">
          <div class="flex flex-wrap items-center gap-2">
            <label for="finalityWindow" class="text-xs"
              >Finality Window (seconds)</label
            >
            <NumberInput
              id="finalityWindow"
              name="finalityWindow"
              :min="0"
              :step="1"
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
      </div>

      <ContractInfo
        :showNewDeploymentButton="!isDeploymentOpen"
        @openDeployment="isDeploymentOpen = true"
      />

      <template v-if="nodeStore.hasAtLeastOneValidator || uiStore.showTutorial">
        <ConstructorParameters
          id="tutorial-how-to-deploy"
          v-if="isDeploymentOpen"
          @deployedContract="isDeploymentOpen = false"
          :leaderOnly="leaderOnly"
          :consensusMaxRotations="consensusMaxRotations"
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
          :consensusMaxRotations="consensusMaxRotations"
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
