import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import type { Address } from '@/types';
import { createAccount, generatePrivateKey } from 'genlayer-js';
import { useShortAddress } from '@/hooks';

export interface AccountInfo {
  type: 'local' | 'metamask';
  address: Address;
  privateKey?: Address; // Only for local accounts
}

export const useAccountsStore = defineStore('accountsStore', () => {
  const { shorten } = useShortAddress();

  // Store all accounts (both local and MetaMask)
  const accounts = ref<AccountInfo[]>([]);
  const selectedAccount = ref<AccountInfo | null>(null);

  // Initialize local accounts from localStorage
  const storedKeys = localStorage.getItem('accountsStore.privateKeys');
  if (storedKeys) {
    const privateKeys = storedKeys.split(',') as Address[];
    accounts.value = privateKeys.map((key) => ({
      type: 'local',
      address: createAccount(key).address,
      privateKey: key,
    }));

    // Set initial selected account if stored
    const storedSelectedKey = localStorage.getItem(
      'accountsStore.currentPrivateKey',
    );
    if (storedSelectedKey) {
      selectedAccount.value =
        accounts.value.find((acc) => acc.privateKey === storedSelectedKey) ||
        null;
    }
  }

  async function fetchMetaMaskAccount() {
    if (window.ethereum) {
      const ethAccounts = await window.ethereum.request({
        method: 'eth_requestAccounts',
      });

      const metamaskAccount: AccountInfo = {
        type: 'metamask',
        address: ethAccounts[0] as Address,
      };

      // Update or add MetaMask account
      const existingMetaMaskIndex = accounts.value.findIndex(
        (acc) => acc.type === 'metamask',
      );
      if (existingMetaMaskIndex >= 0) {
        accounts.value[existingMetaMaskIndex] = metamaskAccount;
      } else {
        accounts.value.push(metamaskAccount);
      }

      setCurrentAccount(metamaskAccount);
    }
  }

  if (window.ethereum) {
    window.ethereum.on('accountsChanged', (newAccounts: string[]) => {
      if (newAccounts.length > 0) {
        const metamaskAccount: AccountInfo = {
          type: 'metamask',
          address: newAccounts[0] as Address,
        };

        const existingMetaMaskIndex = accounts.value.findIndex(
          (acc) => acc.type === 'metamask',
        );
        if (existingMetaMaskIndex >= 0) {
          accounts.value[existingMetaMaskIndex] = metamaskAccount;
        }

        if (selectedAccount.value?.type === 'metamask') {
          setCurrentAccount(metamaskAccount);
        }
      }
    });
  }

  function generateNewAccount(): Address {
    const privateKey = generatePrivateKey();
    const newAccount: AccountInfo = {
      type: 'local',
      address: createAccount(privateKey).address,
      privateKey,
    };

    accounts.value.push(newAccount);
    setCurrentAccount(newAccount);

    const storedKeys = localStorage.getItem('accountsStore.privateKeys');
    if (storedKeys) {
      localStorage.setItem(
        'accountsStore.privateKeys',
        [...storedKeys.split(','), privateKey].join(','),
      );
    } else {
      localStorage.setItem('accountsStore.privateKeys', privateKey);
    }
    return privateKey;
  }

  function removeAccount(accountToRemove: AccountInfo) {
    if (
      accounts.value.filter((acc) => acc.type === 'local').length <= 1 &&
      accountToRemove.type === 'local'
    ) {
      throw new Error('You need at least 1 local account');
    }

    accounts.value = accounts.value.filter((acc) =>
      acc.type === 'metamask'
        ? acc.address !== accountToRemove.address
        : acc.privateKey !== accountToRemove.privateKey,
    );

    if (selectedAccount.value === accountToRemove) {
      const firstLocalAccount = accounts.value.find(
        (acc) => acc.type === 'local',
      );
      if (firstLocalAccount) {
        setCurrentAccount(firstLocalAccount);
      }
    }
  }

  function setCurrentAccount(account: AccountInfo | null) {
    selectedAccount.value = account;

    // Persist local account selection to localStorage
    if (account?.type === 'local' && account.privateKey) {
      localStorage.setItem(
        'accountsStore.currentPrivateKey',
        account.privateKey,
      );
    } else {
      // Clear stored private key if no local account is selected
      localStorage.removeItem('accountsStore.currentPrivateKey');
    }
  }

  const displayAddress = computed(() => {
    if (!selectedAccount.value) return '';
    try {
      return shorten(selectedAccount.value.address);
    } catch (err) {
      console.error(err);
      return '0x';
    }
  });

  const currentUserAccount = computed(() => {
    if (!selectedAccount.value) return undefined;

    if (
      selectedAccount.value.type === 'local' &&
      selectedAccount.value.privateKey
    ) {
      return createAccount(selectedAccount.value.privateKey);
    }

    if (selectedAccount.value.type === 'metamask') {
      // For MetaMask accounts, return a minimal account interface with just the address
      return {
        address: selectedAccount.value.address,
        type: 'metamask',
      };
    }

    return undefined;
  });

  const currentUserAddress = computed(() =>
    selectedAccount.value ? selectedAccount.value.address : '',
  );

  // For backwards compatibility and persistence
  const privateKeys = computed(() =>
    accounts.value
      .filter((acc) => acc.type === 'local')
      .map((acc) => acc.privateKey!),
  );

  return {
    accounts,
    selectedAccount,
    currentUserAccount,
    currentUserAddress,
    privateKeys,
    fetchMetaMaskAccount,
    generateNewAccount,
    removeAccount,
    setCurrentAccount,
    displayAddress,
  };
});
