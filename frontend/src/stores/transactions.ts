import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { TransactionItem } from '@/types';
import { useDb, useRpcClient, useWebSocketClient } from '@/hooks';
import { useContractsStore } from '@/stores';

export const useTransactionsStore = defineStore('transactionsStore', () => {
  const rpcClient = useRpcClient();
  const webSocketClient = useWebSocketClient();
  const transactions = ref<TransactionItem[]>([]);
  const contractsStore = useContractsStore();
  const subscriptions = new Set();
  const db = useDb();

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
        status: tx.status,
        data: tx,
      });

      if (currentTx.type === 'deploy' && tx.status === 'FINALIZED') {
        contractsStore.addDeployedContract({
          contractId: currentTx.localContractId,
          address: tx.data.contract_address,
          defaultState: '{}',
        });
      }
    } else {
      // Temporary logging to debug always-PENDING transactions
      console.warn('Transaction not found', tx);
      console.trace('updateTransaction', tx);
    }
  }

  async function refreshPendingTransactions() {
    const pendingTxs = transactions.value.filter(
      (tx: TransactionItem) => tx.status !== 'FINALIZED',
    ) as TransactionItem[];

    await Promise.all(
      pendingTxs.map(async (tx) => {
        const newTx = await getTransaction(tx.hash);

        if (newTx) {
          updateTransaction(newTx);
          await db.transactions.where('hash').equals(tx.hash).modify({
            status: newTx.status,
            data: newTx,
          });
        } else {
          removeTransaction(tx);
          await db.transactions.where('hash').equals(tx.hash).delete();
        }
      }),
    );
  }

  async function getTransaction(hash: string) {
    return rpcClient.getTransactionByHash(hash);
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

  async function setTransactionAppeal(tx_address: string) {
    rpcClient.setTransactionAppeal(tx_address);
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
