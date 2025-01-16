import { simulator } from 'genlayer-js/chains';
import { createClient } from 'genlayer-js';
import type { Account, GenLayerClient } from 'genlayer-js/types';
import { watch } from 'vue';
import { useAccountsStore } from '@/stores';

let client: GenLayerClient<typeof simulator> | null = null;

export function useGenlayer() {
  const accountsStore = useAccountsStore();

  if (!client) {
    initClient();
  }

  watch([() => accountsStore.selectedAccount?.address], () => {
    initClient();
  });

  function initClient() {
    const clientAccount =
      accountsStore.selectedAccount?.type === 'local'
        ? (accountsStore.selectedAccount as Account)
        : accountsStore.selectedAccount?.address;

    client = createClient({
      chain: simulator,
      endpoint: import.meta.env.VITE_JSON_RPC_SERVER_URL,
      account: clientAccount,
    });
  }

  return {
    client,
    initClient,
  };
}
