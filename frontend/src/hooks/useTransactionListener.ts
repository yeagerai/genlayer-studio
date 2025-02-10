import { useTransactionsStore } from '@/stores';
import type { TransactionItem } from '@/types';
import { useWebSocketClient } from '@/hooks';

export function useTransactionListener() {
  const transactionsStore = useTransactionsStore();
  const webSocketClient = useWebSocketClient();

  function init() {
    webSocketClient.on(
      'transaction_status_updated',
      handleTransactionStatusUpdate,
    );
  }

  async function handleTransactionStatusUpdate(eventData: any) {
    const newTx = await transactionsStore.getTransaction(eventData.data.hash);

    const currentTx = transactionsStore.transactions.find(
      (t: TransactionItem) => t.hash === eventData.data.hash,
    );

    if (!newTx) {
      if (currentTx) {
        console.log('Server tx not found for local tx:', currentTx);
        // We're cleaning up local txs that don't exist on the server anymore
        transactionsStore.removeTransaction(currentTx);
      }

      return;
    }

    if (!currentTx) {
      // This happens regularly when local transactions get cleared (e.g. user clears all txs or deploys new contract instance)
      return;
    }

    const statusOrder = [
      'PENDING',
      'CANCELED',
      'PROPOSING',
      'COMMITTING',
      'REVEALING',
      'ACCEPTED',
      'FINALIZED',
      // UNDETERMINED ?
    ];

    // Only update if new status is later in the sequence than current status to prevent race conditions
    const currentStatusIndex = statusOrder.indexOf(currentTx.status);
    const newStatusIndex = statusOrder.indexOf(newTx.status);

    if (newStatusIndex < currentStatusIndex) {
      console.warn('Ignoring out-of-order status update:', newTx.status);
      alert('YES')
      return;
    }

    console.log(currentStatusIndex, newStatusIndex)

    transactionsStore.updateTransaction(newTx);
  }

  return {
    init,
  };
}
