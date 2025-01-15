<script setup lang="ts">
import { useContractQueries } from '@/hooks';
import { computed } from 'vue';
import PageSection from '@/components/Simulator/PageSection.vue';
import ContractMethodItem from '@/components/Simulator/ContractMethodItem.vue';
import EmptyListPlaceholder from '@/components/Simulator/EmptyListPlaceholder.vue';
import type { ContractSchema } from 'genlayer-js/types';

const props = defineProps<{
  leaderOnly: boolean;
}>();

const { contractAbiQuery } = useContractQueries();

const { data, isPending, isError, error, isRefetching } = contractAbiQuery;

const readMethods = computed(() => {
  const methods = (data.value as ContractSchema).methods;
  return Object.entries(methods).filter((x) => x[1].readonly);
});
</script>

<template>
  <PageSection data-testid="contract-read-methods">
    <template #title
      >Read Methods
      <Loader v-if="isRefetching" :size="14" />
    </template>

    <ContentLoader v-if="isPending" />

    <Alert v-else-if="isError" error>
      {{ error?.message }}
    </Alert>

    <template v-else-if="data">
      <ContractMethodItem
        v-for="method in readMethods"
        :name="method[0]"
        :key="method[0]"
        :method="method[1]"
        methodType="read"
        :leaderOnly="props.leaderOnly"
      />

      <EmptyListPlaceholder v-if="readMethods.length === 0">
        No read methods.
      </EmptyListPlaceholder>
    </template>
  </PageSection>
</template>
