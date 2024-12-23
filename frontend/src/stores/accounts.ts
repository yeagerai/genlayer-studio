import { defineStore } from 'pinia';
import { computed, ref, watch } from 'vue';
import type { Address } from '@/types';
import { createAccount, generatePrivateKey } from 'genlayer-js';
import { useShortAddress } from '@/hooks';

export const useAccountsStore = defineStore('accountsStore', () => {
  const key = localStorage.getItem('accountsStore.currentPrivateKey');
  const currentPrivateKey = ref<Address | null>(key ? (key as Address) : null);
  const currentUserAddress = computed(() =>
    currentPrivateKey.value
      ? createAccount(currentPrivateKey.value).address
      : '',
  );
  const { shorten } = useShortAddress();

  const privateKeys = ref<Address[]>(
    localStorage.getItem('accountsStore.privateKeys')
      ? ((localStorage.getItem('accountsStore.privateKeys') || '').split(
          ',',
        ) as Address[])
      : [],
  );

  const walletAddress = ref<Address | undefined>(undefined);
  const isWalletSelected = ref<boolean>(false);

  async function fetchMetaMaskAccount() {
    if (window.ethereum) {
      const accounts = await window.ethereum.request({
        method: 'eth_requestAccounts',
      });

      walletAddress.value = accounts[0];
      setCurrentAccount();
    }
  }

  if (window.ethereum) {
    window.ethereum.on('accountsChanged', (accounts: string[]) => {
      walletAddress.value = accounts[0] as Address;
    });
  }

  function generateNewAccount(): Address {
    const privateKey = generatePrivateKey();
    privateKeys.value = [...privateKeys.value, privateKey];
    setCurrentAccount(privateKey);
    return privateKey;
  }

  function removeAccount(privateKey: Address) {
    if (privateKeys.value.length <= 1) {
      throw new Error('You need at least 1 account');
    }

    privateKeys.value = privateKeys.value.filter((k) => k !== privateKey);

    if (currentPrivateKey.value === privateKey) {
      setCurrentAccount(privateKeys.value[0]);
    }
  }

  function setCurrentAccount(privateKey?: Address) {
    if (privateKey) {
      currentPrivateKey.value = privateKey;
    }
    isWalletSelected.value = !privateKey;
  }

  const displayAddress = computed(() => {
    try {
      if (walletAddress.value) {
        return shorten(walletAddress.value);
      }
      if (!currentPrivateKey.value) {
        return '';
      } else {
        return shorten(createAccount(currentPrivateKey.value).address);
      }
    } catch (err) {
      console.error(err);
      return '0x';
    }
  });

  return {
    currentUserAddress,
    currentPrivateKey,
    privateKeys,
    walletAddress,
    isWalletSelected,
    fetchMetaMaskAccount,
    generateNewAccount,
    removeAccount,
    setCurrentAccount,
    displayAddress,
  };
});
