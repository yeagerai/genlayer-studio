import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { TransactionItem } from '@/types';
import type { TransactionHash } from 'genlayer-js/types';
import { TransactionStatus } from 'genlayer-js/types';
import { useDb, useGenlayer, useWebSocketClient, useRpcClient } from '@/hooks';
import { useContractsStore } from '@/stores';

export const useTransactionsStore = defineStore('transactionsStore', () => {
  const genlayer = useGenlayer();
  const genlayerClient = computed(() => genlayer.client.value);
  const webSocketClient = useWebSocketClient();
  const transactions = ref<TransactionItem[]>([]);
  const subscriptions = new Set();
  const db = useDb();
  const rpcClient = useRpcClient();

  function addTransaction(tx: TransactionItem) {
    transactions.value.unshift(tx); // Push on top in case there's no date property yet
    subscribe([tx.hash]);
  }

  function removeTransaction(tx: TransactionItem) {
    transactions.value = transactions.value.filter((t) => t.hash !== tx.hash);
    unsubscribe(tx.hash);
  }

  function updateTransaction(tx: any) {
    const currentTxIndex = transactions.value.findIndex(
      (t) => t.hash === tx.hash,
    );

    if (currentTxIndex !== -1) {
      const currentTx = transactions.value[currentTxIndex];

      transactions.value.splice(currentTxIndex, 1, {
        ...currentTx,
        statusName: tx.statusName,
        data: tx,
      });
    } else {
      // Temporary logging to debug always-PENDING transactions
      console.warn('Transaction not found', tx);
      console.trace('updateTransaction', tx);
    }
  }

  async function getTransaction(hash: TransactionHash) {
    return genlayerClient.value?.getTransaction({ hash });
  }

  async function refreshPendingTransactions() {
    const pendingTxs = transactions.value.filter(
      (tx: TransactionItem) => tx.statusName !== TransactionStatus.FINALIZED,
    ) as TransactionItem[];

    await Promise.all(
      pendingTxs.map(async (tx) => {
        const newTx = await getTransaction(tx.hash as TransactionHash);

        if (newTx) {
          updateTransaction(newTx);
          await db.transactions.where('hash').equals(tx.hash).modify({
            statusName: newTx.statusName,
            data: newTx,
          });
        } else {
          removeTransaction(tx);
          await db.transactions.where('hash').equals(tx.hash).delete();
        }
      }),
    );
  }

  async function clearTransactionsForContract(contractId: string) {
    const contractTxs = transactions.value.filter(
      (t) => t.localContractId === contractId,
    );

    contractTxs.forEach((t) => unsubscribe(t.hash));

    transactions.value = transactions.value.filter(
      (t) => t.localContractId !== contractId,
    );

    await db.transactions.where('localContractId').equals(contractId).delete();
  }

  async function setTransactionAppeal(tx_address: `0x${string}`) {
    await genlayerClient.value?.appealTransaction({
      txId: tx_address,
    });
  }

  function subscribe(topics: string[]) {
    topics.forEach((topic) => {
      subscriptions.add(topic);
    });
    if (webSocketClient.connected) {
      webSocketClient.emit('subscribe', topics);
    }
  }

  function unsubscribe(topic: string) {
    const deleted = subscriptions.delete(topic);
    if (deleted && webSocketClient.connected) {
      webSocketClient.emit('unsubscribe', [topic]);
    }
  }

  function initSubscriptions() {
    subscribe(transactions.value.map((t) => t.hash));
  }

  async function resetStorage() {
    transactions.value.forEach((t) => unsubscribe(t.hash));
    transactions.value = [];
    await db.transactions.clear();
  }

  return {
    transactions,
    getTransaction,
    addTransaction,
    removeTransaction,
    updateTransaction,
    clearTransactionsForContract,
    setTransactionAppeal,
    refreshPendingTransactions,
    initSubscriptions,
    resetStorage,
  };
});
