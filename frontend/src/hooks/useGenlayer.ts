import { simulator } from 'genlayer-js/chains';
import { createClient, createAccount } from 'genlayer-js';
import type { GenLayerClient } from 'genlayer-js/types';
import { watch } from 'vue';
import { useAccountsStore } from '@/stores';

let client: GenLayerClient<typeof simulator> | null = null;

export function useGenlayer() {
  const accountsStore = useAccountsStore();

  if (!client) {
    initClient();
  }

  watch(
      [
        () => accountsStore.currentUserAddress,
        () => accountsStore.isWalletSelected,
        () => accountsStore.walletAddress,
      ],
      () => {
        initClient();
      },
  );

  function initClient() {
    client = createClient({
      chain: simulator,
      endpoint: import.meta.env.VITE_JSON_RPC_SERVER_URL,
      accountOrAddress: accountsStore.isWalletSelected ? accountsStore.walletAddress : createAccount(accountsStore.currentPrivateKey || undefined),
    });
  }

  return {
    client,
    initClient,
  };
}
