import { useTransactionsStore } from '@/stores';
import type { TransactionItem } from '@/types';
import { useWebSocketClient } from '@/hooks';

export function useTransactionListener() {
  const transactionsStore = useTransactionsStore();
  const webSocketClient = useWebSocketClient();
  const latestRequestTimes = new Map<string, number>();

  function init() {
    webSocketClient.on(
      'transaction_status_updated',
      handleTransactionStatusUpdate,
    );
  }

  async function getTransaction(hash: string, requestTime: number) {
    const result = await transactionsStore.getTransaction(hash);

    // Only process the result if this is still the latest request for this hash
    if (latestRequestTimes.get(hash) === requestTime) {
      return result;
    } else {
      return null;
    }
  }

  async function handleTransactionStatusUpdate(eventData: any) {
    const { hash } = eventData.data;

    const requestTime = Date.now();
    latestRequestTimes.set(hash, requestTime);

    const newTx = await getTransaction(hash, requestTime);

    if (!newTx) {
      console.warn('Server tx not found for local tx:', newTx);
      transactionsStore.removeTransaction(newTx);
      return;
    }

    const currentTx = transactionsStore.transactions.find(
      (t: TransactionItem) => t.hash === hash,
    );

    if (!currentTx) {
      // This happens when local transactions get cleared (e.g. user clears all txs or deploys new contract instance)
      console.warn('Current tx not found:', hash);
      return;
    }

    transactionsStore.updateTransaction(newTx);
  }

  return {
    init,
  };
}
