<script setup lang="ts">
import CodeEditor from '@/components/Simulator/CodeEditor.vue';
import { useContractsStore } from '@/stores';
import { computed } from 'vue';
import HomeTab from './HomeTab.vue';
import { useContractQueries } from '@/hooks';
import ContractTabs from '@/components/Simulator/ContractTabs.vue';

const store = useContractsStore();
const { contractSchemaQuery } = useContractQueries();
const { error } = contractSchemaQuery;

const showHome = computed(() => store.currentContractId === '');
</script>

<template>
  <div class="flex h-full w-full flex-col">
    <ContractTabs />

    <HomeTab v-show="showHome" />

    <div
      v-for="contract in store.openedContracts"
      :key="contract.id"
      class="relative flex h-full w-full flex-col overflow-hidden"
      v-show="contract.id === store.currentContractId"
    >
      <div class="flex h-full w-full grow overflow-hidden">
        <CodeEditor :contract="contract" />
      </div>

      <div
        v-if="!!error"
        class="max-h-[160px] w-full shrink-0 overflow-y-auto whitespace-pre-wrap bg-red-500 bg-opacity-80 px-2 py-1 text-xs text-white"
      >
        {{ error }}
      </div>
    </div>
  </div>
</template>
