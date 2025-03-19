<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useContractsStore, useTransactionsStore } from '@/stores';
import { TrashIcon } from '@heroicons/vue/24/solid';
import TransactionItem from './TransactionItem.vue';
import PageSection from './PageSection.vue';
import EmptyListPlaceholder from '@/components/Simulator/EmptyListPlaceholder.vue';
import { RpcClient } from '@/clients/rpc.ts';

const contractsStore = useContractsStore();
const transactionsStore = useTransactionsStore();
const rpcClient = new RpcClient();
const relatedTransactions = ref([]);

const props = defineProps({
  finalityWindow: Number,
});

// Function to fetch related transactions
const fetchRelatedTransactions = async (contractAddress: string) => {
  if (!contractAddress) return;

  try {
    const response = await rpcClient.call({
      method: 'gen_getTransactionsByRelatedContract',
      params: [contractAddress],
    });

    if (response.result) {
      relatedTransactions.value = response.result;
    }
  } catch (error) {
    console.error('Error fetching related transactions:', error);
  }
};

// Watch for changes to the contract address and fetch related transactions
watch(
  () => {
    const transactions = transactionsStore.transactions.filter(
      (t) => t.localContractId === contractsStore.currentContractId,
    );
    return transactions.length > 0 ? transactions[0].data?.to_address : null;
  },
  (newAddress) => {
    if (newAddress) {
      fetchRelatedTransactions(newAddress);
    }
  },
  { immediate: true },
);

const transactions = computed(() => {
  const contractTransactions = transactionsStore.transactions.filter(
    (t) => t.localContractId === contractsStore.currentContractId,
  );

  // Combine both transaction sets
  const allTransactions = [
    ...contractTransactions,
    ...relatedTransactions.value,
  ];

  // Sort all transactions by date
  const transactionsOrderedByDate = allTransactions
    .slice()
    .sort(
      (a, b) =>
        new Date(b.data.created_at).getTime() -
        new Date(a.data.created_at).getTime(),
    );

  return transactionsOrderedByDate;
});

const isClearTransactionsModalOpen = ref(false);

const handleClearTransactions = () => {
  transactionsStore.clearTransactionsForContract(
    contractsStore.currentContractId ?? '',
  );

  isClearTransactionsModalOpen.value = false;
};
</script>

<template>
  <PageSection data-testid="latest-transactions">
    <template #title>Transactions</template>

    <template #actions
      ><GhostBtn
        v-if="transactions.length > 0"
        @click="isClearTransactionsModalOpen = true"
        v-tooltip="'Clear Transactions List'"
      >
        <TrashIcon class="h-4 w-4" /></GhostBtn
    ></template>

    <div class="flex flex-col">
      <TransactionItem
        v-for="transaction in transactions"
        :key="transaction.hash"
        :transaction="transaction"
        :finalityWindow="props.finalityWindow ?? 0"
      />
    </div>

    <EmptyListPlaceholder v-if="transactions.length === 0">
      No transactions yet.
    </EmptyListPlaceholder>

    <ConfirmationModal
      :open="isClearTransactionsModalOpen"
      @close="isClearTransactionsModalOpen = false"
      @confirm="handleClearTransactions"
      buttonText="Clear Transactions"
      dangerous
    >
      <template #title>Clear Transaction List</template>
      <template #description
        >Are you sure you want to clear all transactions?</template
      >
    </ConfirmationModal>
  </PageSection>
</template>
